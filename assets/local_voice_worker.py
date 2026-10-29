"""One local speech job in a provider-specific package directory."""
import json,os,re,sys
from pathlib import Path

def chunks(text,limit=400):
    parts=[];current=''
    for word in text.split():
        if current and len(current)+1+len(word)>limit:parts.append(current);current=''
        # Avoid sending pathological single-token text beyond the model context.
        for start in range(0,len(word),limit):
            piece=word[start:start+limit]
            if start and current:parts.append(current);current=''
            current=(current+' '+piece).strip()
    if current:parts.append(current)
    return parts

def main():
    job=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    # All provider dependencies live here; do not discover incompatible optional
    # packages (e.g. torchvision) from ComfyUI's base environment.
    sys.path[:]=[p for p in sys.path if not any(part in ('site-packages','dist-packages') for part in Path(p).parts)]
    sys.path.insert(0,job['packages'])
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    if job.get('probe'):
        if job['model']=='kokoro':import kokoro_onnx,soundfile
        else:
            import torch
            from qwen_tts import Qwen3TTSModel
            if not torch.version.cuda:raise RuntimeError('Qwen requires the managed CUDA-enabled PyTorch build (also supports CPU mode).')
            print('QWEN_TORCH_CUDA_BUILD '+str(torch.version.cuda),flush=True)
        print('LOCAL_VOICE_IMPORT_PASS',flush=True);return
    import numpy as np
    import soundfile as sf
    o=job['options'];weights=Path(job['weights']);audio=[]
    if job['model']=='kokoro':
        import onnxruntime as ort
        from kokoro_onnx import Kokoro
        settings=ort.SessionOptions();settings.intra_op_num_threads=min(4,os.cpu_count() or 2)
        session=ort.InferenceSession(str(weights/'kokoro-v1.0.onnx'),sess_options=settings,providers=['CPUExecutionProvider'])
        engine=Kokoro.from_session(session,str(weights/'voices-v1.0.bin'))
        language='en-gb' if o['voice'].startswith('b') else 'en-us'
        for text in chunks(o['text']):
            value,sample_rate=engine.create(text,voice=o['voice'],speed=o['speed'],lang=language);audio.append(np.asarray(value,dtype=np.float32))
    else:
        import torch
        from qwen_tts import Qwen3TTSModel
        if o['device']=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA is unavailable. Select CPU mode, or check the NVIDIA driver.')
        torch.manual_seed(int(o['seed']))
        model=Qwen3TTSModel.from_pretrained(str(weights),device_map='cuda:0' if o['device']=='cuda' else 'cpu',dtype=torch.float16 if o['device']=='cuda' else torch.float32,attn_implementation='sdpa',local_files_only=True)
        reference,sr=sf.read(job['reference'],dtype='float32')
        if reference.ndim>1:reference=reference.mean(axis=1)
        prompt=model.create_voice_clone_prompt(ref_audio=(reference,sr),ref_text=o.get('transcript') or None,x_vector_only_mode=not bool(o.get('transcript')))
        for text in chunks(o['text'],250):
            wavs,sample_rate=model.generate_voice_clone(text=text,language=o['language'],voice_clone_prompt=prompt,temperature=o['temperature'],top_p=o['top_p'],max_new_tokens=2048)
            audio.append(np.asarray(wavs[0],dtype=np.float32))
    if not audio:raise ValueError('No speech was generated.')
    result=np.concatenate(audio)
    if not np.isfinite(result).all() or len(result)>sample_rate*600:raise ValueError('Use a shorter speech script (under ten minutes).')
    sf.write(job['target'],np.clip(result,-1,1),sample_rate,subtype='PCM_16')

if __name__=='__main__':main()
