"""一键打包：PyInstaller onefile → dist/IELTSCoach.exe

打包策略：
- onefile 单文件：用户双击即用，最适合发给同学试玩
- --windowed 无黑窗口；GUI 启动失败会自动弹窗并把错误写入 %APPDATA%\\IELTSCoach\\error.log
- 打包进 exe 的只读资源：data/questions.json、config.example.json（首次运行复制为模板）
- 用户数据（coach.db、录音、config.json）运行后写在 %APPDATA%\\IELTSCoach
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    args = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile", "--windowed",
        "--name", "IELTSCoach",
        "--icon", str(ROOT / "icon.ico"),
        "--add-data", f"{ROOT / 'data' / 'questions.json'};data",
        "--add-data", f"{ROOT / 'config.example.json'};.",
        "--collect-data", "_sounddevice_data",   # PortAudio 动态库
        "--collect-binaries", "ctranslate2",     # faster-whisper 推理引擎
        "--hidden-import", "av",
        "--hidden-import", "edge_tts",
        str(ROOT / "main.py"),
    ]
    print(">> " + " ".join(args[:8]) + " ...")
    subprocess.run(args, cwd=ROOT, check=True)
    exe = ROOT / "dist" / "IELTSCoach.exe"
    print(f"\n打包完成：{exe}（{exe.stat().st_size / 1024 / 1024:.1f} MB）")


if __name__ == "__main__":
    main()
