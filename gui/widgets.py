"""Hand-painted widgets: the cut-corner shapes QSS cannot draw."""
from __future__ import annotations

import math

from PySide6.QtCore import (
    QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui import theme


def chamfer_path(rect: QRectF, cut: float) -> QPainterPath:
    """Rectangle with the top-left and bottom-right corners cut at 45 deg."""
    path = QPainterPath()
    path.moveTo(rect.left() + cut, rect.top())
    path.lineTo(rect.right(), rect.top())
    path.lineTo(rect.right(), rect.bottom() - cut)
    path.lineTo(rect.right() - cut, rect.bottom())
    path.lineTo(rect.left(), rect.bottom())
    path.lineTo(rect.left(), rect.top() + cut)
    path.closeSubpath()
    return path


def app_icon() -> QIcon:
    """Red cut-corner block with a white open shackle gap: the app mark."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, size, size)
        p.fillPath(chamfer_path(r, size * 0.28), QColor(theme.RED))
        bar = QRectF(size * 0.30, size * 0.44, size * 0.40, size * 0.12)
        p.fillRect(bar, QColor(theme.ON_RED))
        p.end()
        icon.addPixmap(pm)
    return icon


class ChamferPanel(QFrame):
    """Surface panel with cut corners. Colours are theme token names
    ('SURFACE', 'LINE'...), resolved at paint time so a theme switch
    repaints them."""

    def __init__(self, parent=None, fill="SURFACE"):
        super().__init__(parent)
        self.setObjectName("chamferPanel")
        self._fill = fill
        self._border = "LINE"
        self._dashed = False
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_look(self, fill: str, border: str, dashed: bool = False) -> None:
        self._fill, self._border, self._dashed = fill, border, dashed
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = chamfer_path(rect, theme.CHAMFER)
        p.fillPath(path, QColor(getattr(theme, self._fill)))
        pen = QPen(QColor(getattr(theme, self._border)), 1)
        if self._dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([4, 4])
        p.setPen(pen)
        p.drawPath(path)


def mix(a, b, t: float) -> QColor:
    """Blend two colours (QColor or '#hex'), alpha included."""
    ca, cb = QColor(a), QColor(b)
    return QColor.fromRgbF(
        ca.redF() + (cb.redF() - ca.redF()) * t,
        ca.greenF() + (cb.greenF() - ca.greenF()) * t,
        ca.blueF() + (cb.blueF() - ca.blueF()) * t,
        ca.alphaF() + (cb.alphaF() - ca.alphaF()) * t,
    )


class _Eased:
    """A 0..1 value that eases towards a target and repaints its widget."""

    def __init__(self, widget: QWidget, ms: int, value: float = 0.0):
        self.value = value
        self._w = widget
        self._anim = QVariantAnimation(widget)
        self._anim.setDuration(ms)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set)

    def _set(self, v):
        self.value = float(v)
        self._w.update()

    def to(self, target: float) -> None:
        if abs(self.value - target) < 1e-3 and self._anim.state() != QVariantAnimation.State.Running:
            return
        self._anim.stop()
        self._anim.setStartValue(self.value)
        self._anim.setEndValue(float(target))
        self._anim.start()


class Toggle(QAbstractButton):
    """Square-knob switch. Red track when on. The knob slides, sits slightly
    raised over a recessed track, and dips a pixel while pressed."""

    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._pos = _Eased(self, 180, 1.0 if checked else 0.0)
        self.toggled.connect(lambda on: self._pos.to(1.0 if on else 0.0))

    def sizeHint(self):
        return QSize(38, 20)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(1, 1, 36, 18)
        t = self._pos.value
        enabled = self.isEnabled()
        if enabled:
            fill = mix(theme.LINE, theme.RED, t)
            knob_color = mix(theme.MUTED, theme.ON_RED, t)
        else:
            fill, knob_color = QColor(theme.FAINT), QColor(theme.DIM)
        p.fillRect(track, fill)
        # Recessed track: a soft shadow under the top edge.
        inset = QLinearGradient(0, track.top(), 0, track.top() + 6)
        inset.setColorAt(0, QColor(0, 0, 0, 70))
        inset.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(track, inset)

        dip = 1 if self.isDown() else 0
        knob = QRectF(4 + (track.right() - 19) * t, 4 + dip, 12, 12)
        if enabled and not dip:
            p.fillRect(knob.translated(0, 1), QColor(0, 0, 0, 60))
        face = QLinearGradient(knob.topLeft(), knob.bottomLeft())
        face.setColorAt(0, knob_color.lighter(112))
        face.setColorAt(1, knob_color.darker(108))
        p.fillRect(knob, face)
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.WHITE), 1))
            p.drawRect(QRectF(0.5, 0.5, 37, 19))


class OptionRow(QWidget):
    """Switch + title + one-line explanation. The whole row is clickable."""

    toggled = Signal(bool)

    def __init__(self, title: str, desc: str, checked=True, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle = Toggle(checked)
        self.toggle.toggled.connect(self.toggled)

        t = QLabel(title)
        t.setObjectName("optTitle")
        d = QLabel(desc)
        d.setObjectName("optDesc")
        d.setWordWrap(True)

        text = QVBoxLayout()
        text.setSpacing(2)
        text.setContentsMargins(0, 0, 0, 0)
        text.addWidget(t)
        text.addWidget(d)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(12)
        row.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignTop)
        row.addLayout(text, 1)

    def isChecked(self) -> bool:
        return self.toggle.isChecked()

    def setChecked(self, on: bool) -> None:
        self.toggle.setChecked(on)

    def mouseReleaseEvent(self, event):
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self.toggle.toggle()


class PrimaryButton(QPushButton):
    """The one red, cut-corner action button. Raised on a darker lip; hover
    fades the red in, press sinks the face onto the lip."""

    LIP = 3

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(180, 48)
        f = QFont(theme.FONT_HEAD)
        f.setPixelSize(19)
        self.setFont(f)
        self._hover = _Eased(self, 160)
        self._press = _Eased(self, 90)
        self.pressed.connect(lambda: self._press.to(1))
        self.released.connect(lambda: self._press.to(0))

    def enterEvent(self, event):
        self._hover.to(1)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover.to(0)
        super().leaveEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = QRectF(self.rect())
        sink = self.LIP * self._press.value
        face = full.adjusted(0, sink, 0, -self.LIP + sink)
        if not self.isEnabled():
            p.fillPath(chamfer_path(full.adjusted(0, self.LIP, 0, 0), theme.CHAMFER), QColor(theme.FAINT))
            fill, fg = QColor(theme.FAINT), QColor(theme.DIM)
        else:
            p.fillPath(chamfer_path(full.adjusted(0, self.LIP, 0, 0), theme.CHAMFER), QColor("#8A0410"))
            fill = mix(theme.RED, theme.RED_HOVER, self._hover.value)
            fg = QColor(theme.ON_RED)
        path = chamfer_path(face, theme.CHAMFER)
        p.fillPath(path, fill)
        if self.isEnabled():
            # Light from above: a faint sheen on the upper half of the face.
            sheen = QLinearGradient(0, face.top(), 0, face.center().y())
            sheen.setColorAt(0, QColor(255, 255, 255, 38))
            sheen.setColorAt(1, QColor(255, 255, 255, 0))
            p.fillPath(path, sheen)
        if self.hasFocus():
            p.setPen(QPen(QColor(theme.ON_RED), 1))
            p.drawPath(chamfer_path(face.adjusted(2.5, 2.5, -2.5, -2.5), theme.CHAMFER - 2))
        p.setPen(fg)
        p.setFont(self.font())
        p.drawText(face, Qt.AlignmentFlag.AlignCenter, self.text())


class FlatButton(QPushButton):
    """Secondary outline button, also used checkable for segmented choices
    (objectName 'seg'). Keeps the QSS size and font; paints its own frame so
    hover and checked states fade instead of snapping, and press dips the
    label a pixel over a hairline base."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = _Eased(self, 160)
        self._check = _Eased(self, 180)
        self.toggled.connect(lambda on: self._check.to(1.0 if on else 0.0))

    def setChecked(self, on: bool) -> None:
        super().setChecked(on)
        self._check.value = 1.0 if on else 0.0
        self.update()

    def enterEvent(self, event):
        self._hover.to(1)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover.to(0)
        super().leaveEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -1.5)
        h, c = self._hover.value, self._check.value
        if not self.isEnabled():
            border, fg, fill = QColor(theme.FAINT), QColor(theme.DIM), QColor(0, 0, 0, 0)
        else:
            idle_fg = theme.MUTED if self.objectName() == "seg" else theme.TEXT
            lift = max(h, 0.7) if self.hasFocus() else h
            border = mix(mix(theme.LINE, theme.WHITE, lift), theme.RED, c)
            fg = mix(mix(idle_fg, theme.WHITE, h), theme.WHITE, c)
            fill = mix(QColor(0, 0, 0, 0), QColor(theme.RED_DEEP), c)
            hover_fill = QColor(theme.WHITE)
            hover_fill.setAlphaF(0.05 * h * (1 - c))
            p.fillRect(rect, hover_fill)
        p.fillRect(rect, fill)
        # Base hairline: the button sits on a slightly darker edge.
        if self.isEnabled() and not self.isDown():
            p.setPen(QPen(QColor(0, 0, 0, 70), 1))
            p.drawLine(QPointF(rect.left() + 1, rect.bottom() + 1), QPointF(rect.right(), rect.bottom() + 1))
        p.setPen(QPen(border, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect)
        p.setPen(fg)
        p.setFont(self.font())
        p.drawText(rect.translated(0, 1 if self.isDown() else 0), Qt.AlignmentFlag.AlignCenter, self.text())


class TrashButton(QAbstractButton):
    """Small hand-drawn bin that removes one row from the queue. Grey at
    rest; under the cursor it fades to red and the lid lifts and tilts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Quitar de la cola")
        self.setFixedSize(28, 28)
        self._hover = _Eased(self, 150)

    def sizeHint(self):
        return QSize(28, 28)

    def enterEvent(self, event):
        self._hover.to(1)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover.to(0)
        super().leaveEvent(event)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self._hover.value
        pen = QPen(mix(theme.MUTED, theme.RED, h), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        cx, top = self.width() / 2, (self.height() - 14) / 2
        p.save()                                                             # lid + handle
        p.translate(cx + 6, top + 2.5)
        p.rotate(-14 * h)
        p.translate(0, -1.5 * h)
        p.drawLine(QPointF(-12, 0), QPointF(0, 0))
        p.drawLine(QPointF(-8, -2.5), QPointF(-4, -2.5))
        p.restore()
        body = QPainterPath()
        body.moveTo(cx - 4.5, top + 4.5)
        body.lineTo(cx - 3.5, top + 14)
        body.lineTo(cx + 3.5, top + 14)
        body.lineTo(cx + 4.5, top + 4.5)
        p.drawPath(body)
        for dx in (-1.5, 1.5):                                               # ribs
            p.drawLine(QPointF(cx + dx, top + 6.5), QPointF(cx + dx, top + 12))


class StatusMark(QWidget):
    """Small square swatch + label for the table's status column. `color`
    and `dot` are theme token names, resolved at paint time."""

    def __init__(self, color: str, text: str, parent=None, dot: str | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._color, self._dot, self._text = color, dot or color, text

    def text(self) -> str:
        return self._text

    def paintEvent(self, _event):
        p = QPainter(self)
        y = (self.height() - 8) / 2
        p.fillRect(QRectF(8, y, 8, 8), QColor(getattr(theme, self._dot)))
        p.setPen(QColor(getattr(theme, self._color)))
        p.setFont(self.font())
        p.drawText(QRectF(24, 0, self.width() - 32, self.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)


class ThemeSwitch(QWidget):
    """Light/dark switch in the window header, drawn as a terminal chip.
    Light: a steel plate with etched circuit traces. Dark: a black screen
    with a red neon grid and falling binary. The knob is a cut-corner chip
    with a blinking `>_` prompt that glitches (RGB split) while it slides.
    Clicking emits `changed('light'|'dark')`. All painted, no images."""

    changed = Signal(str)
    W, H = 78, 34

    # Fixed positions as fractions of the track, so nothing jumps between frames.
    _RAIN = ((0.10, 0.22, "1"), (0.10, 0.58, "0"), (0.22, 0.40, "0"), (0.22, 0.78, "1"),
             (0.34, 0.15, "1"), (0.34, 0.52, "1"), (0.46, 0.34, "0"), (0.46, 0.72, "0"),
             (0.58, 0.20, "1"), (0.58, 0.60, "0"))
    # Circuit traces (x0, y0, x1, y1), each ending in a square pad.
    _TRACES = ((0.48, 0.30, 0.70, 0.30), (0.70, 0.30, 0.78, 0.18),
               (0.52, 0.70, 0.88, 0.70), (0.88, 0.70, 0.94, 0.52),
               (0.62, 0.50, 0.82, 0.50))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(self.W, self.H)
        self._t = 1.0 if theme.MODE == "dark" else 0.0  # 0 light, 1 dark
        self._hover = False
        self._blink = True
        self._ticks = 0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(520)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._step)
        # The cursor blinks only for a moment after a switch, then stays solid.
        self._cursor = QTimer(self)
        self._cursor.setInterval(400)
        self._cursor.timeout.connect(self._tick)

    def _step(self, value):
        self._t = float(value)
        self.update()

    def _tick(self):
        self._ticks -= 1
        self._blink = not self._blink
        if self._ticks <= 0:
            self._cursor.stop()
            self._blink = True
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        mode = "light" if theme.MODE == "dark" else "dark"
        self._ticks = 6  # ~2.4 s at 400 ms
        self._blink = True
        self._cursor.start()
        self._anim.stop()
        self._anim.setStartValue(self._t)
        self._anim.setEndValue(1.0 if mode == "dark" else 0.0)
        self._anim.start()
        self.changed.emit(mode)

    @staticmethod
    def _mix(a: str, b: str, t: float) -> QColor:
        ca, cb = QColor(a), QColor(b)
        return QColor.fromRgbF(
            ca.redF() + (cb.redF() - ca.redF()) * t,
            ca.greenF() + (cb.greenF() - ca.greenF()) * t,
            ca.blueF() + (cb.blueF() - ca.blueF()) * t,
        )

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t, w, h = self._t, float(self.W), float(self.H)
        track = QRectF(1, 1, w - 2, h - 2)
        plate = chamfer_path(track, 8)
        red = QColor(theme.RED)

        # Screen: etched steel by day, near-black with a red cast by night.
        bg = QLinearGradient(0, track.top(), 0, track.bottom())
        bg.setColorAt(0, self._mix("#DCE0E6", "#050508", t))
        bg.setColorAt(1, self._mix("#B9C0CA", "#1A0609", t))
        p.fillPath(plate, bg)
        p.save()
        p.setClipPath(plate)
        p.setPen(Qt.PenStyle.NoPen)

        if t > 0:
            # Neon floor grid, lines converging on the horizon.
            horizon = track.top() + track.height() * 0.45
            grid = QColor(red)
            grid.setAlphaF(0.55 * t)
            p.setPen(QPen(grid, 0.8))
            vx = track.center().x()
            for i in range(-6, 7):
                p.drawLine(QPointF(vx + i * 3, horizon), QPointF(vx + i * 16, track.bottom()))
            for k in range(4):
                y = horizon + (track.bottom() - horizon) * (k / 4) ** 1.6
                p.drawLine(QPointF(track.left(), y), QPointF(track.right(), y))

            # Binary rain, dropping into place as the screen turns on.
            mono = QFont("Consolas")
            mono.setPixelSize(8)
            p.setFont(mono)
            rain = QColor(red.lighter(140))
            rain.setAlphaF(0.85 * t)
            p.setPen(rain)
            for rx, ry, ch in self._RAIN:
                p.drawText(QPointF(track.left() + rx * track.width(),
                                   track.top() + ry * track.height() - (1 - t) * 14 + 4), ch)
            p.setPen(Qt.PenStyle.NoPen)

        if t < 1:
            # Circuit traces etched in the steel, fading out at night.
            trace = QColor(40, 46, 56, int(170 * (1 - t)))
            p.setPen(QPen(trace, 1))
            for x0, y0, x1, y1 in self._TRACES:
                p.drawLine(QPointF(track.left() + x0 * track.width(), track.top() + y0 * track.height()),
                           QPointF(track.left() + x1 * track.width(), track.top() + y1 * track.height()))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(trace)
            for _x0, _y0, x1, y1 in self._TRACES:
                p.drawRect(QRectF(track.left() + x1 * track.width() - 1.5,
                                  track.top() + y1 * track.height() - 1.5, 3, 3))

        # CRT scanlines over the whole screen.
        p.setBrush(QColor(0, 0, 0, int(18 + 22 * t)))
        y = track.top()
        while y < track.bottom():
            p.drawRect(QRectF(track.left(), y, track.width(), 1))
            y += 3

        # Knob: a cut-corner chip that slides across.
        knob_d = track.height() - 6
        x0, x1 = track.left() + 3, track.right() - 3 - knob_d
        kx = x0 + (x1 - x0) * t
        chip = QRectF(kx, track.top() + 3, knob_d, knob_d)

        # Red glow the chip casts at night, then its drop shadow.
        glow = QColor(red)
        for k, a in ((3, 0.08), (2, 0.14), (1, 0.22)):
            glow.setAlphaF(a * t)
            p.setBrush(glow)
            p.drawPath(chamfer_path(chip.adjusted(-k * 2, -k * 2, k * 2, k * 2), 5 + k * 2))
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawPath(chamfer_path(chip.translated(0.8, 1.6), 5))

        face = QLinearGradient(chip.topLeft(), chip.bottomLeft())
        face.setColorAt(0, self._mix("#2A2E36", "#14080A", t))
        face.setColorAt(1, self._mix("#16181D", "#050505", t))
        p.setBrush(face)
        p.setPen(QPen(self._mix("#5A616D", theme.RED, t), 1))
        p.drawPath(chamfer_path(chip, 5))

        # Prompt. RGB split is slight at rest in the dark and spikes mid-slide.
        prompt = ">_" if self._blink else ">"
        f = QFont("Consolas")
        f.setPixelSize(int(knob_d * 0.48))
        f.setBold(True)
        p.setFont(f)
        split = 0.6 * t + 3.0 * math.sin(math.pi * t)
        align = Qt.AlignmentFlag.AlignCenter
        if split > 0.3:
            p.setPen(QColor(0, 240, 255, 170))
            p.drawText(chip.translated(-split, 0), align, prompt)
            p.setPen(QColor(255, 20, 60, 170))
            p.drawText(chip.translated(split, 0), align, prompt)
        p.setPen(self._mix("#9BE7A6", "#FFFFFF", t))
        p.drawText(chip, align, prompt)
        p.restore()

        # Rim: red when hovered.
        if self._hover:
            rim = red
        else:
            rim = QColor(255, 255, 255, 40) if t > 0.5 else QColor(0, 0, 0, 60)
        p.setPen(QPen(rim, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(plate)
