"""Cartões da tela inicial: DPI e iluminação (ambos reais)."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...devices.fc30_mouse import lighting
from .. import icons, theme
from ..dpi_model import DpiModel
from .common import Card, ColorDot, ColorSwatch, Combo, repolish
from .levels import LevelColumn
from .lighting_dialog import PALETTE, LightingDialog, from_hex

EFFECT_CHOICES = (("Estático", lighting.Effect.STATIC), ("Onda", lighting.Effect.WAVE))
UNKNOWN_COLOR = "#2c3033"  # amostra enquanto a iluminação real não foi lida


class DpiCard(Card):
    """Os 5 níveis do perfil ativo como sliders verticais; só o estado local muda ao arrastar."""

    def __init__(self, model: DpiModel) -> None:
        super().__init__("crosshair", "DPI")
        self._model = model
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 8)
        layout.setSpacing(0)

        self.reload_button = QPushButton("Recarregar do mouse")
        self.reload_button.setObjectName("outline")
        self.reload_button.setToolTip("Lê o estado atual do mouse (somente leitura).")
        self.reload_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reload_button.clicked.connect(model.reload)
        self.title_row.addWidget(self.reload_button)
        layout.addLayout(self.title_row)
        layout.addSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.columns = [LevelColumn(level, model) for level in range(5)]
        for column in self.columns:
            row.addWidget(column, 1)
        layout.addLayout(row, 1)
        layout.addSpacing(2)

        model.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        for column in self.columns:
            column.refresh()
        self.reload_button.setEnabled(not self._model.busy)


class ClickableSwatch(ColorSwatch):
    """Amostra de cor que abre o modal ao ser clicada."""

    clicked = Signal()

    def __init__(self, color: str) -> None:
        super().__init__(color)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Cor da iluminação")

    def mouseReleaseEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self.isEnabled()
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class LightingCard(Card):
    """Efeito, cor e velocidade da iluminação do perfil exibido. Tudo é local até "Salvar".

    A paleta aplica uma cor pronta; o conta-gotas abre o modal para uma cor que não está nela.
    """

    def __init__(self, model: DpiModel) -> None:
        super().__init__("bulb", "Iluminação")
        self._model = model
        self.dialog: LightingDialog | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 12)
        layout.setSpacing(0)

        self.effect = Combo([name for name, _ in EFFECT_CHOICES])
        self.effect.setFixedWidth(120)
        self.effect.setPlaceholderText("")
        self.effect.activated.connect(self._effect_chosen)
        self.title_row.addWidget(self.effect)
        layout.addLayout(self.title_row)
        layout.addSpacing(10)

        colors = QHBoxLayout()
        colors.setSpacing(0)
        self.swatch = ClickableSwatch(UNKNOWN_COLOR)
        self.swatch.clicked.connect(self.open_dialog)
        colors.addWidget(self.swatch, 0)
        colors.addSpacing(16)
        self.dots: dict[str, ColorDot] = {}
        dots = QHBoxLayout()
        dots.setSpacing(0)
        for name, color in PALETTE:
            dot = ColorDot(name, color)
            dot.clicked.connect(lambda _=False, value=color: self._model.set_light(from_hex(value)))
            self.dots[color] = dot
            dots.addWidget(dot)
            dots.addStretch(1)
        self.eyedropper = QPushButton()
        self.eyedropper.setObjectName("round")
        self.eyedropper.setFixedSize(30, 30)
        self.eyedropper.setIcon(icons.icon("eyedropper", theme.TEXT, 16))
        self.eyedropper.setIconSize(QSize(16, 16))
        self.eyedropper.setToolTip("Outra cor")
        self.eyedropper.setCursor(Qt.CursorShape.PointingHandCursor)
        self.eyedropper.clicked.connect(self.open_dialog)
        dots.addWidget(self.eyedropper)
        colors.addLayout(dots, 9)
        layout.addLayout(colors)

        # Velocidade da onda: o aparelho usa 1 = rápida … 8 = lenta; o controle cresce para a direita = mais rápido.
        self.speed_row = QWidget()
        speed = QHBoxLayout(self.speed_row)
        speed.setContentsMargins(0, 10, 0, 0)
        speed.setSpacing(10)
        slow, fast = QLabel("Devagar"), QLabel("Rápido")
        for label in (slow, fast):
            label.setObjectName("cardCaption")
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, len(lighting.SPEEDS))
        self.speed_slider.setFixedHeight(18)
        self.speed_slider.valueChanged.connect(self._speed_moved)
        speed.addWidget(slow)
        speed.addWidget(self.speed_slider, 1)
        speed.addWidget(fast)
        layout.addWidget(self.speed_row)
        layout.addStretch(1)

        model.changed.connect(self.refresh)
        self.refresh()

    # slider 1..8 (direita = rápido)  <->  velocidade do aparelho 8..1
    @staticmethod
    def _to_slider(speed: int) -> int:
        return len(lighting.SPEEDS) + 1 - speed

    _from_slider = _to_slider

    def _effect_chosen(self, index: int) -> None:
        self._model.set_light_effect(EFFECT_CHOICES[index][1])

    def _speed_moved(self, value: int) -> None:
        self._model.set_light_speed(self._from_slider(value))

    def open_dialog(self) -> None:
        """Abre o modal com a configuração pendente (ou a do mouse). Nada é enviado ao aparelho."""
        rgb = self._model.light_rgb
        if rgb is None or self._model.busy or self.dialog is not None:
            return
        dialog = LightingDialog(rgb, self.window(), self._model.recent.colors)
        dialog.accepted.connect(lambda: self._chosen(dialog.rgb))
        dialog.finished.connect(self._closed)
        self.dialog = dialog
        dialog.open()

    def _chosen(self, rgb: tuple[int, int, int]) -> None:
        self._model.set_light(rgb)
        self._model.recent.add(rgb)

    def _closed(self) -> None:
        if self.dialog is not None:
            self.dialog.deleteLater()
            self.dialog = None

    def refresh(self) -> None:
        model = self._model
        loaded = model.light_rgb is not None
        usable = loaded and not model.busy
        effect = model.light_effect
        static = effect is lighting.Effect.STATIC
        wave = effect is lighting.Effect.WAVE
        self.swatch.set_color(model.light_hex or UNKNOWN_COLOR)
        self.swatch.set_multicolor(wave)
        self.swatch.setEnabled(usable)
        for color, dot in self.dots.items():
            dot.setChecked(static and model.light_rgb == from_hex(color))
            dot.setEnabled(usable)
        self.eyedropper.setEnabled(usable)
        names = [choice for _, choice in EFFECT_CHOICES]
        self.effect.blockSignals(True)
        self.effect.setCurrentIndex(names.index(effect) if effect in names else -1)
        self.effect.setPlaceholderText(model.light_effect_name or "")
        self.effect.blockSignals(False)
        self.effect.setEnabled(usable)
        self.effect.setProperty("edited", model.light_edit is not None)
        repolish(self.effect)
        self.speed_row.setVisible(wave)
        self.speed_slider.setEnabled(usable)
        if wave and model.light_speed in lighting.SPEEDS:
            self.speed_slider.blockSignals(True)
            self.speed_slider.setValue(self._to_slider(model.light_speed))
            self.speed_slider.blockSignals(False)
