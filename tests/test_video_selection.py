import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Studio
from engine import validate_options, build_workflow


class VideoSelectionTests(unittest.TestCase):
    def test_text_jobs_cannot_silently_ignore_an_attached_image(self):
        for model in ('wan13', 'wan22', 'ltx2', 'minimax_h3'):
            with self.subTest(model=model), self.assertRaisesRegex(ValueError, 'Text → Video'):
                validate_options(dict(model=model, mode='text', source_image='selected', prompt='A blue robot'))

    def test_wan_image_job_connects_its_image_to_the_sampler_latent(self):
        options = validate_options(dict(model='wan22', mode='image', source_image='selected', prompt='A blue robot'))
        graph = build_workflow(options | {'input_file': 'selected.png'}, 'fixture')
        latent = graph[graph['8']['inputs']['latent_image'][0]]
        loaded = graph[latent['inputs']['start_image'][0]]
        self.assertEqual(loaded['class_type'], 'LoadImage')
        self.assertEqual(loaded['inputs']['image'], 'selected.png')

    def test_selection_is_saved_during_work_without_changing_generation_options(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}):
            studio=Studio(tmp);image=Path(tmp)/'source.png';image.write_bytes(b'fixture')
            studio.images=[dict(id='source-a',path=str(image))]
            options=copy.deepcopy(studio.settings['options']);studio.state['busy']=True
            with patch.object(studio.engine,'stop') as stop:
                studio.save_settings({'video_source_image':'source-a'})
                stop.assert_not_called()
            self.assertEqual(json.loads((Path(tmp)/'settings.json').read_text())['video_source_image'],'source-a')
            self.assertEqual(studio.settings['options'],options)
            self.assertTrue(studio.state['busy'])

    def test_invalid_or_removed_image_cannot_replace_a_saved_selection(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}):
            studio=Studio(tmp);studio.settings['video_source_image']='saved'
            for value in ([],42,None,'missing'):
                with self.subTest(value=value),self.assertRaises(ValueError):studio.save_settings({'video_source_image':value})
                self.assertEqual(studio.settings['video_source_image'],'saved')
            studio.save_settings({'video_source_image':''})
            self.assertEqual(studio.settings['video_source_image'],'')

    def test_disk_failure_rolls_back_selection(self):
        with tempfile.TemporaryDirectory() as tmp,patch('app.gpu_info',return_value={}):
            studio=Studio(tmp);studio.settings['video_source_image']='old'
            image=Path(tmp)/'source.png';image.write_bytes(b'fixture')
            studio.images=[dict(id='new',path=str(image))]
            with patch('app.atomic_json',side_effect=OSError('disk full')),self.assertRaises(OSError):
                studio.save_settings({'video_source_image':'new'})
            self.assertEqual(studio.settings['video_source_image'],'old')
