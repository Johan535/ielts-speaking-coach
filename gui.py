"""雅思口语教练 - M2b 图形界面（PySide6）

架构：
- SessionWorker(QThread)：完整练习会话跑在工作线程（规划→开场→录音→转写→Agent→评分→沉淀），
  所有耗时操作（API 调用、语音合成、语音识别）都不阻塞界面。
- MainWindow：对话区 + 今日规划卡片 + 反馈面板 + 录音/救援/结束按钮 + 复习弹窗。

启动：python main.py --gui
"""
import os
import sys
import threading
from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPainter, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.config import load_config
from app.agent import ExaminerAgent
from app.memory import AgentMemory
from app import paths
from app.planner import Planner
from app.question_bank import QuestionBank
from app.tools import build_tool_funcs
from app import asr, tts
from app.audio import Recorder

# 兼容旧引用：CLI 测试里可能用到
RECORD_DIR = paths.recordings_dir()

# ---------------- 样式 ----------------

STYLE = """
QMainWindow { background: #f5f7fa; }
QGroupBox {
    background: #ffffff;
    border: 1px solid #e0e4ea;
    border-radius: 10px;
    margin-top: 12px;
    padding: 10px 8px 8px 8px;
    font-weight: bold;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
QTextEdit {
    background: #ffffff;
    border: 1px solid #e0e4ea;
    border-radius: 10px;
    padding: 8px;
    font-size: 15px;
}
QPushButton {
    background: #1a73e8;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    font-size: 14px;
}
QPushButton:hover { background: #1765cc; }
QPushButton:disabled { background: #b8c4d0; }
QPushButton#help { background: #fbbc04; color: #3c4043; }
QPushButton#help:hover { background: #e5ac00; }
QPushButton#finish { background: #ea4335; }
QPushButton#finish:hover { background: #d33426; }
QPushButton#secondary { background: #eef2f7; color: #1a73e8; }
QPushButton#secondary:hover { background: #e2e9f2; }
QPushButton#recording { background: #ea4335; }
QLabel#planTopic { font-size: 17px; font-weight: bold; color: #1a73e8; }
QLabel#planReason { color: #5f6368; font-size: 13px; }
QSpinBox { padding: 4px; border-radius: 6px; border: 1px solid #d0d7df; }
QStatusBar { background: #eef2f7; color: #3c4043; }
QListWidget { border: none; font-size: 14px; }
"""


# ---------------- 工作线程：整个练习会话 ----------------

