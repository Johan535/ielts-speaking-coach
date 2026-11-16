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


class Recorder:
    """GUI 用录音器：start() 开始，stop() 结束，save(path) 写 wav 并返回秒数。

    与 record_to_wav 的区别：不阻塞等待控制台输入，由界面线程决定何时停止。
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sample_rate = sample_rate
        self._frames: list = []
        self._stream = None

    def _callback(self, indata, frame_count, time_info, status):
        self._frames.append(indata.copy())

    def start(self):
        self._stream = sd.InputStream(
            samplerate=self.sample_rate, channels=1, dtype="float32", callback=self._callback
        )
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def save(self, path: Path) -> float:
        """把录到的音频写成 wav；返回时长（秒）。"""
        if self._frames:
            data = np.concatenate(self._frames)
        else:
            data = np.zeros((0,), dtype=np.float32)
        pcm = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)

        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self.sample_rate)
            w.writeframes(pcm.tobytes())
        return len(data) / self.sample_rate
