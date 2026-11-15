"""雅思口语教练 - M1 命令行最小闭环

流程：选话题 -> AI 考官提问（语音+文字）-> 按回车录音回答 -> 转写 -> AI 追问
      卡住输入 h 求助 -> 练习结束自动生成雅思四项评分反馈
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
from app.llm import Examiner
from app.question_bank import QuestionBank
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


def main():
    cfg = load_config()
    RECORD_DIR.mkdir(exist_ok=True)

    print("=" * 50)
    print("  雅思口语教练 v0.1（M1 命令行最小闭环）")
    print("  考官会用英文提问并朗读；轮到你时按回车开始录音，")
    print("  说完再按一次回车结束。卡住输入 h 求助，q 提前结束。")
    print("=" * 50 + "\n")

    qb = QuestionBank()
    topic = qb.random_topic()
    first_q = qb.random_question(topic)
    print(f"[话题] 今日话题：{topic['name']}")

    try:
        rounds = int(input("[设置] 本次练习几轮对话？（默认 6）> ") or "6")
    except ValueError:
        rounds = 6

    examiner = Examiner(cfg)
    opening = examiner.next_move(
        f"Interview topic: {topic['name']}. Start the interview now. "
        f"Ask your first question. Suggested opening: \"{first_q}\""
    )
    tts.speak_or_print(opening, RECORD_DIR, voice=cfg.get("tts_voice"))

    transcript = ""
    for i in range(rounds):
        choice = input("\n[回车]开始回答 | [h]卡住了 | [q]结束 > ").strip().lower()
        if choice == "q":
            break
        if choice == "h":
            help_text = examiner.next_move("", stuck=True)
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
        reply = examiner.next_move(transcript)
        tts.speak_or_print(reply, RECORD_DIR, voice=cfg.get("tts_voice"))

    print("\n[评分] 考官正在为你打分……")
    fb = examiner.feedback()
    pretty_feedback(fb)
    print("今天的练习结束，明天继续！加油！")


if __name__ == "__main__":
    main()
