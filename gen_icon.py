"""生成应用图标 icon.ico（PySide6 QPainter 绘制，无需额外依赖）。

画一个蓝色圆角方块 + 白色对话气泡 + "A+" 字样，寓意口语教练。
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import QApplication


def make_icon(size: int = 256) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)

    # 蓝色圆角底
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1a73e8"))
    r = size * 0.055
    p.drawRoundedRect(QRectF(0, 0, size, size), r, r)

    # 白色对话气泡
    p.setBrush(QColor("#ffffff"))
    bw, bh = size * 0.62, size * 0.42
    bx, by = size * 0.19, size * 0.16
    p.drawRoundedRect(QRectF(bx, by, bw, bh), size * 0.08, size * 0.08)
    # 气泡小尾巴（三角形）
    from PySide6.QtGui import QPolygonF
    from PySide6.QtCore import QPointF
    tail = QPolygonF([
        QPointF(bx + bw * 0.18, by + bh - 2),
        QPointF(bx + bw * 0.38, by + bh - 2),
        QPointF(bx + bw * 0.18, by + bh + size * 0.22),
    ])
    p.drawPolygon(tail)

    # 文字 A+（上半行）+ 口语波形（下半行用三个小竖条代替）
    p.setPen(QColor("#1a73e8"))
    font = QFont("Segoe UI", int(size * 0.16))
    font.setBold(True)
    p.setFont(font)
    p.drawText(QRectF(bx, by - size * 0.02, bw, bh), Qt.AlignCenter, "A+")
    p.end()
    return pm


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    pm = make_icon()
    out = ROOT / "icon.ico"
    ok = pm.save(str(out), "ICO")
    if not ok:
        raise RuntimeError("ICO 保存失败（Qt ICO 插件不可用）")
    print(f"已生成 {out} ({pm.width()}x{pm.height()})")


if __name__ == "__main__":
    main()
