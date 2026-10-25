"""Canvas persistence, resource limits and imports independent of inference."""
import copy
import http.client
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import canvas_projects as projects
from app import Studio,make_handler
from media_storage import metadata_path


def document():
    return dict(name='Poster',width=1024,height=768,background='#112233',layers=[
        dict(id='portrait',kind='image',source_id='a'*24,name='Photo',x=12,y=34,w=400,h=300,opacity=.7,rotation=25,locked=True),
        dict(id='title',kind='text',text='Hello\nworld',font='serif',font_size=90,color='#ffaa00',visible=False)])


class CanvasTests(unittest.TestCase):
    def test_canvas_http_routes_require_token_and_restore_only_library_sources(self):
        with tempfile.TemporaryDirectory() as temp,patch('app.gpu_info',return_value={}):
            studio=Studio(temp);studio.images=[dict(id='a'*24,path='fixture.png',name='Photo',width=512,height=512),dict(id='d'*24,path='other.png')]
            server=http.server.ThreadingHTTPServer(('127.0.0.1',0),make_handler(studio,lambda:None))
            threading.Thread(target=server.serve_forever,daemon=True).start()
            def request(route,body=None,authorized=True):
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                headers={'X-Wan-Token':studio.token} if authorized else {}
                connection.request('POST' if body is not None else 'GET',route,json.dumps(body) if body is not None else None,headers)
                response=connection.getresponse();result=response.status,json.loads(response.read());connection.close();return result
            try:
                self.assertEqual(request('/api/canvas/projects',authorized=False)[0],403)
                status,result=request('/api/canvas/project',{'project':document()});self.assertEqual(status,200)
                key=result['project']['id'];status,result=request('/api/canvas/project/'+key)
                self.assertEqual(status,200);self.assertEqual([s['id'] for s in result['sources']],['a'*24])
                self.assertEqual(request('/api/canvas/projects')[1]['items'][0]['id'],key)
                self.assertEqual(request('/api/canvas/project/../settings')[0],400)
                self.assertEqual(request('/api/canvas/draft')[1]['project'],None)
                self.assertEqual(request('/api/canvas/draft',{'project':document()})[0],200)
                self.assertEqual(request('/api/canvas/draft')[1]['project']['name'],'Poster')
            finally:server.shutdown();server.server_close()

    def test_named_projects_draft_and_roundtrip_preserve_editable_layers(self):
        with tempfile.TemporaryDirectory() as temp:
            saved=projects.save(temp,document());loaded=projects.load(temp,saved['id'])
            self.assertEqual(loaded,projects.validate(saved));self.assertEqual(loaded['layers'][0]['rotation'],25)
            self.assertTrue(loaded['layers'][0]['locked']);self.assertFalse(loaded['layers'][1]['visible'])
            self.assertEqual(loaded['layers'][1]['text'],'Hello\nworld')
            projects.save(temp,saved,True);self.assertEqual(projects.load(temp),loaded)
            self.assertEqual(len(projects.catalog(temp)),1)
            self.assertFalse((Path(temp)/'Library').exists())

    def test_untrusted_ids_cannot_escape_project_folder_or_overwrite_files(self):
        with tempfile.TemporaryDirectory() as temp:
            for key in ('../settings','A'*24,'..\\settings',42,None):
                if key is None:continue
                with self.subTest(key=key),self.assertRaises(ValueError):projects.load(temp,key)
            with self.assertRaisesRegex(ValueError,'no longer exists'):projects.save(temp,document()|{'id':'b'*24})
            self.assertIsNone(projects.load(temp))

    def test_invalid_dimensions_layers_and_nonfinite_values_rejected(self):
        bad=[{'width':8192,'height':8192},{'height':63},{'width':True},{'height':1024.5},{'background':'red'},
             {'layers':[{'id':'x','kind':'image','source_id':'../secret'}]},
             {'layers':[{'id':'x','kind':'text','x':float('nan')}]},
             {'layers':[{'id':'x','kind':'text','opacity':float('inf')}]},
             {'layers':[{'id':'x','kind':'text','w':0}]},
             {'layers':[{'id':'x','kind':'text','visible':'false'}]},
             {'layers':[{'id':'x','kind':'text','font':'arbitrary font'}]},
             {'layers':[{'id':'x','kind':'text'}]*2},
             {'layers':[{'id':str(i),'kind':'text'} for i in range(65)]}]
        for change in bad:
            with self.subTest(change=change),self.assertRaises(ValueError):projects.validate(document()|change)

    def test_canvas_import_and_export_preserve_running_job_state(self):
        for composite in (False,True):
            with self.subTest(composite=composite),tempfile.TemporaryDirectory() as temp,patch('app.gpu_info',return_value={}):
                studio=Studio(temp);studio.state.update(busy=True,stage='Rendering',progress=.37,result='in progress')
                before=copy.deepcopy(studio.state);path=Path(temp)/'Library/Images/new.png';path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
                info=dict(id='c'*24,path=str(path),name='Poster.png',width=1024,height=768)
                with patch('app.import_image',return_value=info) as importer,patch.object(studio.thumbnails,'get'),patch.object(studio.engine,'stop') as stop:
                    result=studio.canvas_image({'data':'mock','project':document()},composite)
                    self.assertEqual(importer.call_args.kwargs['preserve_alpha'],not composite);stop.assert_not_called()
                self.assertEqual(studio.state,before);self.assertEqual(studio.revision,1)
                self.assertEqual(json.loads((Path(temp)/'images.json').read_text())[0]['kind'],'canvas_composite' if composite else 'canvas_source')
                self.assertTrue(metadata_path(path).is_file());self.assertEqual(result['media_type'],'image')
                if composite:self.assertEqual(result['canvas_project']['layers'][0]['source_id'],'a'*24)

    def test_source_import_keeps_running_generation_and_queue_untouched(self):
        with tempfile.TemporaryDirectory() as temp,patch('app.gpu_info',return_value={}):
            studio=Studio(temp);studio.state.update(busy=True,stage='Rendering',progress=.4,latest_media={'id':'render-result'})
            before=copy.deepcopy(studio.state);queue=copy.deepcopy(studio.queue.jobs)
            path=Path(temp)/'Library/Images/source.png';path.write_bytes(b'fixture')
            info=dict(id='e'*24,path=str(path),name='Source.png',width=512,height=512)
            with patch('app.import_image',return_value=info) as importer,patch.object(studio.thumbnails,'get'),patch.object(studio.engine,'stop') as stop:
                result=studio.source_image({'data':'mock'})
            self.assertEqual(studio.state,before);self.assertEqual(studio.queue.jobs,queue);stop.assert_not_called()
            self.assertEqual(result['kind'],'imported');self.assertEqual(result['id'],'e'*24)
            self.assertFalse(importer.call_args.kwargs['preserve_alpha']);self.assertEqual(studio.revision,1)

    def test_mismatched_export_does_not_enter_library(self):
        with tempfile.TemporaryDirectory() as temp,patch('app.gpu_info',return_value={}):
            studio=Studio(temp);path=Path(temp)/'rejected.png';path.write_bytes(b'fixture')
            with patch('app.import_image',return_value=dict(path=str(path),width=64,height=64)),self.assertRaisesRegex(ValueError,'dimensions'):
                studio.canvas_image({'project':document()},True)
            self.assertEqual(studio.images,[]);self.assertFalse(path.exists());self.assertEqual(json.loads((Path(temp)/'images.json').read_text()),[])


if __name__=='__main__':unittest.main()
