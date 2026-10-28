"""Modal de cor da iluminação: seletor, predefinições, hexadecimal, canais R, G, B e cores recentes.

Nunca acessa o mouse: só devolve (``accepted``) a cor escolhida a quem o abriu.
"""

from PySide6.QtCore import QPointF, QRectF, QRegularExpression, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPen,
    QRegularExpressionValidator,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import icons, theme
from .common import ColorDot, ColorSwatch

# (nome, cor) da paleta do cartão, amostradas da referência visual.
PALETTE: tuple[tuple[str, str], ...] = (
    ("Vermelho", "#fd2b2f"),
    ("Laranja", "#f98008"),
    ("Amarelo", "#f2e50e"),
    ("Verde", "#27e725"),
    ("Ciano", "#0be2f4"),
    ("Azul", "#0b6efe"),
    ("Roxo", "#6e24fb"),
    ("Rosa", "#f304e5"),
    ("Branco", "#f4f3f7"),
)
# Predefinições do modal: a paleta do cartão mais duas.
PRESETS: tuple[tuple[str, str], ...] = (
    PALETTE[:3] + (("Lima", "#8cf51a"),) + PALETTE[3:8] + (("Rosa claro", "#ff7ad9"),) + PALETTE[8:]
)


def to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % tuple(rgb)


