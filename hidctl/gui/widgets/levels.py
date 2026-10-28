"""Colunas de nível (slider vertical + valor embaixo), no estilo do software de referência."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QSizePolicy, QSlider, QVBoxLayout, QWidget

from ...devices.fc30_mouse import values
from .. import theme
from ..dpi_model import DpiModel
from .common import repolish

MAX_SLIDER_HEIGHT = 300
CHECK_TOOLTIP = "Mostra se o nível está habilitado no mouse. Habilitar ou desabilitar níveis não está disponível nesta versão."


class LevelCheck(QWidget):
    """Caixa vermelha de "nível habilitado" (somente leitura), como na referência."""

    def __init__(self) -> None:
        super().__init__()
        self.checked = False
        self.setFixedSize(16, 16)
        self.setToolTip(CHECK_TOOLTIP)

    def set_checked(self, value: bool) -> None:
        self.checked = value
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(16, 16)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self.checked:
            painter.setPen(QPen(QColor(theme.RED), 1.5))
            painter.setBrush(QColor(theme.RED_SELECTED_BG))
            painter.drawRoundedRect(rect, 4, 4)
            painter.setPen(
                QPen(
                    QColor(theme.RED),
                    2.2,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
            painter.drawPolyline(
                [
                    QPointF(x + w * 0.24, y + h * 0.52),
                    QPointF(x + w * 0.43, y + h * 0.72),
                    QPointF(x + w * 0.78, y + h * 0.28),
                ]
            )
        else:
            painter.setPen(QPen(QColor(theme.OUTLINE), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, 4, 4)


class LevelColumn(QWidget):
    """Um nível: etiqueta ATIVO, caixa de habilitado, slider vertical e o valor embaixo.

    O slider tem um passo por valor liberado (``values.writable_values()``); arrastar só edita
    o estado local. Nada é enviado ao mouse daqui.
    """

    def __init__(self, level: int, model: DpiModel) -> None:
        super().__init__()
        self.level = level
        self._model = model
        self._options = values.writable_values()
        self._refreshing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.check = LevelCheck()
        self.slider = QSlider(Qt.Orientation.Vertical)
        self.slider.setObjectName("levelSlider")
        self.slider.setRange(0, len(self._options) - 1)
        self.slider.setPageStep(1)
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setMinimumHeight(60)
        self.slider.setMaximumHeight(MAX_SLIDER_HEIGHT)
        self.slider.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.slider.setFixedWidth(22)
        self.slider.valueChanged.connect(self._moved)
        self.value_label = QLabel()
        self.value_label.setObjectName("levelValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption = QLabel(str(level + 1))
        self.caption.setObjectName("levelCaption")
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center = Qt.AlignmentFlag.AlignHCenter
        layout.addWidget(self.check, 0, center)
        layout.addWidget(self.slider, 100, center)
        layout.addWidget(self.value_label)
        layout.addWidget(self.caption)
        layout.addStretch(
            1
        )  # sobra de altura (slider no limite) fica embaixo, sem afastar as etiquetas

    def _index_for(self, value: int | None, estimate: int) -> int:
        if value is not None:
            return [o.nominal for o in self._options].index(value)
        return min(
            range(len(self._options)),
            key=lambda i: abs(self._options[i].nominal - estimate),
        )

    def _moved(self, index: int) -> None:
        if self._refreshing:
            return
        try:
            self._model.set_value(self.level, self._options[index].nominal)
        except ValueError:
            self.refresh()

    def refresh(self) -> None:
        model, snap = self._model, self._model.loaded
        view = snap.levels[self.level] if snap else None
        self._refreshing = True
        try:
            if view is None:
                self.slider.setValue(0)
                self.value_label.setText("—")
                self.check.set_checked(False)
                self.slider.setEnabled(False)
                self.slider.setToolTip("")
            else:
                value = model.value_of(self.level)
                self.slider.setValue(self._index_for(value, view.estimate))
                self.slider.setEnabled(view.editable and not model.busy)
                self.check.set_checked(view.enabled)
                entry = values.by_nominal(value) if value is not None else None
                if not view.enabled:
                    text, tip = "—", "Nível desabilitado no mouse."
                elif entry is None:
                    text = f"≈{view.estimate}*"
                    tip = "Valor não validado: o código foi lido, mas não foi testado por este programa."
                elif entry.evidence is values.Evidence.TESTED_PERCEIVED:
                    text, tip = (
                        str(entry.nominal),
                        f"{entry.nominal} DPI: testado no aparelho (gravado, relido e percebido).",
                    )
                else:
                    text, tip = (
                        str(entry.nominal),
                        f"{entry.nominal} DPI: gravado e relido no aparelho, sem medição física do DPI.",
                    )
                self.value_label.setText(text)
                self.slider.setToolTip(tip)
        finally:
            self._refreshing = False
        active = snap is not None and model.active_level == self.level
        edited = self.level in model.edits
        self.value_label.setToolTip("Nível ativo no mouse" if active else "")
        for widget, key, state in (
            (self.value_label, "active", active),
            (self.value_label, "edited", edited),
            (
                self.slider,
                "unvalidated",
                bool(view and view.enabled and model.value_of(self.level) is None),
            ),
        ):
            widget.setProperty(key, state)
            repolish(widget)
        name = f"Nível {self.level + 1}: {self.value_label.text()}"
        if active:
            name += ", ativo no mouse"
        if edited:
            name += ", alterado e não salvo"
        self.slider.setAccessibleName(name)
