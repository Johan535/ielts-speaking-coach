"""GUI 冒烟测试（无硬件、无 API、不改动用户数据）

- 用 QT_QPA_PLATFORM=offscreen 在无窗口模式下构建界面
- 验证：控件齐全、初始状态正确、信号回调正确更新界面
- 不点击「开始练习」（会触发真实 API），复习弹窗只读不点「已复习」
"""
import os
import sys
from pathlib import Path

# Windows 控制台默认 GBK，强制 UTF-8 避免中文乱码
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

import gui  # noqa: E402

PASS = 0


def check(name: str, cond: bool):
    global PASS
    assert cond, f"FAIL: {name}"
    PASS += 1
    print(f"  ✓ {name}")


def test_mainwindow():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(gui.STYLE)
    win = gui.MainWindow()

    check("窗口标题", win.windowTitle() == "雅思口语教练 v0.2 · Agent 版")
    check("对话区存在", win.chat is not None and not win.chat.isReadOnly() is False)
    check("规划卡片初始占位", "开始练习" in win.plan_topic.text())
    check("轮数默认 6", win.spin_rounds.value() == 6)
    check("轮数范围 2-10", win.spin_rounds.minimum() == 2 and win.spin_rounds.maximum() == 10)
    check("未开始时录音键禁用", not win.btn_record.isEnabled())
    check("未开始时救援键禁用", not win.btn_help.isEnabled())
    check("未开始时结束键禁用", not win.btn_finish.isEnabled())
    check("开始键可用", win.btn_start.isEnabled())
    check("复习键可用", win.btn_review.isEnabled())

    # 信号回调（不启动真实会话，直接喂假数据）
    win._append_examiner("What is your favourite food?")
    win._append_candidate("I like noodles.")
    check("考官消息上屏", "What is your favourite food?" in win.chat.toPlainText())
    check("考生消息上屏", "I like noodles." in win.chat.toPlainText())

    win._on_record_state(True)
    check("录音中按钮变红字", "结束回答" in win.btn_record.text())
    check("录音中救援键禁用", not win.btn_help.isEnabled())
    win._on_record_state(False)
    check("停止后按钮复原", "开始回答" in win.btn_record.text())

    fb = {
        "fluency": 6.5, "vocabulary": 6.0, "grammar": 6.0, "pronunciation": 6.5,
        "scores_reason": "Good ideas, simple structures.",
        "errors": [{"wrong": "I very like", "right": "I really like", "why": "very 不能修饰动词"}],
        "new_expressions": ["comfort food (治愈系美食)"],
        "encouragement": "Keep it up!",
    }
    win._on_feedback(fb)
    html = win.fb_text.toHtml()
    check("反馈含流利度", "流利度" in html and "6.5" in html)
    check("反馈含纠错", "very 不能修饰动词" in html)
    check("反馈含新表达", "comfort food" in html)

    win._on_growth({"sessions": 3, "weaknesses": 2, "corpus": 5, "checkins": 2})
    check("档案统计上屏", "练习 3 次" in win.lbl_memory.text() and "语料 5 条" in win.lbl_memory.text())

    win._on_session_done()
    check("会话结束后按钮复位", win.btn_start.isEnabled() and not win.btn_record.isEnabled())

    win.close()
    return app


def test_review_dialog():
    dlg = gui.ReviewDialog()
    # 只读验证：列表与提示文字一致（不点「已复习」，避免改动真实数据）
    expected = dlg.hint.text()
    check("复习弹窗可打开", dlg.windowTitle() == "📚 复习到期表达")
    if dlg.items:
        check("复习提示与实际列表一致", f"{len(dlg.items)} 条" in expected)
    else:
        check("复习弹窗空态提示", "没有到期表达" in expected)
    check("复习列表项数一致", dlg.listw.count() == len(dlg.items))
    dlg.close()


def main():
    print("== GUI 冒烟测试（offscreen）==")
    app = test_mainwindow()
    test_review_dialog()
    print(f"\n全部通过：{PASS} 项断言 ✓")


if __name__ == "__main__":
    main()
