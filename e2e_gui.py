"""GUI 端到端实测（手动运行）：offscreen 无窗口 + 真实 API + 真实麦克风。

驱动真实 SessionWorker 完整跑一轮（静默回答路径），验证：
规划 → 开场 → 录音 → 转写 → Agent 接话 → 评分 → 记忆沉淀 → 打卡 全链路。
运行前自动备份 data/coach.db，结束自动还原，不污染用户数据。

用法：.venv\\Scripts\\python.exe e2e_gui.py
"""
import re
import os
import shutil
import sys
from pathlib import Path

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QObject, QTimer, Slot  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import gui  # noqa: E402

DB = ROOT / "data" / "coach.db"
BAK = ROOT / "data" / "coach.db.e2e_bak"
REC = ROOT / "data" / "recordings"

PASS = 0


def check(name: str, cond: bool):
    global PASS
    assert cond, f"FAIL: {name}"
    PASS += 1
    print(f"  ✓ {name}")


class Driver(QObject):
    """接收 SessionWorker 信号并自动驱动录音（UI 线程，保证 QTimer 安全）。"""

    def __init__(self, worker, app):
        super().__init__()
        self.worker = worker
        self.app = app
        self.plan = None
        self.examiner_lines = 0
        self.feedback = None
        self.growth = None
        self.failed = None
        self.record_started = False
        self.stopped = False
        self.stop_pending = False
        self.statuses = []
        self.rounds_seen = set()

    @Slot(str, str, list)
    def on_plan(self, topic, reason, due):
        self.plan = topic

    @Slot(str)
    def on_examiner(self, text):
        self.examiner_lines += 1

    @Slot(str)
    def on_status(self, s):
        self.statuses.append(s)
        # 每轮出现「第 i/N 轮」提示时触发一次开始回答
        m = re.search(r"第 (\d+)/(\d+) 轮", s)
        if m:
            idx = int(m.group(1))
            if idx not in self.rounds_seen:
                self.rounds_seen.add(idx)
                self.record_started = True
                QTimer.singleShot(400, self.worker.request_start)

    @Slot(bool)
    def on_record_state(self, recording: bool):
        if recording and not self.stop_pending:
            self.stop_pending = True
            QTimer.singleShot(1500, self.worker.request_stop)
        if not recording:
            self.stopped = True
            self.stop_pending = False

    @Slot(dict)
    def on_feedback(self, fb):
        self.feedback = fb

    @Slot(dict)
    def on_growth(self, g):
        self.growth = g

    @Slot(str)
    def on_failed(self, m):
        self.failed = m
        self.app.quit()

    @Slot()
    def on_done(self):
        self.app.quit()


def main():
    if DB.exists():
        shutil.copy2(DB, BAK)
    else:
        BAK.unlink(missing_ok=True)

    app = QApplication(sys.argv)
    app.setStyleSheet(gui.STYLE)
    win = gui.MainWindow()
    win.spin_rounds.setValue(win.spin_rounds.minimum())  # 最少轮数（QSpinBox 最小 2）
    rounds = win.spin_rounds.value()
    win._on_start()  # 复用按钮入口：创建 SessionWorker 并 start()
    w = win.worker

    d = Driver(w, app)
    # 在 app.exec() 之前连接即可收到全部信号（跨线程信号排队投递）
    w.plan_ready.connect(d.on_plan)
    w.examiner_said.connect(d.on_examiner)
    w.status.connect(d.on_status)
    w.record_state.connect(d.on_record_state)
    w.feedback_ready.connect(d.on_feedback)
    w.growth_ready.connect(d.on_growth)
    w.failed.connect(d.on_failed)
    w.session_done.connect(d.on_done)

    def on_timeout():
        d.failed = "TIMEOUT（5 分钟兜底）"
        w.request_quit()
        QTimer.singleShot(3000, app.quit)

    QTimer.singleShot(300_000, on_timeout)  # 兜底超时 5 分钟

    print("== 会话进行中（真实 API + 麦克风，请勿操作）==")
    app.exec()
    w.wait(5000)

    print("\n== 诊断信息 ==")
    print(f"failed = {d.failed}")
    print(f"examiner_lines = {d.examiner_lines}")
    for s in d.statuses:
        print(f"  [状态] {s}")

    print("\n== 断言 ==")
    check("规划器给出话题", bool(d.plan))
    check(f"考官开口 ≥{rounds + 1} 句（开场+每轮接话）", d.examiner_lines >= rounds + 1)
    check("每轮都录了音", d.record_started and d.stopped and len(d.rounds_seen) == rounds)
    check("无异常", d.failed is None)
    ok_fb = (
        isinstance(d.feedback, dict)
        and all(k in d.feedback for k in ("fluency", "vocabulary", "grammar", "pronunciation"))
    )
    check("反馈为四项评分 JSON", ok_fb)
    check("记忆档案已更新", isinstance(d.growth, dict))
    if d.feedback:
        scores = {k: d.feedback[k] for k in ("fluency", "vocabulary", "grammar", "pronunciation")}
        print(f"\n话题：{d.plan}；考官共 {d.examiner_lines} 句；评分：{scores}")
    return 0


def cleanup():
    if BAK.exists():
        shutil.copy2(BAK, DB)
        BAK.unlink()
    if REC.exists():
        for f in list(REC.glob("answer_*.wav")) + list(REC.glob("tts_*.mp3")):
            try:
                f.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    except Exception:
        import traceback

        traceback.print_exc()
    finally:
        cleanup()
        print(f"\n结果：{PASS} 通过")
    sys.exit(0 if code == 0 else 1)
