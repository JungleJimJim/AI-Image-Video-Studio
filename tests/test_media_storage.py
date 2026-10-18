"""Media relocation must preserve bytes, metadata and queued work."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from common import atomic_json, load_json
from media_storage import digest, media_folder, migrate_library


class MediaStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old = self.root / 'Videos'
        (self.old / 'Images').mkdir(parents=True)
        self.image = self.old / 'Images' / 'café & image.png'
        self.image.write_bytes(b'original image bytes')
        self.mask = self.image.with_suffix('.mask.png')
        self.mask.write_bytes(b'original mask bytes')
        self.video = self.old / 'clip.mp4'
        self.video.write_bytes(b'original video bytes')
        self.settings = dict(output=str(self.old), options={'seed': 42}, custom='keep')
        self.images = [dict(id='image', path=str(self.image), mask_path=str(self.mask),
                            options={'seed': 42, 'model': 'flux3'}, parent_id='original')]
        self.videos = [dict(id='video', path=str(self.video), options={'seed': 123})]
        for name, data in [('settings.json', self.settings), ('images.json', self.images),
                           ('library.json', self.videos), ('queue.json', {'paused': True, 'jobs': [
                               {'id': 'queued', 'output': str(self.old), 'priority': 9, 'options': {'seed': 19}}]})]:
            atomic_json(self.root / name, data)
        atomic_json(self.image.with_suffix('.json'), {**self.images[0], 'workflow': {'keep': True}})

    def test_relocation_preserves_media_metadata_masks_queue_and_settings(self):
        before = [digest(path) for path in (self.image, self.mask, self.video)]
        result = migrate_library(self.root, self.settings)
        image = load_json(self.root / 'images.json', [])[0]
        video = load_json(self.root / 'library.json', [])[0]
        new_paths = [Path(image['path']), Path(image['mask_path']), Path(video['path'])]
        self.assertEqual([digest(path) for path in new_paths], before)
        self.assertEqual(new_paths[0].parent, self.root / 'Library/Images')
        self.assertEqual(new_paths[2].parent, self.root / 'Library/Videos')
        self.assertEqual(image['options'], self.images[0]['options'])
        self.assertEqual(image['parent_id'], 'original')
        sidecar = load_json(new_paths[0].with_suffix('.json'), {})
        self.assertEqual(sidecar['path'], image['path'])
        self.assertEqual(sidecar['mask_path'], image['mask_path'])
        self.assertEqual(sidecar['workflow'], {'keep': True})
        self.assertEqual(result, {**self.settings, 'output': str(self.root / 'Library'), 'media_layout': 2})
        job = load_json(self.root / 'queue.json', {})['jobs'][0]
        self.assertEqual(job, {'id': 'queued', 'output': result['output'], 'priority': 9, 'options': {'seed': 19}})
        self.assertFalse(self.old.exists())
        # Reopening must neither duplicate files nor move the library again.
        files = sorted(str(path) for path in (self.root / 'Library').rglob('*'))
        self.assertEqual(migrate_library(self.root, result), result)
        self.assertEqual(files, sorted(str(path) for path in (self.root / 'Library').rglob('*')))

    def test_existing_destination_and_sidecar_are_never_overwritten(self):
        target = self.root / 'Library/Images' / self.image.name
        target.parent.mkdir(parents=True)
        target.with_suffix('.json').write_bytes(b'unrelated existing sidecar')
        result = migrate_library(self.root, self.settings)
        moved = Path(load_json(self.root / 'images.json', [])[0]['path'])
        self.assertNotEqual(moved, target)
        self.assertEqual(target.with_suffix('.json').read_bytes(), b'unrelated existing sidecar')
        self.assertEqual(moved.read_bytes(), b'original image bytes')

    def test_failed_commit_keeps_original_files_and_can_retry(self):
        def fail_settings(path, data):
            if Path(path) == self.root / 'settings.json':
                raise PermissionError('fixture: settings commit interrupted')
            atomic_json(path, data)
        with patch('media_storage.atomic_json', side_effect=fail_settings), self.assertRaises(PermissionError):
            migrate_library(self.root, self.settings)
        self.assertEqual(self.image.read_bytes(), b'original image bytes')
        self.assertEqual(self.video.read_bytes(), b'original video bytes')
        self.assertEqual(load_json(self.root / 'settings.json', {}), self.settings)
        result = migrate_library(self.root, self.settings)
        self.assertEqual(result['media_layout'], 2)
        self.assertTrue(Path(load_json(self.root / 'images.json', [])[0]['path']).is_file())
        self.assertFalse(self.image.exists())

    def test_cleanup_preserves_a_source_changed_after_copy(self):
        with patch('media_storage.finish_cleanup'):
            result = migrate_library(self.root, self.settings)
        self.image.write_bytes(b'user changed the old file')
        migrate_library(self.root, result)
        self.assertEqual(self.image.read_bytes(), b'user changed the old file')

    def test_all_new_image_operations_and_videos_share_sibling_folders(self):
        result = migrate_library(self.root, self.settings)
        self.assertEqual(media_folder(self.root, 'image'), Path(result['output']) / 'Images')
        self.assertEqual(media_folder(self.root, 'video'), Path(result['output']) / 'Videos')
        custom = self.root / 'custom library'
        self.assertEqual(media_folder(self.root, 'video', custom), custom / 'Videos')


if __name__ == '__main__':
    unittest.main()
