"""Moving JSON sidecars must preserve media, metadata bytes and name collisions."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from common import atomic_json,load_json
from media_storage import metadata_path,migrate_metadata


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.library=Path(self.temp.name)/'Custom library'
        self.image=self.library/'Images/example.png';self.video=self.library/'Videos/example.mp4'
        for media in (self.image,self.video):
            media.parent.mkdir(parents=True,exist_ok=True);media.write_bytes(b'original media')
            atomic_json(media.with_suffix('.json'),{'path':str(media),'options':{'seed':42},'workflow':{'keep':True}})
        self.images=[{'path':str(self.image)}];self.videos=[{'path':str(self.video)}]

    def test_both_media_types_move_without_changing_bytes_or_settings(self):
        originals={p:p.with_suffix('.json').read_bytes() for p in (self.image,self.video)}
        self.assertEqual(migrate_metadata(self.images,self.videos),[])
        for media,content in originals.items():
            target=metadata_path(media)
            self.assertEqual(target.parent,self.library/'Metadata'/media.parent.name)
            self.assertEqual(target.read_bytes(),content)
            self.assertEqual(media.read_bytes(),b'original media')
            self.assertFalse(media.with_suffix('.json').exists())
        self.assertEqual(migrate_metadata(self.images,self.videos),[])
        self.assertEqual(len(list((self.library/'Metadata').rglob('*.json'))),2)

    def test_existing_different_metadata_is_preserved(self):
        target=metadata_path(self.image);atomic_json(target,{'unrelated':'keep'})
        content=self.image.with_suffix('.json').read_bytes()
        self.assertEqual(migrate_metadata(self.images,[]),[])
        self.assertEqual(load_json(target,{}),{'unrelated':'keep'})
        backups=list(target.parent.glob('*-previous-*.json'))
        self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_bytes(),content)
        self.assertFalse(self.image.with_suffix('.json').exists())

    def test_failed_copy_keeps_original_and_can_retry(self):
        sidecar=self.image.with_suffix('.json');content=sidecar.read_bytes()
        with patch('media_storage.os.replace',side_effect=PermissionError('locked')):
            self.assertEqual(len(migrate_metadata(self.images,[])),1)
        self.assertEqual(sidecar.read_bytes(),content)
        self.assertFalse(metadata_path(self.image).exists())
        self.assertEqual(migrate_metadata(self.images,[]),[])
        self.assertEqual(metadata_path(self.image).read_bytes(),content)

    def test_new_image_saves_metadata_separately(self):
        from app import Studio
        root=Path(self.temp.name)
        with patch('app.gpu_info',return_value={}):studio=Studio(root)
        info={'id':'new','path':str(self.image),'name':'example.png','options':{'seed':123}}
        studio.add_image(info,{'new':'workflow'})
        self.assertEqual(load_json(metadata_path(self.image),{})['workflow'],{'new':'workflow'})
        self.assertEqual(load_json(root/'images.json',[]),[info])


if __name__=='__main__':unittest.main()
