"""路径解析：开发模式与 PyInstaller 打包模式共用同一套接口。

- 开发模式（python main.py）：一切照旧——资源/数据/配置都在项目目录。
- 打包模式（IELTSCoach.exe）：只读资源（题库、配置模板）从 PyInstaller 解包目录
  （sys._MEIPASS）读取；用户数据（数据库、录音、配置文件）写到
  %APPDATA%\\IELTSCoach，避免污染安装目录，也方便卸载。
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "IELTSCoach"


def is_frozen() -> bool:
    """是否为 PyInstaller 打包后的运行环境。"""
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """只读资源目录（题库、配置模板）。打包后指向解包临时目录。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS"))
    return PROJECT_ROOT


def user_data_dir() -> Path:
    """可写数据目录。打包后为 %APPDATA%\\IELTSCoach，开发模式为项目目录。"""
    if is_frozen():
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        d = base / APP_NAME
    else:
        d = PROJECT_ROOT
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    if is_frozen():
        return user_data_dir() / "coach.db"
    return PROJECT_ROOT / "data" / "coach.db"


def recordings_dir() -> Path:
    d = user_data_dir() / "recordings" if is_frozen() else PROJECT_ROOT / "recordings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    if is_frozen():
        return user_data_dir() / "config.json"
    return PROJECT_ROOT / "config.json"
