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

    def topic_by_name(self, name: str) -> dict | None:
        for t in self.topics:
            if t["name"] == name:
                return t
        return None

    def next_question(self, topic_name: str, exclude: list | None = None) -> str | None:
        """取该话题的下一题，优先避开 exclude 中已用过的题目。"""
        t = self.topic_by_name(topic_name)
        if t is None:
            return None
        pool = [q for q in t["questions"] if q not in (exclude or [])]
        if not pool:  # 题目用完则允许重复（兜底）
            pool = t["questions"]
        return random.choice(pool)
