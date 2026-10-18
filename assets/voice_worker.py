"""One isolated HTTP request. No model, GPU, cloud service or runtime imports."""
import json,sys,urllib.request,urllib.error
from pathlib import Path

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Voice redirects are not allowed.')

def main():
    job=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'));target=Path(job['target'])
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    request=urllib.request.Request(job['url'],data=json.dumps(job['payload']).encode(),headers={'Content-Type':'application/json','Accept':'audio/wav'})
    try:
        with opener.open(request,timeout=1800) as response,target.open('wb') as output:
            size=0
            while chunk:=response.read(65536):
                size+=len(chunk)
                if size>60*1024**2:raise ValueError('Speech response exceeds 60 MB. Use a shorter script.')
                output.write(chunk)
        header=target.read_bytes()[:12]
        if header[:4]!=b'RIFF' or header[8:12]!=b'WAVE':raise ValueError('The voice server did not return WAV audio.')
    except urllib.error.HTTPError as error:raise RuntimeError(str(error)+' '+error.read(2000).decode(errors='replace')) from None

if __name__=='__main__':main()
