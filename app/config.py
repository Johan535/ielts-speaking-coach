"""配置加载：读取 config.json。

开发模式：项目根目录 config.json（不存在则报错，提示复制模板）。
打包模式：%APPDATA%\\IELTSCoach\\config.json；首次运行自动复制打包内的
config.example.json 作为模板，然后报错提示用户填 api_key（界面层捕获后弹窗）。
"""
import json
import shutil
from pathlib import Path

from . import paths


def ensure_user_config() -> tuple[Path, bool]:
    """打包模式下确保用户配置文件存在；返回 (路径, 是否新建)。"""
    p = paths.config_path()
    if paths.is_frozen() and not p.exists():
        src = paths.resource_dir() / "config.example.json"
        if src.exists():
            shutil.copyfile(src, p)
            return p, True
    return p, False


def load_config() -> dict:
    p = paths.config_path()
    if not p.exists():
        if paths.is_frozen():
            p, created = ensure_user_config()
            if created:
                raise FileNotFoundError(
                    f"首次运行：已为你生成配置文件\n{p}\n\n"
                    "请用记事本打开它，填入 api_key（DeepSeek 平台申请）后重新启动程序。"
                )
        raise FileNotFoundError(
            f"找不到配置文件 {p}。\n"
            "请复制 config.example.json 为 config.json，并填入你的 API key。"
        )
    with open(p, encoding="utf-8") as f:
        return json.load(f)