class SessionWorker(QThread):
    """一条龙：规划 → 开场 → 录音/救援循环 → 评分 → 记忆沉淀。

    界面线程通过 request_* 方法投递指令（线程安全），
    工作线程通过 Signal 把进展推回界面。信号保证跨线程安全。
    """

    status = Signal(str)                    # 状态栏文字
    plan_ready = Signal(str, str, list)     # 话题, 理由, 到期复习(dict 列表)
    examiner_said = Signal(str)             # 考官说的一句话
    candidate_said = Signal(str)            # 转写出的考生回答
    record_state = Signal(bool)             # True=录音中
    feedback_ready = Signal(dict)           # 四项评分 JSON
    growth_ready = Signal(dict)             # 记忆档案统计
    session_done = Signal()                 # 会话正常结束
    failed = Signal(str)                    # 会话异常结束

    def __init__(self, cfg: dict, rounds: int):
        super().__init__()
        self.cfg = cfg
        self.rounds = rounds
        # 注意：AgentMemory（SQLite 连接）不能在 UI 线程创建——
        # sqlite3 连接有线程亲和性，必须在 run() 所在的工作线程里创建。
        self._memory = None
        self._bank = None
        self.record_dir = paths.recordings_dir()
        self._start = threading.Event()
        self._stop = threading.Event()
        self._help = threading.Event()
        self._quit = threading.Event()
        self._recorder = None
        self._agent = None

    # ---- 界面线程入口（线程安全）----

    def request_start(self):
        self._start.set()

    def request_stop(self):
        self._stop.set()

    def request_help(self):
        self._help.set()

    def request_quit(self):
        self._quit.set()
        self._stop.set()  # 若正在录音，先停录再退出

    # ---- 会话主流程（工作线程）----

    def run(self):
        try:
            # 工作线程里创建依赖（SQLite 连接有线程亲和性）
            self._memory = AgentMemory()
            self._bank = QuestionBank()
            self._run_session()
        except Exception as e:  # 任何异常都不能让程序崩溃
            self.failed.emit(f"{type(e).__name__}: {e}")
        finally:
            if self._memory is not None:
                self._memory.close()

    def _say(self, text: str):
        """考官说一句话：推给界面 + 语音朗读（失败退化为纯文字）。"""
        self.examiner_said.emit(text)
        try:
            tts.speak(text, self.record_dir, voice=self.cfg.get("tts_voice"))
        except Exception as e:
            self.status.emit(f"（语音合成失败，已退化为文字模式）")

    def _wait_start(self) -> bool:
        """等待用户点「开始回答」；期间可处理救援。返回 False 表示用户退出。"""
        while True:
            if self._help.is_set():
                self._help.clear()
                self.status.emit("🆘 救援中：考官慢速重述 + 关键词……")
                self._say(self._agent.next_move("", stuck=True))
                continue
            if self._quit.is_set():
                return False
            if self._start.is_set():
                self._start.clear()
                return True
            self.msleep(100)

    def _run_session(self):
        # ---- 1. 规划器：今天练什么 ----
        planner = Planner(self._memory)
        plan = planner.daily_task(self._bank)
        topic = plan["topic"]
        self.plan_ready.emit(topic, plan["reason"], plan["due_reviews"])

        # ---- 2. 组装 Agent ----
        first_q = self._bank.next_question(topic) or f"Tell me something about {topic}."
        used = [first_q]
        ctx = {
            "bank": self._bank,
            "used": used,
            "topic": topic,
            "tool_funcs": build_tool_funcs(
                {"memory": self._memory, "bank": self._bank, "used": used, "topic": topic}
            ),
        }
        agent = ExaminerAgent(self.cfg, self._memory, ctx)
        self._agent = agent
        session_id = self._memory.start_session(topic)
        self.status.emit(f"练习开始（第 {session_id} 次）……")

        # ---- 3. 考官开场 ----
        self.status.emit("考官思考中……")
        opening = agent.next_move(
            f"Interview topic: {topic}. Start the interview now. "
            f"Ask your first question. Suggested opening: \"{first_q}\""
        )
        self._say(opening)

        # ---- 4. 录音回答循环 ----
        answered = 0
        for i in range(self.rounds):
            self.status.emit(f"第 {i + 1}/{self.rounds} 轮 · 点「🎤 开始回答」，回答完再点一次结束")
            if not self._wait_start():
                break

            wav_path = self.record_dir / f"answer_{i + 1}.wav"
            self._recorder = Recorder()
            try:
                self._recorder.start()
            except Exception as e:
                self.failed.emit(f"麦克风打开失败：{e}")
                return
            self.record_state.emit(True)
            self.status.emit("录音中……回答完点「⏹ 结束回答」")

            while not (self._stop.is_set() or self._quit.is_set()):
                self.msleep(100)
            self._stop.clear()
            self._recorder.stop()
            secs = self._recorder.save(wav_path)
            self._recorder = None
            self.record_state.emit(False)

            if secs < 0.8:
                transcript = "(no response)"
                self.status.emit("录音太短，当作沉默")
            else:
                self.status.emit("转写中……（首次需加载语音模型，可能稍慢）")
                transcript = asr.transcribe(
                    wav_path, model_name=self.cfg.get("asr_model", "base")
                )
            self.candidate_said.emit(transcript)
            answered += 1

            self.status.emit("考官思考中……")
            self._say(agent.next_move(transcript))

        # ---- 5. 评分 → 记忆沉淀 → 打卡 ----
        if answered == 0:
            self.growth_ready.emit(self._memory.stats())
            self.status.emit("本次没有作答，未评分；明天再来吧！")
            self.session_done.emit()
            return

        self.status.emit("🏁 评分中……")
        fb = agent.feedback()
        self._memory.finish_session(session_id, answered, fb)
        self.feedback_ready.emit(fb)
        self.growth_ready.emit(self._memory.stats())
        self.status.emit("练习结束，明天继续！加油！")
        self.session_done.emit()


