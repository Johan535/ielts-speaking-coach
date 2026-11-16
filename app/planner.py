"""每日规划器：弱项话题优先 + 语料到期复习

规则引擎（不用 LLM，省钱且行为可预测）：
    1. 有近 7 天评分记录 → 选平均分最低的话题（补短板）
    2. 无任何记录 → 随机热身话题
    3. 附带到期复习的表达清单（间隔重复）
"""
from datetime import date

from .question_bank import QuestionBank


class Planner:
    def __init__(self, memory):
        self.memory = memory

    def _topic_stats(self) -> dict:
        """最近 7 天各话题的平均总分与练习次数。"""
        rows = self.memory.conn.execute(
            "SELECT s.topic, "
            "AVG((sc.fluency + sc.vocabulary + sc.grammar + sc.pronunciation) / 4.0) AS avg_score, "
            "COUNT(*) AS cnt "
            "FROM scores sc JOIN sessions s ON s.id = sc.session_id "
            "WHERE s.date >= date('now', 'localtime', '-7 days') "
            "GROUP BY s.topic").fetchall()
        return {r["topic"]: {"avg_score": r["avg_score"], "cnt": r["cnt"]} for r in rows}

    def daily_task(self, bank: QuestionBank) -> dict:
        """返回今日任务：话题 + 选择理由 + 到期复习清单。"""
        stats = self._topic_stats()
        due = self.memory.conn.execute(
            "SELECT id, expression, translation, times_reviewed FROM corpus "
            "WHERE mastered=0 AND (next_review_at IS NULL OR next_review_at <= ?) "
            "ORDER BY times_reviewed ASC LIMIT 5",
            (date.today().isoformat(),)).fetchall()

        if stats:
            weakest = min(stats.items(), key=lambda kv: kv[1]["avg_score"])
            topic = weakest[0]
            reason = (f"最近 7 天你在「{topic}」平均分最低"
                      f"（{weakest[1]['avg_score']:.1f} 分，练过 {weakest[1]['cnt']} 次），今天优先补短板。")
        else:
            topic = bank.random_topic()["name"]
            reason = "今天是你第一次练习，先从一个常见话题热身。"

        return {
            "topic": topic,
            "reason": reason,
            "due_reviews": [dict(r) for r in due],
        }
