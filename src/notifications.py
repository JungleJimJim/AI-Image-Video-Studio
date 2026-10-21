"""Native completion audio, independent of browser autoplay and window focus."""
from common import resource


def play_completion_ping():
    try:
        import winsound
        sound=resource('completion-ping.wav')
        if not sound.is_file():return False
        winsound.PlaySound(str(sound),winsound.SND_FILENAME|winsound.SND_ASYNC|winsound.SND_NODEFAULT)
        return True
    except (ImportError,OSError,RuntimeError):
        # An unavailable audio device must never turn a completed render into a failure.
        return False
