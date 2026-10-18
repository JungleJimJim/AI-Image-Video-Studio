"""Decode local recordings to bounded mono WAV. Contains no AI inference."""
import json
from pathlib import Path
import sys
import wave


def decode(request):
    import av
    source, target = Path(request['source']), Path(request['target'])
    target.parent.mkdir(parents=True,exist_ok=True)
    maximum = 600 * 48000
    samples = 0
    try:
        with av.open(str(source)) as container, wave.open(str(target),'wb') as output:
            if not container.streams.audio:
                raise ValueError('The file contains no audio. Choose a WAV, MP3, M4A, OGG or FLAC recording.')
            output.setparams((1,2,48000,0,'NONE','not compressed'))
            converter=av.AudioResampler(format='s16',layout='mono',rate=48000)
            for frame in container.decode(audio=0):
                for converted in converter.resample(frame):
                    samples += converted.samples
                    if samples>maximum:
                        raise ValueError('Choose a recording no longer than ten minutes.')
                    output.writeframesraw(converted.to_ndarray().tobytes())
            for converted in converter.resample(None):
                samples += converted.samples
                if samples>maximum:raise ValueError('Choose a recording no longer than ten minutes.')
                output.writeframesraw(converted.to_ndarray().tobytes())
        if samples<24000:
            raise ValueError('Choose a recording at least half a second long.')
        return dict(duration=round(samples/48000,3),sample_rate=48000,channels=1)
    except Exception:
        target.unlink(missing_ok=True)
        raise


if __name__=='__main__':
    print(json.dumps(decode(json.load(sys.stdin))))