# ---------------- 打卡热力图（M3：streak 可视化） ----------------

class CheckinHeatmap(QWidget):
    """近 12 周打卡热力图（GitHub 风格）：绿色=已打卡，浅灰=未打卡，顶部标注月份。"""

    CELL = 13
    GAP = 3
    WEEKS = 12
    LABEL_H = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dates = set()
        step = self.CELL + self.GAP
        self.setFixedSize(self.WEEKS * step + 6, self.LABEL_H + 7 * step + 6)

    def set_dates(self, dates):
        self._dates = set(dates)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        today = date.today()
        start = today - timedelta(days=(self.WEEKS - 1) * 7)
        start -= timedelta(days=start.weekday())  # 对齐到周一
        step = self.CELL + self.GAP

        # 月份标注：该列所在周的周一属于新月时标注
        painter.setPen(QColor("#9aa0a6"))
        for col in range(self.WEEKS):
            monday = start + timedelta(days=col * 7)
            if monday.day <= 7:
                painter.drawText(col * step + 3, 12, f"{monday.month}月")

        # 格子：行=周一..周日，列=周
        for col in range(self.WEEKS):
            for row in range(7):
                d = start + timedelta(days=col * 7 + row)
                if d > today:
                    continue
                x, y = col * step + 3, self.LABEL_H + row * step
                color = QColor("#34a853") if d.isoformat() in self._dates else QColor("#e8eaed")
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(x, y, self.CELL, self.CELL, 3, 3)


