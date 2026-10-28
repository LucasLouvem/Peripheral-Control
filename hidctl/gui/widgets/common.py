"""Componentes pequenos compartilhados entre as seções."""

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from .. import icons, theme

ICON_SIZE = 18  # ícones dos títulos dos cartões (mesmo tamanho do texto de 13 px, com folga)


def repolish(widget: QWidget) -> None:
    """Reaplica a folha de estilo após mudar uma propriedade dinâmica."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("sectionLabel")
    font = label.font()
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
    label.setFont(font)
    return label


class Card(QFrame):
    """Cartão com borda e título (ícone + texto)."""

    def __init__(self, icon_name: str, title: str) -> None:
        super().__init__()
        self.setObjectName("card")
        self.title_row = QHBoxLayout()
        self.title_row.setSpacing(14)
        glyph = QLabel()
        glyph.setPixmap(icons.pixmap(icon_name, theme.TEXT_SOFT, ICON_SIZE))
        glyph.setFixedSize(ICON_SIZE, ICON_SIZE)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("cardTitle")
        self.title_row.addWidget(glyph)
        self.title_row.addWidget(self.title_label)
        self.title_row.addStretch(1)


class StatusDot(QWidget):
    def __init__(self, color: str, diameter: int = 12) -> None:
        super().__init__()
        self._color = QColor(color)
        self.setFixedSize(diameter, diameter)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(self.rect())


class RowButton(QPushButton):
    """Botão da barra lateral: só o ícone (compacto); o nome aparece como dica ao passar o mouse."""

    def __init__(self, object_name: str, icon_name: str, text: str, icon_size: int = 20) -> None:
        super().__init__()
        self.setObjectName(object_name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.icon_name = icon_name
        self._icon_size = icon_size
        self._text = text
        self.setToolTip(text)
        self.setAccessibleName(text)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.accent = QFrame()
        self.accent.setObjectName("accentBar")
        self.accent.setFixedWidth(4)
        self.accent.hide()
        layout.addWidget(self.accent)
        layout.addStretch(1)
        self.glyph = QLabel()
        self.glyph.setFixedSize(icon_size, icon_size)
        layout.addWidget(self.glyph)
        layout.addStretch(1)
        layout.addSpacing(4)  # compensa a barra de destaque para o ícone ficar centrado
        for child in (self.accent, self.glyph):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.set_active(False)

    def text(self) -> str:
        return self._text

    def set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.accent.setVisible(active)
        color = theme.RED_BRIGHT if active else theme.TEXT_SOFT
        self.glyph.setPixmap(icons.pixmap(self.icon_name, color, self._icon_size))
        repolish(self)


class Combo(QComboBox):
    """QComboBox com o chevron desenhado por nós (o QSS não cobre o ícone)."""

    def __init__(self, items: tuple[str, ...]) -> None:
        super().__init__()
        self.addItems(list(items))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        size = 14
        pixmap = icons.pixmap("chevron-down", theme.TEXT, size)
        painter.drawPixmap(self.width() - size - 8, (self.height() - size) // 2, pixmap)


class ColorDot(QAbstractButton):
    """Círculo de cor selecionável; o anel indica a seleção.

    Tem 44 px de largura ideal e encolhe até 32 px quando a janela é estreita.
    """

    FULL = 30
    SMALLEST = 22

    def __init__(self, name: str, color: str) -> None:
        super().__init__()
        self.color = color
        self.setCheckable(True)
        self.setToolTip(name)
        self.setAccessibleName(name)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(self.SMALLEST, self.FULL)
        self.setMaximumSize(self.FULL, self.FULL)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(self.FULL, self.FULL)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.3)
        center = QPointF(self.width() / 2, self.height() / 2)
        scale = min(self.width(), self.height()) / self.FULL
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self.color))
        painter.drawEllipse(center, 11.5 * scale, 11.5 * scale)
        if self.isChecked():
            ring = QColor(theme.RED_SELECTED_BORDER if self.color == "#fd2b2f" else self.color)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 2.0 * scale))
            painter.drawEllipse(center, 14.0 * scale, 14.0 * scale)


class ColorSwatch(QWidget):
    """Retângulo com a cor atual."""

    def __init__(self, color: str) -> None:
        super().__init__()
        self.color = color
        self.setMinimumSize(44, 30)
        self.setMaximumSize(84, 30)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(84, 30)

    def set_color(self, color: str) -> None:
        self.color = color
        self.update()

    def set_multicolor(self, on: bool) -> None:
        """Efeito multicolor (onda): a amostra mostra o arco-íris em vez de uma cor só."""
        self.multicolor = on
        self.update()

    multicolor = False

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.multicolor:
            gradient = QLinearGradient(0, 0, self.width(), 0)
            for i in range(7):
                gradient.setColorAt(i / 6, QColor.fromHsv(i * 50, 230, 255))
            painter.setBrush(gradient)
        else:
            painter.setBrush(QColor(self.color))
        painter.drawRoundedRect(QRectF(self.rect()), 5, 5)


class Toast(QLabel):
    """Aviso temporário sobre a janela (ex.: "Disponível futuramente")."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self.hide()

    def show_message(self, text: str, msec: int = 2800) -> None:
        self.setText(text)
        self.adjustSize()
        self.reposition()
        self.show()
        self.raise_()
        self._timer.start(msec)

    def reposition(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.move(
                (parent.width() - self.width()) // 2,
                parent.height() - self.height() - 70,
            )


class ReadonlyField(QLabel):
    """Campo de texto somente leitura com a aparência do seletor (sem permitir edição)."""

    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self.setObjectName("readonlyField")
