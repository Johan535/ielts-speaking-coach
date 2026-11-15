"""语音识别：faster-whisper（本地免费）

首次使用会自动从 HuggingFace 下载模型；国内网络建议：
  $env:HF_ENDPOINT = "https://hf-mirror.com"
"""
from pathlib import Path

_model = None
_current_name = None


def get_model(model_name: str = "base", device: str = "cpu"):
    global _model, _current_name
    if _model is None or _current_name != model_name:
        print(f"[模型] 正在加载语音识别模型 '{model_name}'（首次运行需下载约 150MB，请稍候）……")
        from faster_whisper import WhisperModel

        _model = WhisperModel(model_name, device=device, compute_type="int8")
        _current_name = model_name
    return _model


def transcribe(path: Path, model_name: str = "base", device: str = "cpu", language: str = "en") -> str:
    model = get_model(model_name, device)
    segments, info = model.transcribe(str(path), language=language, beam_size=1)
    text = " ".join(s.text.strip() for s in segments).strip()
    return text
