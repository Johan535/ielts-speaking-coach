"""配置加载：读取项目根目录下的 config.json"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    p = ROOT / "config.json"
    if not p.exists():
        raise FileNotFoundError(
            f"找不到配置文件 {p}。\n"
            "请复制 config.example.json 为 config.json，并填入你的 API key。"
        )
    with open(p, encoding="utf-8") as f:
        return json.load(f)
