import librosa
import numpy as np


def detect_beats(audio_path: str) -> tuple[float, list[float]]:
    """Return (tempo_bpm, beat_timestamps_seconds) for an audio file."""
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    # librosa.beat.beat_track(y=y, sr=sr) silently returns empty results on
    # some inputs (librosa 0.11); computing the onset envelope ourselves
    # and passing it explicitly avoids that failure mode.
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    tempo_value = float(tempo) if np.isscalar(tempo) else float(tempo[0])
    return tempo_value, beat_times.tolist()