def from_hex(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


class _Pad(QWidget):
    """Base dos controles arrastáveis: emite ``moved(x, y)`` com a posição normalizada (0-1)."""

    moved = Signal(float, float)

    def __init__(self) -> None:
        super().__init__()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _emit(self, event) -> None:
        pos = event.position()
        self.moved.emit(
            min(1.0, max(0.0, pos.x() / max(1, self.width()))),
            min(1.0, max(0.0, pos.y() / max(1, self.height()))),
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._emit(event)

    @staticmethod
    def _handle(painter: QPainter, center: QPointF) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#000000"), 3))
        painter.drawEllipse(center, 8, 8)
        painter.setPen(QPen(QColor("#ffffff"), 2))
        painter.drawEllipse(center, 8, 8)


class SaturationValueSquare(_Pad):
    """Quadrado de saturação (→) e brilho (↑) para o matiz atual."""

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(200, 170)
        self.hue, self.sat, self.val = 0, 255, 255

    def set_hsv(self, h: int, s: int, v: int) -> None:
        self.hue, self.sat, self.val = h, s, v
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor.fromHsv(self.hue, 255, 255))
        painter.drawRoundedRect(area, 8, 8)
        white = QLinearGradient(area.left(), 0, area.right(), 0)
        white.setColorAt(0, QColor(255, 255, 255, 255))
        white.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setBrush(QBrush(white))
        painter.drawRoundedRect(area, 8, 8)
        black = QLinearGradient(0, area.top(), 0, area.bottom())
        black.setColorAt(0, QColor(0, 0, 0, 0))
        black.setColorAt(1, QColor(0, 0, 0, 255))
        painter.setBrush(QBrush(black))
        painter.drawRoundedRect(area, 8, 8)
        self._handle(
            painter,
            QPointF(
                area.left() + area.width() * self.sat / 255,
                area.top() + area.height() * (1 - self.val / 255),
            ),
        )


class HueBar(_Pad):
    """Barra vertical de matiz (0 em cima)."""

    def __init__(self) -> None:
        super().__init__()
        self.setFixedWidth(22)
        self.hue = 0

    def set_hue(self, hue: int) -> None:
        self.hue = hue
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        gradient = QLinearGradient(0, area.top(), 0, area.bottom())
        for i in range(7):
            gradient.setColorAt(i / 6, QColor.fromHsv(0 if i == 6 else i * 60, 255, 255))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(area, 10, 10)
        self._handle(
            painter,
            QPointF(self.width() / 2, area.top() + area.height() * self.hue / 360),
        )


class LightingDialog(QDialog):
    """Edita uma única cor. ``rgb`` é a edição desta abertura; só ``accepted`` a entrega a quem abriu."""

    def __init__(
        self,
        rgb: tuple[int, int, int],
        parent=None,
        recent: tuple[tuple[int, int, int], ...] = (),
    ) -> None:
        super().__init__(parent)
        self.setObjectName("lightingDialog")
        self.setWindowTitle("Cor da iluminação")
        self.setModal(True)
        self._rgb = tuple(rgb)
        self._hue = max(0, QColor(*self._rgb).hsvHue())

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)
        body = QHBoxLayout()
        body.setSpacing(24)
        root.addLayout(body, 1)

        # ---- esquerda: abas "Cor sólida" e "Cores recentes"
        left = QVBoxLayout()
        left.setSpacing(12)
        tabs = QHBoxLayout()
        tabs.setSpacing(8)
        self.tab_group = QButtonGroup(self)
        self.solid_tab = self._tab("eyedropper", "Cor sólida", 0)
        self.recent_tab = self._tab("clock", "Cores recentes", 1)
        tabs.addWidget(self.solid_tab)
        tabs.addWidget(self.recent_tab)
        tabs.addStretch(1)
        left.addLayout(tabs)
        self.pages = QStackedWidget()
        picker = QWidget()
        picker_row = QHBoxLayout(picker)
        picker_row.setContentsMargins(0, 0, 0, 0)
        picker_row.setSpacing(14)
        self.square = SaturationValueSquare()
        self.hue_bar = HueBar()
        picker_row.addWidget(self.square, 1)
        picker_row.addWidget(self.hue_bar)
        self.pages.addWidget(picker)
        self.recent_dots: dict[tuple[int, int, int], ColorDot] = {}
        self.pages.addWidget(self._recent_page(recent))
        left.addWidget(self.pages, 1)
        body.addLayout(left, 3)

        # ---- direita: predefinições e cor atual
        right = QVBoxLayout()
        right.setSpacing(10)
        right.addWidget(self._heading("Predefinições"))
        grid = QGridLayout()
        grid.setSpacing(6)
        self.dots: dict[str, ColorDot] = {}
        for index, (name, color) in enumerate(PRESETS):
            dot = ColorDot(name, color)
            dot.clicked.connect(lambda _=False, value=color: self.set_rgb(from_hex(value)))
            self.dots[color] = dot
            grid.addWidget(dot, index // 6, index % 6)
        right.addLayout(grid)
        right.addSpacing(6)
        right.addWidget(self._heading("Cor atual"))
        current = QHBoxLayout()
        current.setSpacing(8)
        self.preview = ColorSwatch(to_hex(self._rgb))
        self.preview.setFixedSize(QSize(64, 40))
        self.hex_edit = QLineEdit()
        self.hex_edit.setObjectName("hexEdit")
        self.hex_edit.setValidator(
            QRegularExpressionValidator(QRegularExpression("#?[0-9a-fA-F]{0,6}"))
        )
        self.hex_edit.setAccessibleName("Hexadecimal")
        self.hex_edit.textEdited.connect(self._from_hex_text)
        self.hex_edit.editingFinished.connect(
            lambda: self.hex_edit.setText(to_hex(self._rgb).upper())
        )
        self.copy_button = QPushButton()
        self.copy_button.setObjectName("round")
        self.copy_button.setFixedSize(34, 34)
        self.copy_button.setIcon(icons.icon("copy", theme.TEXT, 16))
        self.copy_button.setIconSize(QSize(16, 16))
        self.copy_button.setToolTip("Copiar hexadecimal")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.clicked.connect(
            lambda: QApplication.clipboard().setText(to_hex(self._rgb).upper())
        )
        current.addWidget(self.preview)
        current.addWidget(self.hex_edit, 1)
        current.addWidget(self.copy_button)
        right.addLayout(current)
        self.spins: dict[str, QSpinBox] = {}
        for letter, value in zip("RGB", self._rgb):
            row = QHBoxLayout()
            label = QLabel(letter)
            label.setObjectName("cardCaption")
            label.setFixedWidth(16)
            spin = QSpinBox()
            spin.setRange(0, 255)
            spin.setValue(value)
            spin.setAccessibleName(letter)
            spin.valueChanged.connect(self._from_spins)
            self.spins[letter] = spin
            row.addWidget(label)
            row.addWidget(spin, 1)
            right.addLayout(row)
        right.addStretch(1)
        body.addLayout(right, 2)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setObjectName("outline")
        self.cancel_button.setMinimumWidth(110)
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button = QPushButton("Confirmar")
        self.confirm_button.setObjectName("apply")
        self.confirm_button.setMinimumWidth(110)
        self.confirm_button.clicked.connect(self.accept)
        self.confirm_button.setDefault(True)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.confirm_button)
        root.addLayout(buttons)

        self.square.moved.connect(
            lambda x, y: self._from_hsv(self._hue, round(x * 255), round((1 - y) * 255))
        )
        self.hue_bar.moved.connect(
            lambda _x, y: self._from_hsv(min(359, round(y * 360)), self.square.sat, self.square.val)
        )
        self.resize(600, 400)
        self._show(self._rgb)

    # ---------------------------------------------------------------- montagem

    def _tab(self, icon: str, text: str, page: int) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("tab")
        button.setCheckable(True)
        button.setIcon(icons.icon(icon, theme.TEXT_SOFT, 16))
        button.setIconSize(QSize(16, 16))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setChecked(page == 0)
        button.clicked.connect(lambda _=False: self.pages.setCurrentIndex(page))
        self.tab_group.addButton(button)
        return button

    @staticmethod
    def _heading(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("dialogHeading")
        return label

    def _recent_page(self, recent) -> QWidget:
        page = QWidget()
        layout = QGridLayout(page)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(8)
        for index, rgb in enumerate(recent):
            dot = ColorDot(to_hex(rgb), to_hex(rgb))
            dot.clicked.connect(lambda _=False, value=rgb: self.set_rgb(value))
            self.recent_dots[rgb] = dot
            layout.addWidget(dot, index // 8, index % 8)
        if not recent:
            empty = QLabel("Nenhuma cor recente")
            empty.setObjectName("cardCaption")
            layout.addWidget(empty, 0, 0)
        layout.setRowStretch(layout.rowCount(), 1)
        layout.setColumnStretch(8, 1)
        return page

    # ---------------------------------------------------------------- estado

    @property
    def rgb(self) -> tuple[int, int, int]:
        return self._rgb

    def set_rgb(self, rgb: tuple[int, int, int]) -> None:
        self._show(tuple(rgb))

    def _from_spins(self) -> None:
        self._show((self.spins["R"].value(), self.spins["G"].value(), self.spins["B"].value()))

    def _from_hex_text(self, text: str) -> None:
        digits = text.lstrip("#")
        if len(digits) == 6:
            self._show(from_hex("#" + digits), keep_hex_text=True)

    def _from_hsv(self, h: int, s: int, v: int) -> None:
        color = QColor.fromHsv(h, s, v)
        self._hue = h
        self._show((color.red(), color.green(), color.blue()), hsv=(h, s, v))

    def _show(
        self,
        rgb: tuple[int, int, int],
        hsv: tuple[int, int, int] | None = None,
        keep_hex_text: bool = False,
    ) -> None:
        self._rgb = rgb
        if hsv is None:
            color = QColor(*rgb)
            h, s, v = color.hsvHue(), color.hsvSaturation(), color.value()
            if h >= 0 and s > 0 and v > 0:  # em cinza/preto o matiz não existe: mantém o anterior
                self._hue = h
            hsv = (self._hue, s, v)
        for letter, value in zip("RGB", rgb):
            spin = self.spins[letter]
            if spin.value() != value:
                spin.blockSignals(True)
                spin.setValue(value)
                spin.blockSignals(False)
        self.square.set_hsv(*hsv)
        self.hue_bar.set_hue(hsv[0])
        self.preview.set_color(to_hex(rgb))
        if not keep_hex_text:
            self.hex_edit.setText(to_hex(rgb).upper())
        for color, dot in self.dots.items():
            dot.setChecked(from_hex(color) == rgb)
        for value, dot in self.recent_dots.items():
            dot.setChecked(value == rgb)
