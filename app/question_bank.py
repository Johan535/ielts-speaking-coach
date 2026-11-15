"""题库：加载 data/questions.json，随机选话题/题目"""
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class QuestionBank:
    def __init__(self, path: Path | None = None):
        path = path or ROOT / "data" / "questions.json"
        with open(path, encoding="utf-8") as f:
            self.data = json.load(f)
        self.topics = self.data["topics"]

    def random_topic(self) -> dict:
        return random.choice(self.topics)

    def random_question(self, topic: dict) -> str:
        return random.choice(topic["questions"])
