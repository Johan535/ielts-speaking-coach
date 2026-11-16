"""雅思口语教练 - M2a 命令行版（Agent 核心）

流程：规划器选今日话题(弱项优先) -> 考官(带记忆+工具)开场 -> 录音回答 -> Agent 追问/换题
     卡住输入 h 求助 -> 练习结束自动评分 -> 评分沉淀进弱点档案与语料库 -> 打卡
"""
import sys
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 避免中文乱码
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
from app import audio, asr, tts

RECORD_DIR = ROOT / "recordings"


def pretty_feedback(fb):
    line = "=" * 50
    print("\n" + line)
    print("  [评分] 雅思四项评分（模拟，仅供参考）")
    print(line)
    print(f"  流利度 Fluency       : {fb.get('fluency', '?')}")
    print(f"  词汇   Vocabulary    : {fb.get('vocabulary', '?')}")
    print(f"  语法   Grammar       : {fb.get('grammar', '?')}")
    print(f"  发音   Pronunciation : {fb.get('pronunciation', '?')}")
    if fb.get("scores_reason"):
        print(f"\n  [点评] {fb['scores_reason']}")
    errs = fb.get("errors") or []
    if errs:
        print("\n  [纠错] 你说错的句子：")
        for e in errs:
            print(f"    x {e.get('wrong', '')}")
            print(f"      -> {e.get('right', '')}（{e.get('why', '')}）")
    news = fb.get("new_expressions") or []
    if news:
        print("\n  [积累] 值得记下来的表达：")
        for n in news:
            print(f"    - {n}")
    if fb.get("encouragement"):
        print(f"\n  [鼓励] {fb['encouragement']}")
    print(line)


def show_memory_growth(memory: AgentMemory):
    stats = memory.stats()
    print("\n[档案] 教练已经记住了你的：")
    print(f"  - 弱点记录 {stats['weaknesses']} 条 | 语料库表达 {stats['corpus']} 条")
    print(f"  - 累计练习 {stats['sessions']} 次 | 打卡 {stats['checkins']} 天")


def main():
    cfg = load_config()
    RECORD_DIR.mkdir(exist_ok=True)
    memory = AgentMemory()
    planner = Planner(memory)
    bank = QuestionBank()

    print("=" * 50)
    print("  雅思口语教练 v0.2（Agent 版 · 命令行）")
    print("  考官记得你、有工具、会自主规划今天练什么")
    print("=" * 50 + "\n")

    # ---- 1. 规划器：今天练什么 ----
    plan = planner.daily_task(bank)
    topic = plan["topic"]
    print(f"[规划] 今日话题：{topic}")
    print(f"[规划] 为什么：{plan['reason']}")
    if plan["due_reviews"]:
        print("[规划] 今天到期的复习表达：")
        for r in plan["due_reviews"]:
            print(f"    - {r['expression']}（{r['translation']}）")
        print("[规划] 练完记得复习哦（复习入口将在图形界面提供）")

    try:
        rounds = int(input("\n[设置] 本次练习几轮对话？（默认 6）> ") or "6")
    except ValueError:
        rounds = 6

    # ---- 2. 组装 Agent 上下文 ----
    first_q = bank.next_question(topic) or f"Tell me something about {topic}."
    used = [first_q]
    ctx = {
        "bank": bank,
        "used": used,
        "topic": topic,
        "tool_funcs": build_tool_funcs({"memory": memory, "bank": bank, "used": used, "topic": topic}),
    }
    agent = ExaminerAgent(cfg, memory, ctx)

    session_id = memory.start_session(topic)
    print(f"\n[考官] 练习开始（第 {session_id} 次练习）……")
    opening = agent.next_move(
        f"Interview topic: {topic}. Start the interview now. "
        f"Ask your first question. Suggested opening: \"{first_q}\""
    )
    tts.speak_or_print(opening, RECORD_DIR, voice=cfg.get("tts_voice"))

    answered = 0
    for i in range(rounds):
        choice = input("\n[回车]开始回答 | [h]卡住了 | [q]结束 > ").strip().lower()
        if choice == "q":
            break
        if choice == "h":
            help_text = agent.next_move("", stuck=True)
            tts.speak_or_print(help_text, RECORD_DIR, voice=cfg.get("tts_voice"))
            choice = input("\n[回车]开始回答 | [q]结束 > ").strip().lower()
            if choice == "q":
                break

        wav_path = RECORD_DIR / f"answer_{i + 1}.wav"
        print("[录音] 开始录音……回答完按回车结束")
        secs = audio.record_to_wav(wav_path)
        if secs < 0.8:
            print("（录音太短，当作沉默，考官继续提问）")
            transcript = "(no response)"
        else:
            print("[转写] 识别中……")
            transcript = asr.transcribe(wav_path, model_name=cfg.get("asr_model", "base"))
            print(f"[你说] {transcript}")
        answered += 1
        reply = agent.next_move(transcript)
        tts.speak_or_print(reply, RECORD_DIR, voice=cfg.get("tts_voice"))

    # ---- 3. 评分 -> 记忆沉淀 -> 打卡 ----
    print("\n[评分] 考官正在为你打分……")
    fb = agent.feedback()
    memory.finish_session(session_id, answered, fb)
    pretty_feedback(fb)
    show_memory_growth(memory)
    memory.close()
    print("\n今天的练习结束，明天继续！加油！")


if __name__ == "__main__":
    if "--gui" in sys.argv:
        import gui

        gui.main()
    else:
        main()
