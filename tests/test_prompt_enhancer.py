import io,json,os,stat,sys,tempfile,threading,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import prompt_enhancer as p
from downloads import Cancelled
class PromptEnhancerTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
 def tearDown(self):self.temp.cleanup()
 def options(self,**extra):return p.validate(dict(prompt='A "green dragon" flying over a lake',context='image',mode='refine',**extra))
 def test_pinned_optional_cpu_pack(self):
  s=p.spec();self.assertIn('Q4',s['model_name']);self.assertEqual(len(s['model']['sha256']),64);self.assertTrue(s['model']['url'].startswith('https://huggingface.co/Qwen/'));self.assertTrue(s['runtime']['url'].startswith('https://github.com/ggml-org/llama.cpp/'));self.assertEqual(len(s['runtime']['sha256']),64);self.assertFalse(p.inventory(self.root)['ready'])
 def test_invalid_prompts_and_modes(self):
  for raw in ({},{'prompt':' '},{'prompt':'x'*4001},{'prompt':'x','context':'unknown'},{'prompt':'x','mode':'unknown'}):
   with self.assertRaises(ValueError):p.validate(raw)
 def test_context_and_intent_are_separate_from_user_input(self):
  for context in p.CONTEXTS:
   o=p.validate(dict(prompt='Keep "exact text" and two people',context=context,mode='expand'));messages=p.messages(o);self.assertEqual(messages[1]['content'],o['prompt']);self.assertIn(p.CONTEXTS[context],messages[0]['content']);self.assertIn('Preserve the user intent',messages[0]['content'])
 def archive(self,entries):
  path=self.root/'test.zip'
  with zipfile.ZipFile(path,'w') as z:
   for name,value in entries:z.writestr(name,value)
  return path
 def test_runtime_extracts_only_expected_executable_and_libraries(self):
  z=self.archive([('llama-server.exe',b'server'),('ggml.dll',b'library'),('llama-cli.exe',b'excluded'),('LICENSE',b'license')]);files=p.unpack(z,self.root/'runtime');self.assertEqual(set(files),{'llama-server.exe','ggml.dll','LICENSE'});self.assertFalse((self.root/'runtime/llama-cli.exe').exists())
 def test_runtime_rejects_traversal(self):
  with self.assertRaisesRegex(ValueError,'Unsafe'):p.unpack(self.archive([('../escape.dll',b'x')]),self.root/'runtime')
 def test_runtime_rejects_symlink(self):
  z=self.root/'link.zip';info=zipfile.ZipInfo('library.dll');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
  with zipfile.ZipFile(z,'w') as archive:archive.writestr(info,'outside')
  with self.assertRaisesRegex(ValueError,'Unsafe'):p.unpack(z,self.root/'runtime')
 def test_response_validation_and_truncation(self):
  self.assertEqual(p.clean_result({'choices':[{'finish_reason':'stop','message':{'content':'```text\nClear rewritten prompt\n```'}}]}),'Clear rewritten prompt')
  for data in ({},{'choices':[{'finish_reason':'length','message':{'content':'unfinished'}}]},{'choices':[{'message':{'content':'\x00invalid'}}]}):
   with self.assertRaises(ValueError):p.clean_result(data)
 def fake_transport(self,tokens=None):
  requests=[];processes=[]
  class Child:
   def __init__(self,command,**kwargs):self.command=command;self.env=kwargs['env'];self.closed=False;processes.append(self)
   def poll(self):return 0 if self.closed else None
   def terminate(self):self.closed=True
   def wait(self,**kwargs):return 0
  class Opener:
   def open(self,request,**kwargs):
    requests.append(request);route=request.full_url.split('/',3)[-1];data={'status':'ok'} if route=='health' else {'tokens':list(range(4000)) if tokens=='long' else [1,2,3]} if route=='tokenize' else {'choices':[{'finish_reason':'stop','message':{'content':'A clear visual prompt'}}]};return io.BytesIO(json.dumps(data).encode())
  return Child,Opener(),requests,processes
 def test_private_cpu_transport_and_process_cleanup(self):
  child,opener,requests,processes=self.fake_transport()
  with patch.object(p,'inventory',return_value={'ready':True}),patch.object(p.subprocess,'Popen',child),patch.object(p.urllib.request,'build_opener',return_value=opener),patch.dict(os.environ,{'LLAMA_ARG_TOOLS':'exec_shell_command'}):
   result=p.generate(self.root,self.options(),lambda *a:None,threading.Event())
  self.assertEqual(result,'A clear visual prompt');process=processes[0];self.assertTrue(process.closed);self.assertEqual(process.command[process.command.index('--n-gpu-layers')+1],'0');self.assertNotIn('LLAMA_ARG_TOOLS',process.env);self.assertNotIn(self.options()['prompt'],process.command);self.assertTrue(all(r.full_url.startswith('http://127.0.0.1:') and r.get_header('Authorization').startswith('Bearer ') for r in requests));self.assertEqual(len(requests),3)
 def test_too_long_tokenized_prompt_never_runs_completion(self):
  child,opener,requests,processes=self.fake_transport('long')
  with patch.object(p,'inventory',return_value={'ready':True}),patch.object(p.subprocess,'Popen',child),patch.object(p.urllib.request,'build_opener',return_value=opener):
   with self.assertRaisesRegex(ValueError,'too many AI tokens'):p.generate(self.root,self.options(),lambda *a:None,threading.Event())
  self.assertTrue(processes[0].closed);self.assertEqual(len(requests),2)
 def test_cancel_closes_owned_process(self):
  child,opener,requests,processes=self.fake_transport();cancel=threading.Event();cancel.set()
  with patch.object(p,'inventory',return_value={'ready':True}),patch.object(p.subprocess,'Popen',child),patch.object(p.urllib.request,'build_opener',return_value=opener):
   with self.assertRaises(Cancelled):p.generate(self.root,self.options(),lambda *a:None,cancel)
  self.assertTrue(processes[0].closed)
 def test_manager_rejects_overlap_and_cancels_only_matching_job(self):
  manager=p.PromptEnhancer(self.root);started=threading.Event();errors=[]
  def generation(root,o,report,cancel):started.set();cancel.wait(5);raise Cancelled('Cancelled')
  def run():
   try:manager.execute('enhance',self.options())
   except Cancelled as error:errors.append(str(error))
  with patch.object(p,'generate',side_effect=generation):
   worker=threading.Thread(target=run);worker.start();self.assertTrue(started.wait(2));snapshot=manager.snapshot();self.assertTrue(snapshot['busy'])
   with self.assertRaises(ValueError):manager.execute('install')
   with self.assertRaises(ValueError):manager.cancel_current('wrong-id')
   manager.cancel_current(snapshot['id']);worker.join(timeout=3)
  self.assertFalse(worker.is_alive());self.assertFalse(manager.snapshot()['busy']);self.assertTrue(manager.done.is_set());self.assertEqual(errors,['Cancelled'])
 def test_manager_result_keeps_original_until_client_applies(self):
  manager=p.PromptEnhancer(self.root);o=self.options()
  with patch.object(p,'generate',return_value='Refined draft'):result=manager.execute('enhance',o)
  self.assertEqual(result['result']['original'],o['prompt']);self.assertEqual(result['result']['prompt'],'Refined draft');self.assertFalse((self.root/'settings.json').exists());manager.close()
