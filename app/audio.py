"""录音：sounddevice 后台录音，回车停止"""
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


def record_to_wav(path: Path, sample_rate: int = SAMPLE_RATE) -> float:
    """开始录音，直到用户在控制台按回车；返回录音时长（秒）。"""
    stop = threading.Event()
    frames: list = []

    def callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    stream = sd.InputStream(
        samplerate=sample_rate, channels=1, dtype="float32", callback=callback
    )
    stream.start()
    input("（录音进行中……）按回车结束录音 > ")
    stream.stop()
    stream.close()

    if frames:
        data = np.concatenate(frames)
    else:
        data = np.zeros((0,), dtype=np.float32)
    pcm = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)

    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return len(data) / sample_rate
