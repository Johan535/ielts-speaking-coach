"""冒烟测试：TTS 合成 → ffmpeg 转 wav → ASR 转写 → LLM 对话 → 评分 JSON
不依赖麦克风/扬声器，用于验证整条 AI 链路。"""
import asyncio
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app import asr, tts
from app.config import load_config
from app.llm import Examiner

cfg = load_config()
out_dir = ROOT / "recordings"
out_dir.mkdir(exist_ok=True)
mp3 = out_dir / "smoke.mp3"
wav = out_dir / "smoke.wav"

# 1. TTS 合成
print("[1/4] TTS 合成中……")
asyncio.run(tts.synthesize(
    "Hello! Do you work, or are you a student?",
    mp3, cfg.get("tts_voice", "en-GB-SoniaNeural")))
print("    mp3 大小:", mp3.stat().st_size, "bytes")

# 2. ffmpeg 转 16k 单声道 wav
subprocess.run(
    ["ffmpeg", "-y", "-i", str(mp3), "-ar", "16000", "-ac", "1", str(wav)],
    check=True, capture_output=True)
print("[2/4] 已转为 16k 单声道 wav")

# 3. ASR 转写（首次运行会下载 whisper 模型）
print("[3/4] ASR 转写中（首次运行需下载模型，请稍候）……")
text = asr.transcribe(wav, cfg.get("asr_model", "base"), cfg.get("device", "cpu"))
print("    转写结果:", repr(text))

# 4. LLM 对话 + 评分（用真实考生回答验证对话流）
print("[4/4] 测试 DeepSeek 考官……")
ex = Examiner(cfg)
reply = ex.next_move("I am a student, and I study computer science.", stuck=False)
print("    考官回复:", reply)
fb = ex.feedback()
print("    评分 JSON:", json.dumps(fb, ensure_ascii=False, indent=2))
print("\nSMOKE TEST PASSED")