import http.server,urllib.request,urllib.error
from test_library_actions import LibraryFixture
from app import Studio,make_handler
class PromptApiTests(LibraryFixture):
 def setUp(self):
  super().setUp()
  with patch('app.gpu_info',return_value={'name':'fixture','vram_gb':16}):self.studio=Studio(self.root)
  self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.studio,lambda:None));self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
 def tearDown(self):self.studio.prompts.close();self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()
 def request(self,path,data=None,auth=True,origin=None):
  headers={'X-Wan-Token':self.studio.token} if auth else {}
  if origin:headers['Origin']=origin
  return urllib.request.urlopen(urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers=headers))
 def test_prompt_routes_require_auth_and_same_origin(self):
  with patch.object(self.studio.prompts,'execute') as run:
   for auth,origin in [(False,None),(True,'https://example.org')]:
    with self.assertRaises(urllib.error.HTTPError):self.request('/api/prompts/enhance',{'prompt':'A landscape'},auth,origin)
   run.assert_not_called()
 def test_cpu_prompt_enhancement_does_not_interrupt_media_engine(self):
  self.studio.state['busy']=True
  result=dict(ok=True,result=dict(prompt='A refined draft',original='A landscape',context='image'))
  with patch.object(self.studio.prompts,'execute',return_value=result) as run,patch.object(self.studio.engine,'stop') as stop:
   with self.request('/api/prompts/enhance',{'prompt':'A landscape','context':'image'}) as r:self.assertEqual(json.load(r),result)
   run.assert_called_once_with('enhance',{'prompt':'A landscape','context':'image'});stop.assert_not_called();self.assertTrue(self.studio.state['busy'])
 def test_new_asset_and_inventory_are_exposed(self):
  with self.request('/studio-prompt-enhancer.js') as r:self.assertEqual(r.read(),(Path(__file__).resolve().parents[1]/'assets/studio-prompt-enhancer.js').read_bytes())
  with self.request('/api/state') as r:state=json.load(r)
  self.assertIn('prompt_enhancer',state);self.assertFalse(state['prompt_enhancer']['ready'])

if __name__=='__main__':unittest.main()
