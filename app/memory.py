"""记忆层：考官记得你 —— 弱点档案、个人语料库、历史得分、打卡

对外只暴露 AgentMemory 一个类；所有读写走 SQLite（app/db.py）。
"""
from datetime import date, datetime, timedelta

from .db import connect


def _today() -> str:
    return date.today().isoformat()


class AgentMemory:
    def __init__(self, db_path=None):
        self.conn = connect(db_path)

    # ---------------- 画像：注入到考官系统提示 ----------------

    def get_profile(self, limit_weak: int = 5, limit_corpus: int = 5) -> dict:
        """考官的长期记忆：未解决弱点、最近得分、到期复习表达。"""
        cur = self.conn.execute(
            "SELECT text, category, topic, count FROM weaknesses "
            "WHERE resolved=0 ORDER BY count DESC, last_seen DESC LIMIT ?",
            (limit_weak,))
        weaknesses = [dict(r) for r in cur.fetchall()]

        cur = self.conn.execute(
            "SELECT s.topic, s.date, sc.fluency, sc.vocabulary, sc.grammar, sc.pronunciation "
            "FROM scores sc JOIN sessions s ON s.id = sc.session_id "
            "ORDER BY sc.id DESC LIMIT 3")
        recent_scores = [dict(r) for r in cur.fetchall()]

        cur = self.conn.execute(
            "SELECT id, expression, translation, times_reviewed FROM corpus "
            "WHERE mastered=0 AND (next_review_at IS NULL OR next_review_at <= ?) "
            "ORDER BY times_reviewed ASC LIMIT ?",
            (_today(), limit_corpus))
        due_reviews = [dict(r) for r in cur.fetchall()]

        return {"weaknesses": weaknesses, "recent_scores": recent_scores, "due_reviews": due_reviews}

    def profile_text(self, limit_weak: int = 5, limit_corpus: int = 5) -> str:
        """把画像转成给考官的英文提示段落；首次使用（无记忆）返回空串。"""
        p = self.get_profile(limit_weak, limit_corpus)
        parts = []
        if p["weaknesses"]:
            w = "; ".join(
                f"{x['text']} ({x['category']}, topic {x['topic']}, seen {x['count']}x)"
                for x in p["weaknesses"])
            parts.append("The candidate's known weaknesses: " + w)
        if p["recent_scores"]:
            s = p["recent_scores"][0]
            parts.append(
                f"Last session ({s['date']}, topic {s['topic']}): fluency {s['fluency']}, "
                f"vocabulary {s['vocabulary']}, grammar {s['grammar']}, pronunciation {s['pronunciation']}.")
        if p["due_reviews"]:
            r = "; ".join(f"{x['expression']} ({x['translation']})" for x in p["due_reviews"])
            parts.append("Expressions the candidate learned and should review: " + r)
        return "\n".join(parts)

    # ---------------- 会话生命周期 ----------------

    def start_session(self, topic: str) -> int:
        cur = self.conn.execute("INSERT INTO sessions (date, topic) VALUES (?, ?)", (_today(), topic))
        self.conn.commit()
        return cur.lastrowid

    def finish_session(self, session_id: int, rounds: int, feedback: dict) -> None:
        """练习结束：保存四项评分、把纠错/新表达沉淀进档案、打卡。"""
        fb = feedback or {}
        self.conn.execute("UPDATE sessions SET rounds=? WHERE id=?", (rounds, session_id))
        self.conn.execute(
            "INSERT INTO scores (session_id, fluency, vocabulary, grammar, pronunciation) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, fb.get("fluency"), fb.get("vocabulary"),
             fb.get("grammar"), fb.get("pronunciation")))
        for e in (fb.get("errors") or []):
            text = f"{e.get('wrong', '')} -> {e.get('right', '')} ({e.get('why', '')})"
            self.record_weakness(text, category="grammar")
        for n in (fb.get("new_expressions") or []):
            expr, _, trans = n.partition("(")
            self.save_corpus(expr.strip(), trans.rstrip(")").strip() or "", source="feedback")
        self.conn.execute(
            "INSERT INTO checkins (date, session_id, completed) VALUES (?, ?, 1) "
            "ON CONFLICT(date) DO UPDATE SET session_id=excluded.session_id, completed=1",
            (_today(), session_id))
        self.conn.commit()

    # ---------------- 工具写操作（考官对话中静默调用） ----------------

    def save_corpus(self, expression: str, translation: str = "", source: str = "dialogue") -> int:
        """好表达入库，返回 corpus id；同表达只存一条、更新翻译。"""
        self.conn.execute(
            "INSERT INTO corpus (expression, translation, source) VALUES (?, ?, ?) "
            "ON CONFLICT(expression) DO UPDATE SET translation=excluded.translation",
            (expression, translation, source))
        self.conn.commit()
        row = self.conn.execute("SELECT id FROM corpus WHERE expression=?", (expression,)).fetchone()
        return row["id"]

    def record_weakness(self, text: str, category: str = "general", topic: str = "") -> None:
        """错句入档案；同一条错句重复出现则计数 +1。"""
        self.conn.execute(
            "INSERT INTO weaknesses (text, category, topic, last_seen) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(text) DO UPDATE SET count=count+1, last_seen=excluded.last_seen, "
            "category=excluded.category, resolved=0",
            (text, category, topic, _today()))
        self.conn.commit()

    def mark_reviewed(self, corpus_id: int) -> None:
        """间隔重复：复习一次后 1 天 → 3 天 → 7 天 → 14 天后再出现。"""
        intervals = [1, 3, 7, 14]
        row = self.conn.execute("SELECT times_reviewed FROM corpus WHERE id=?", (corpus_id,)).fetchone()
        if not row:
            return
        days = intervals[min(row["times_reviewed"], len(intervals) - 1)]
        nxt = (datetime.now() + timedelta(days=days)).date().isoformat()
        self.conn.execute(
            "UPDATE corpus SET times_reviewed=times_reviewed+1, next_review_at=? WHERE id=?",
            (nxt, corpus_id))
        self.conn.commit()

    # ---------------- 统计（给界面/日记用） ----------------

    def stats(self) -> dict:
        return {
            "sessions": self.conn.execute("SELECT COUNT(*) AS c FROM sessions").fetchone()["c"],
            "checkins": self.conn.execute("SELECT COUNT(*) AS c FROM checkins WHERE completed=1").fetchone()["c"],
            "weaknesses": self.conn.execute("SELECT COUNT(*) AS c FROM weaknesses WHERE resolved=0").fetchone()["c"],
            "corpus": self.conn.execute("SELECT COUNT(*) AS c FROM corpus").fetchone()["c"],
        }

    def close(self):
        self.conn.close()
