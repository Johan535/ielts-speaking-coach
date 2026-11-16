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
    check("复习弹窗可打开", dlg.windowTitle() == "📚 语料库与复习")
    check("弹窗含两个页签", dlg.listw is not None and dlg.allw is not None)
    if dlg.items:
        check("复习提示与实际列表一致", f"{len(dlg.items)} 条" in expected)
    else:
        check("复习弹窗空态提示", "没有到期表达" in expected)
    check("复习列表项数一致", dlg.listw.count() == len(dlg.items))
    check("全部语料列表项数一致", dlg.allw.count() == len(dlg.all_items))
    dlg.close()


def test_checkin_card():
    """M3：打卡卡片——streak 标签与热力图存在，喂假数据后正确更新。"""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(gui.STYLE)
    win = gui.MainWindow()
    check("打卡热力图存在", win.heatmap is not None)
    check("streak 标签存在", "连续" in win.lbl_streak.text())
    # 直接调用刷新函数（构造时已调过一次，这里验证数据驱动更新）
    win.heatmap.set_dates(["2026-11-14", "2026-11-15", "2026-11-16"])
    check("热力图接受日期列表", len(win.heatmap._dates) == 3)
    win.close()


def test_memory_streak_and_corpus():
    """M3 数据层：checkin_streak / corpus_all / mark_mastered（:memory: 库，不碰用户数据）。"""
    from datetime import date, timedelta

    from app.memory import AgentMemory

    mem = AgentMemory(":memory:")
    today = date.today()
    iso = lambda n: (today - timedelta(days=n)).isoformat()
    # 打卡：3天前、2天前、1天前、今天（连续4天）；6天前、5天前（连续2天，隔断）
    for n in (6, 5, 3, 2, 1, 0):
        mem.conn.execute(
            "INSERT INTO checkins (date, session_id, completed) VALUES (?, 1, 1)", (iso(n),))
    mem.conn.commit()
    s = mem.checkin_streak()
    check("当前连续 4 天", s["streak"] == 4)
    check("累计 6 天", s["total_days"] == 6)
    check("最长连续 4 天", s["longest"] == 4)
    check("日期升序", s["dates"] == sorted(s["dates"]))

    # 断签场景：今天没打卡，从昨天起算
    mem.conn.execute("DELETE FROM checkins WHERE date=?", (iso(0),))
    mem.conn.commit()
    s = mem.checkin_streak()
    check("今天未打卡不打断连续", s["streak"] == 3)

    # 语料库
    cid = mem.save_corpus("hit the books", "用功读书", source="dialogue")
    mem.save_corpus("a piece of cake", "小菜一碟", source="feedback")
    rows = mem.corpus_all()
    check("语料共 2 条", len(rows) == 2)
    check("新语料在前", rows[0]["expression"] == "a piece of cake")
    mem.mark_mastered(cid, 1)
    check("标记掌握生效", mem.corpus_all()[1]["mastered"] == 1)
    mem.mark_mastered(cid, 0)
    check("取消掌握生效", mem.corpus_all()[1]["mastered"] == 0)
    mem.close()


def test_worker_thread_affinity():
    """回归：SQLite 连接有线程亲和性——SessionWorker 构造时不得在 UI 线程打开连接，
    必须在 run() 所在的工作线程里创建 AgentMemory（曾导致
    'SQLite objects created in a thread can only be used in that same thread'）。"""
    import json as _json

    cfg = _json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    worker = gui.SessionWorker(cfg, rounds=2)
    check("构造时不在当前线程打开 SQLite 连接", worker._memory is None)
    check("构造时未加载题库", worker._bank is None)


def test_first_run_config_missing():
    """回归：打包版首启缺配置 → 弹「需要配置」框，并调用 os.startfile 打开数据目录。
    （首启 exit 1 是设计行为，不是崩溃——曾误判。）"""
    from unittest import mock

    with mock.patch("gui.QMessageBox.critical") as m_crit, \
         mock.patch("gui.os.startfile") as m_start, \
         mock.patch("gui.paths.is_frozen", return_value=True), \
         mock.patch("gui.paths.user_data_dir", return_value=Path("C:/fake")):
        gui.handle_first_run_missing_config(FileNotFoundError("请填写 api_key"))
        check("弹出『需要配置』对话框", m_crit.called)
        check("对话框内容包含引导文案", "请填写 api_key" in m_crit.call_args[0][2])
        m_start.assert_called_once()
        check("自动打开数据目录", m_start.call_args[0][0] == str(Path("C:/fake")))


def main():
    print("== GUI 冒烟测试（offscreen）==")
    app = test_mainwindow()
    test_review_dialog()
    test_worker_thread_affinity()
    test_checkin_card()
    test_memory_streak_and_corpus()
    test_first_run_config_missing()
    print(f"\n全部通过：{PASS} 项断言 ✓")


if __name__ == "__main__":
    main()
