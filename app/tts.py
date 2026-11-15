"""语音合成与播放：edge-tts（免费）+ pygame 播放 mp3"""
import asyncio
from pathlib import Path

import edge_tts

_initialized = False


def _ensure_pygame():
    global _initialized
    if not _initialized:
        import pygame

        pygame.mixer.init()
        _initialized = True


async def synthesize(text: str, out_path: Path, voice: str) -> None:
    comm = edge_tts.Communicate(text, voice)
    await comm.save(str(out_path))


def speak(text: str, out_dir: Path, voice: str = "en-GB-SoniaNeural") -> None:
    """合成并播放，阻塞直到播放完毕"""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "tts_last.mp3"
    asyncio.run(synthesize(text, path, voice))
    import pygame

    _ensure_pygame()
    pygame.mixer.music.load(str(path))
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(100)


def speak_or_print(text: str, out_dir: Path, voice: str = "en-GB-SoniaNeural") -> None:
    """先打印文字，再尝试朗读；朗读失败时静默降级为纯文字"""
    print(f"\n[考官] {text}")
    try:
        speak(text, out_dir, voice=voice)
    except Exception as e:
        print(f"（语音合成失败，已退化为纯文字模式：{e}）")