class ReviewDialog(QDialog):
    """语料库：Tab1 到期复习（间隔重复），Tab2 全部语料（可标记掌握）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📚 语料库与复习")
        self.resize(520, 440)
        self.memory = AgentMemory()
        self.items = []       # (corpus_id, expression, translation, times)
        self.all_items = []   # corpus_all() 的行（dict）

        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Tab1：到期复习（间隔重复）
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        self.hint = QLabel()
        l1.addWidget(self.hint)
        self.listw = QListWidget()
        l1.addWidget(self.listw)
        self.btn_done = QPushButton("✅ 标记已复习（间隔重复：1→3→7→14 天）")
        self.btn_done.clicked.connect(self._mark_reviewed)
        l1.addWidget(self.btn_done)
        tabs.addTab(w1, "⏰ 到期复习")

        # Tab2：全部语料（可标记掌握）
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        self.all_hint = QLabel()
        l2.addWidget(self.all_hint)
        self.allw = QListWidget()
        l2.addWidget(self.allw)
        self.btn_master = QPushButton("⭐ 标记已掌握 / 取消掌握")
        self.btn_master.clicked.connect(self._toggle_mastered)
        l2.addWidget(self.btn_master)
        tabs.addTab(w2, "📖 全部语料")

        self._reload()
        self._reload_all()

    def _reload(self):
        rows = self.memory.conn.execute(
            "SELECT id, expression, translation, times_reviewed FROM corpus "
            "WHERE mastered=0 AND (next_review_at IS NULL OR next_review_at <= date('now','localtime')) "
            "ORDER BY times_reviewed ASC LIMIT 20"
        ).fetchall()
        self.items = [(r["id"], r["expression"], r["translation"], r["times_reviewed"]) for r in rows]
        self.hint.setText(f"今天有 {len(self.items)} 条表达到期。选中一条，点下方按钮标记已复习。")
        self.listw.clear()
        for cid, expr, trans, times in self.items:
            item = QListWidgetItem(f"{expr}  —  {trans}  （复习过 {times} 次）")
            item.setData(Qt.UserRole, cid)
            self.listw.addItem(item)
        if not self.items:
            self.hint.setText("🎉 今天没有到期表达，去练口语吧！")

    def _reload_all(self):
        self.all_items = self.memory.corpus_all()
        self.all_hint.setText(
            f"语料库共 {len(self.all_items)} 条好表达。标记掌握后不再出现在到期复习里。")
        self.allw.clear()
        for r in self.all_items:
            tag = "✅" if r["mastered"] else "📖"
            item = QListWidgetItem(f"{tag} {r['expression']}  —  {r['translation']}")
            item.setData(Qt.UserRole, r["id"])
            self.allw.addItem(item)

    def _mark_reviewed(self):
        item = self.listw.currentItem()
        if item is None:
            QMessageBox.information(self, "提示", "请先选中一条表达。")
            return
        cid = item.data(Qt.UserRole)
        self.memory.mark_reviewed(cid)
        self._reload()

    def _toggle_mastered(self):
        item = self.allw.currentItem()
        if item is None:
            QMessageBox.information(self, "提示", "请先选中一条表达。")
            return
        cid = item.data(Qt.UserRole)
        row = next((r for r in self.all_items if r["id"] == cid), None)
        if row is None:
            return
        self.memory.mark_mastered(cid, 0 if row["mastered"] else 1)
        self._reload_all()
        self._reload()

    def closeEvent(self, event):
        self.memory.close()
        super().closeEvent(event)


# ---------------- 主窗口 ----------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("雅思口语教练 v0.2 · Agent 版")
        self.resize(1100, 720)
        self.cfg = load_config()
        self.worker: SessionWorker | None = None
        self._recording = False
        self._build_ui()
        self._refresh_checkins()
        self._append_system("👋 欢迎！点击右侧「开始练习」，考官会先告诉你今天练什么。")

    # ---------- 界面搭建 ----------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)

        # 左：对话区 + 按钮条
        left = QVBoxLayout()
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setPlaceholderText("考官的话会出现在这里……")
        left.addWidget(self.chat)

        btns = QHBoxLayout()
        self.btn_record = QPushButton("🎤 开始回答")
        self.btn_record.clicked.connect(self._on_record)
        self.btn_record.setEnabled(False)
        self.btn_help = QPushButton("🆘 卡住了")
        self.btn_help.setObjectName("help")
        self.btn_help.clicked.connect(self._on_help)
        self.btn_help.setEnabled(False)
        self.btn_finish = QPushButton("🏁 结束并评分")
        self.btn_finish.setObjectName("finish")
        self.btn_finish.clicked.connect(self._on_finish)
        self.btn_finish.setEnabled(False)
        btns.addWidget(self.btn_record)
        btns.addWidget(self.btn_help)
        btns.addWidget(self.btn_finish)
        btns.addStretch(1)
        left.addLayout(btns)
        root.addLayout(left, stretch=3)

        # 右：规划卡片 + 复习 + 反馈面板
        right = QVBoxLayout()
        right.setSpacing(10)

        plan_box = QGroupBox("🗓 今日规划")
        plan_lay = QVBoxLayout(plan_box)
        self.plan_topic = QLabel("（点击「开始练习」生成）")
        self.plan_topic.setObjectName("planTopic")
        self.plan_topic.setWordWrap(True)
        self.plan_reason = QLabel("")
        self.plan_reason.setObjectName("planReason")
        self.plan_reason.setWordWrap(True)
        plan_lay.addWidget(self.plan_topic)
        plan_lay.addWidget(self.plan_reason)

        rounds_row = QHBoxLayout()
        rounds_row.addWidget(QLabel("本次轮数："))
        self.spin_rounds = QSpinBox()
        self.spin_rounds.setRange(2, 10)
        self.spin_rounds.setValue(6)
        rounds_row.addWidget(self.spin_rounds)
        rounds_row.addStretch(1)
        plan_lay.addLayout(rounds_row)

        self.btn_start = QPushButton("🚀 开始练习")
        self.btn_start.clicked.connect(self._on_start)
        plan_lay.addWidget(self.btn_start)
        right.addWidget(plan_box)

        checkin_box = QGroupBox("🔥 打卡记录")
        ck_lay = QVBoxLayout(checkin_box)
        self.lbl_streak = QLabel("连续 0 天 · 累计 0 天 · 最长 0 天")
        self.lbl_streak.setStyleSheet("color:#5f6368; font-weight:normal;")
        ck_lay.addWidget(self.lbl_streak)
        self.heatmap = CheckinHeatmap()
        ck_lay.addWidget(self.heatmap, alignment=Qt.AlignHCenter)
        right.addWidget(checkin_box)

        self.btn_review = QPushButton("📚 语料库与复习")
        self.btn_review.setObjectName("secondary")
        self.btn_review.clicked.connect(self._on_review)
        right.addWidget(self.btn_review)

        fb_box = QGroupBox("📊 本次反馈（练习结束后显示）")
        fb_lay = QVBoxLayout(fb_box)
        self.fb_text = QTextEdit()
        self.fb_text.setReadOnly(True)
        self.fb_text.setFrameShape(QFrame.NoFrame)
        self.fb_text.setFixedHeight(240)
        self.fb_text.setPlaceholderText("四项评分、纠错、新表达会出现在这里……")
        fb_lay.addWidget(self.fb_text)
        right.addWidget(fb_box)

        self.lbl_memory = QLabel("📁 教练档案：练习 0 次 · 弱点 0 条 · 语料 0 条")
        self.lbl_memory.setStyleSheet("color:#5f6368;")
        right.addWidget(self.lbl_memory)
        right.addStretch(1)
        right_wrap = QWidget()
        right_wrap.setLayout(right)
        right_wrap.setFixedWidth(360)
        root.addWidget(right_wrap)

        self.statusBar().showMessage("就绪")

    # ---------- 按钮动作（界面线程） ----------

    def _on_start(self):
        if self.worker is not None:
            return
        self._append_system("🚀 会话启动，考官准备中……")
        self.fb_text.clear()
        self.worker = SessionWorker(self.cfg, self.spin_rounds.value())
        self.worker.plan_ready.connect(self._on_plan)
        self.worker.examiner_said.connect(self._append_examiner)
        self.worker.candidate_said.connect(self._append_candidate)
        self.worker.status.connect(self.statusBar().showMessage)
        self.worker.record_state.connect(self._on_record_state)
        self.worker.feedback_ready.connect(self._on_feedback)
        self.worker.growth_ready.connect(self._on_growth)
        self.worker.session_done.connect(self._on_session_done)
        self.worker.failed.connect(self._on_failed)
        self.btn_start.setEnabled(False)
        self.btn_record.setEnabled(True)
        self.btn_help.setEnabled(True)
        self.btn_finish.setEnabled(True)
        self.worker.start()

    def _on_record(self):
        if self.worker is None:
            return
        if self._recording:
            self.worker.request_stop()
        else:
            self.worker.request_start()

    def _on_help(self):
        if self.worker is not None and not self._recording:
            self.worker.request_help()

    def _on_finish(self):
        if self.worker is not None:
            self._append_system("🏁 正在结束练习并评分……")
            self.btn_finish.setEnabled(False)
            self.btn_record.setEnabled(False)
            self.worker.request_quit()

    def _on_review(self):
        ReviewDialog(self).exec()

    # ---------- 工作线程信号回调（跨线程，由 Qt 排队执行） ----------

    def _on_plan(self, topic: str, reason: str, due_reviews: list):
        self.plan_topic.setText(f"今天练：{topic}")
        self.plan_reason.setText(reason)
        n = len(due_reviews)
        if n:
            self.btn_review.setText(f"📚 复习到期表达（{n} 条）")
            self._append_system(f"📚 今天有 {n} 条表达到期复习，练完点右侧按钮复习。")

    def _on_record_state(self, recording: bool):
        self._recording = recording
        if recording:
            self.btn_record.setText("⏹ 结束回答")
            self.btn_record.setObjectName("recording")
            self.btn_help.setEnabled(False)
        else:
            self.btn_record.setText("🎤 开始回答")
            self.btn_record.setObjectName("")
            self.btn_help.setEnabled(self.worker is not None)
        self.btn_record.style().unpolish(self.btn_record)
        self.btn_record.style().polish(self.btn_record)

    def _on_feedback(self, fb: dict):
        lines = ["<h3>📊 雅思四项评分（模拟，仅供参考）</h3>", "<table>"]
        rows = [
            ("流利度 Fluency", fb.get("fluency", "?")),
            ("词汇 Vocabulary", fb.get("vocabulary", "?")),
            ("语法 Grammar", fb.get("grammar", "?")),
            ("发音 Pronunciation", fb.get("pronunciation", "?")),
        ]
        for name, score in rows:
            lines.append(f"<tr><td>{name}</td><td>&nbsp;&nbsp;<b>{score}</b></td></tr>")
        lines.append("</table>")
        if fb.get("scores_reason"):
            lines.append(f"<p><b>点评：</b>{fb['scores_reason']}</p>")
        errs = fb.get("errors") or []
        if errs:
            lines.append("<p><b>纠错：</b></p><ul>")
            for e in errs:
                lines.append(f"<li>{e.get('wrong', '')} → {e.get('right', '')}（{e.get('why', '')}）</li>")
            lines.append("</ul>")
        news = fb.get("new_expressions") or []
        if news:
            lines.append("<p><b>新表达：</b></p><ul>")
            for n in news:
                lines.append(f"<li>{n}</li>")
            lines.append("</ul>")
        if fb.get("encouragement"):
            lines.append(f"<p>💪 {fb['encouragement']}</p>")
        self.fb_text.setHtml("".join(lines))

    def _on_growth(self, stats: dict):
        self.lbl_memory.setText(
            f"📁 教练档案：练习 {stats['sessions']} 次 · 弱点 {stats['weaknesses']} 条 · "
            f"语料 {stats['corpus']} 条 · 打卡 {stats['checkins']} 天"
        )
        self._refresh_checkins()  # 本次打卡已写入，刷新 streak

    def _refresh_checkins(self):
        """读一次打卡统计（UI 线程短连接，读完即关）。"""
        mem = AgentMemory()
        try:
            s = mem.checkin_streak()
        finally:
            mem.close()
        self.lbl_streak.setText(
            f"连续 {s['streak']} 天 · 累计 {s['total_days']} 天 · 最长 {s['longest']} 天")
        self.heatmap.set_dates(s["dates"])

    def _on_session_done(self):
        self._reset_controls()

    def _on_failed(self, msg: str):
        self._append_system(f"⚠️ 出错了：{msg}")
        self.statusBar().showMessage(f"出错：{msg}")
        self._reset_controls()

    def _reset_controls(self):
        self.btn_start.setEnabled(True)
        self.btn_record.setEnabled(False)
        self.btn_help.setEnabled(False)
        self.btn_finish.setEnabled(False)
        if self._recording:
            self._on_record_state(False)
        self.worker = None

    # ---------- 对话区输出 ----------

    def _append_html(self, who: str, color: str, text: str):
        self.chat.append(
            f"<p style='margin:6px 0;'><b style='color:{color};'>{who}：</b>"
            f"<span style='color:#202124;'>{text}</span></p>"
        )
        self.chat.moveCursor(QTextCursor.End)

    def _append_examiner(self, text: str):
        self._append_html("考官", "#1a73e8", text)

    def _append_candidate(self, text: str):
        self._append_html("我", "#188038", text)

    def _append_system(self, text: str):
        self.chat.append(f"<p style='margin:4px 0;color:#80868b;font-size:13px;'>{text}</p>")
        self.chat.moveCursor(QTextCursor.End)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    try:
        win = MainWindow()
    except FileNotFoundError as e:
        # 首次运行没配置：弹窗说明，并打开配置所在目录方便用户编辑
        QMessageBox.critical(None, "需要配置", str(e))
        if paths.is_frozen():
            try:
                os.startfile(str(paths.user_data_dir()))
            except Exception:
                pass
        sys.exit(1)
    win.show()
    code = 0
    try:
        code = app.exec()
    except Exception as e:
        # 打包版无控制台：任何崩溃都写日志 + 弹窗，方便用户反馈
        import traceback

        log = paths.user_data_dir() / "error.log"
        try:
            log.write_text(traceback.format_exc(), encoding="utf-8")
        except Exception:
            pass
        QMessageBox.critical(None, "程序出错了",
                             f"{type(e).__name__}: {e}\n\n详情已写入：\n{log}")
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
