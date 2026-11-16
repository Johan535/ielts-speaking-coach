"""Agent 核心集成测试（无硬件）：验证 记忆注入 / 规划器 / 工具循环 / 评分沉淀

用法：python agent_test.py
成本：约 3-4 次 DeepSeek API 调用（几分钱）
"""
import sys
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.agent import ExaminerAgent
from app.memory import AgentMemory
from app.planner import Planner
from app.question_bank import QuestionBank
from app.tools import build_tool_funcs

PASS, FAIL = 0, 0


def check(name: str, cond: bool, extra: str = ""):
    global PASS, FAIL
    tag = "PASS" if cond else "FAIL"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"[{tag}] {name}" + (f" -- {extra}" if extra else ""))


def main():
    cfg = load_config()
    memory = AgentMemory(":memory:")
    bank = QuestionBank()

    # ---- 1. 预置记忆（模拟第二次使用） ----
    memory.record_weakness("I very like -> I really like", "grammar", "Hometown")
    memory.save_corpus("go the extra mile", "加倍努力", source="feedback")
    memory.save_corpus("bustling", "热闹的", source="feedback")
    check("预置弱点", memory.stats()["weaknesses"] == 1)
    check("预置语料", memory.stats()["corpus"] == 2)

    # ---- 2. 记忆画像 ----
    profile = memory.profile_text()
    check("画像包含弱点", "very like" in profile)
    check("画像包含到期复习", "bustling" in profile or "extra mile" in profile)

    # ---- 3. 规划器 ----
    planner = Planner(memory)
    plan = planner.daily_task(bank)
    check("规划器返回话题", bool(plan["topic"]))
    check("规划器返回复习清单", len(plan["due_reviews"]) == 2)
    print(f"      [规划] 话题={plan['topic']} | 理由={plan['reason']}")

    # ---- 4. Agent 循环 ----
    topic = plan["topic"]
    first_q = bank.next_question(topic)
    used = [first_q]
    ctx = {"memory": memory, "bank": bank, "used": used, "topic": topic,
           "tool_funcs": build_tool_funcs({"memory": memory, "bank": bank, "used": used, "topic": topic})}
    agent = ExaminerAgent(cfg, memory, ctx)
    session_id = memory.start_session(topic)

    opening = agent.next_move(
        f"Interview topic: {topic}. Start the interview now. Ask your first question. "
        f"Suggested opening: \"{first_q}\"")
    check("开场白非空", bool(opening.strip()))
    print(f"      [考官] {opening}")

    weak_before = memory.stats()["weaknesses"]
    corpus_before = memory.stats()["corpus"]

    # 故意用错 very like，且用了一个好表达：考官可能静默记录（软性检查，不计失败）
    answer = ("I am from Beijing, a bustling city. I very like it because "
              "there are many delicious foods and friendly people.")
    reply = agent.next_move(answer)
    check("追问/回复非空", bool(reply.strip()))
    print(f"      [考官] {reply}")
    stats = memory.stats()
    if stats["weaknesses"] > weak_before or stats["corpus"] > corpus_before:
        print(f"      [WARN-OK] 对话中工具已写入记忆 weak {weak_before}->{stats['weaknesses']}, "
              f"corpus {corpus_before}->{stats['corpus']}")
    else:
        print(f"      [WARN] 本轮考官未调用记录工具（模型自主判断，可接受） "
              f"weak {weak_before}->{stats['weaknesses']}, corpus {corpus_before}->{stats['corpus']}")

    # ---- 确定性工具循环验证：考生直接问生词，考官必须调用 lookup_word ----
    reply = agent.next_move("Excuse me, I don't know a word. What does 'scrumptious' mean?")
    check("查词后回复非空", bool(reply.strip()))
    print(f"      [考官] {reply}")
    tool_msgs = [m for m in agent.messages if m.get("role") == "tool"]
    check("工具循环已执行（存在 tool 结果消息）", len(tool_msgs) > 0,
          f"tool messages: {len(tool_msgs)}")
    lookup_calls = [m for m in tool_msgs if "found" in str(m.get("content", ""))]
    check("lookup_word 已调用", len(lookup_calls) > 0)

    # ---- 5. 评分与沉淀 ----
    fb = agent.feedback()
    for k in ("fluency", "vocabulary", "grammar", "pronunciation", "scores_reason", "errors", "new_expressions"):
        check(f"评分字段 {k} 存在", k in fb)
    memory.finish_session(session_id, 2, fb)
    stats = memory.stats()
    check("评分已入库", stats["sessions"] == 1)
    check("打卡已记录", stats["checkins"] == 1)

    # ---- 6. 二次画像：这次记忆应该更丰富 ----
    profile2 = memory.profile_text()
    check("二次画像包含最近得分", "Last session" in profile2)
    print(f"      [画像] {profile2[:120]}...")

    memory.close()
    print("\n" + "=" * 40)
    print(f"结果：{PASS} 通过 / {FAIL} 失败")
    sys.exit(0 if FAIL == 0 else 1)


if __name__ == "__main__":
    main()
