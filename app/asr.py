"""语音识别：faster-whisper（本地免费）

首次使用需下载模型（base 约 145MB）。国内网络 HuggingFace 直连常失败，
自动回退到镜像 https://hf-mirror.com；打包版模型缓存放在应用数据目录。
"""
import os
from pathlib import Path

from . import paths

_model = None
_current_name = None

_MIRROR = "https://hf-mirror.com"


def get_model(model_name: str = "base", device: str = "cpu"):
    global _model, _current_name
    if _model is None or _current_name != model_name:
        from faster_whisper import WhisperModel

        # 打包版：模型缓存归到应用数据目录（%APPDATA%\IELTSCoach\models），
        # 卸载即清理；开发版用默认缓存目录
        if paths.is_frozen():
            os.environ.setdefault("HF_HOME", str(paths.user_data_dir() / "models"))

        print(f"[模型] 正在加载语音识别模型 '{model_name}'（首次运行需下载约 145MB，请稍候）……")
        try:
            _model = WhisperModel(model_name, device=device, compute_type="int8")
        except Exception:
            print(f"[模型] HuggingFace 直连失败，自动切换国内镜像 {_MIRROR} 重试……")
            os.environ["HF_ENDPOINT"] = _MIRROR
            try:
                _model = WhisperModel(model_name, device=device, compute_type="int8")
            except Exception as e:
                raise RuntimeError(
                    "语音模型下载失败（直连与国内镜像均不可用）。\n"
                    f"请检查网络后重试；或手动设置环境变量 HF_ENDPOINT={_MIRROR}。\n"
                    f"原始错误：{e}"
                ) from e
        _current_name = model_name
    return _model


def transcribe(path: Path, model_name: str = "base", device: str = "cpu", language: str = "en") -> str:
    model = get_model(model_name, device)
    segments, info = model.transcribe(str(path), language=language, beam_size=1)
    text = " ".join(s.text.strip() for s in segments).strip()
    return text
