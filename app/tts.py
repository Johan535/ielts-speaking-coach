"""语音合成与播放：edge-tts（免费）+ pygame 播放 mp3"""
import asyncio
import time
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


def cleanup_old_tts(out_dir: Path, keep: Path | None = None) -> int:
    """删除历史 TTS 文件（保留 keep 指定的当前文件）；返回删除数量。
    Windows 上 pygame 会一直占用上次加载的 mp3，删除失败静默忽略，下次再清。"""
    removed = 0
    for f in out_dir.glob("tts_*.mp3"):
        if keep is not None and f == keep:
            continue
        try:
            f.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def speak(text: str, out_dir: Path, voice: str = "en-GB-SoniaNeural") -> None:
    """合成并播放，阻塞直到播放完毕"""
    out_dir.mkdir(parents=True, exist_ok=True)
    # 每次用唯一文件名：pygame 在 Windows 上会一直占用已加载的 mp3，
    # 固定文件名会导致下一句合成时 Permission denied（曾实测触发）
    path = out_dir / f"tts_{int(time.time() * 1000)}.mp3"
    asyncio.run(synthesize(text, path, voice))
    import pygame

    _ensure_pygame()
    try:
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
    finally:
        try:
            pygame.mixer.music.unload()  # 立刻释放文件句柄
        except Exception:
            pass
        cleanup_old_tts(out_dir, keep=path)


def speak_or_print(text: str, out_dir: Path, voice: str = "en-GB-SoniaNeural") -> None:
    """先打印文字，再尝试朗读；朗读失败时静默降级为纯文字"""
    print(f"\n[考官] {text}")
    try:
        speak(text, out_dir, voice=voice)
    except Exception as e:
        print(f"（语音合成失败，已退化为纯文字模式：{e}）")
