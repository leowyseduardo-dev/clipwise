"""Anonymous speaker estimates from Whisper timings and local TitaNet embeddings."""

from functools import lru_cache
import logging
import os
from pathlib import Path
import numpy as np
from .config import settings

logger = logging.getLogger(__name__)


def model_path():
    from .config import BASE_DIR, RESOURCE_DIR

    candidates = [
        os.getenv("CLIPFORGE_SPEAKER_MODEL"),
        settings.data_dir / "models" / "titanet-small.onnx",
        RESOURCE_DIR / "models" / "titanet-small.onnx",
        BASE_DIR / "models" / "titanet-small.onnx",
        BASE_DIR.parent / "tools" / "models" / "titanet-small.onnx",
    ]
    return next((Path(p) for p in candidates if p and Path(p).is_file()), None)


@lru_cache(maxsize=1)
def mel_filters():
    # HTK-equivalent mel triangles at 16 kHz, sampled on a 512-point DFT.
    f = np.linspace(0, 8000, 257)
    hz = 700 * (np.exp(np.linspace(0, np.log1p(8000 / 700), 82)) - 1)
    return np.maximum(
        0,
        np.minimum(
            (f - hz[:-2, None]) / (hz[1:-1] - hz[:-2])[:, None],
            (hz[2:, None] - f) / (hz[2:] - hz[1:-1])[:, None],
        ),
    ).astype("float32")


def features(samples):
    x = np.pad(samples.astype("float32"), 256, mode="reflect")
    x[1:] -= 0.97 * x[:-1].copy()
    frames = np.lib.stride_tricks.sliding_window_view(x, 512)[::160]
    window = np.pad(np.hanning(401)[:-1], (56, 56))
    power = np.abs(np.fft.rfft(frames * window)) ** 2
    mel = np.log(np.maximum(mel_filters() @ power.T, 1e-9))
    return (
        (mel - mel.mean(axis=1, keepdims=True))
        / (mel.std(axis=1, keepdims=True) + 1e-5)
    ).astype("float32")


def speaker_turns(audio, segments):
    path = model_path()
    if not path or not segments:
        return []
    import onnxruntime as ort
    import soundfile as sf

    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(
        str(path), sess_options=options, providers=["CPUExecutionProvider"]
    )
    clusters = []
    turns = []
    with sf.SoundFile(audio) as stream:
        if stream.samplerate != 16000 or stream.channels != 1:
            return []
        for segment in segments:
            start, end = float(segment["start"]), float(segment["end"])
            if end - start < 0.8:
                continue
            # Analyze the central speech of each ASR segment. Keep only anonymous
            # turn labels; embeddings are discarded when the job finishes.
            duration = min(end - start, 3.0)
            offset = start + (end - start - duration) / 2
            stream.seek(min(len(stream), round(offset * 16000)))
            samples = stream.read(round(duration * 16000), dtype="float32")
            if len(samples) < 12800 or np.sqrt(np.mean(samples**2)) < 0.002:
                continue
            mel = features(samples)
            vector = session.run(
                ["embs"],
                {
                    "audio_signal": mel[None],
                    "length": np.array([mel.shape[1]], dtype="int64"),
                },
            )[0][0]
            vector = vector / (np.linalg.norm(vector) + 1e-9)
            similarities = [float(np.dot(vector, v)) for v in clusters]
            if not clusters or (max(similarities) < 0.52 and len(clusters) < 12):
                speaker = len(clusters)
                clusters.append(vector)
            else:
                speaker = int(np.argmax(similarities))
                center = 0.86 * clusters[speaker] + 0.14 * vector
                clusters[speaker] = center / (np.linalg.norm(center) + 1e-9)
            turns.append({"start": start, "end": end, "voice": speaker + 1})
    return turns
