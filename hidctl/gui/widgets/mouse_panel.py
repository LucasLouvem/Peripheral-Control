"""Ilustração do mouse em destaque, com o brilho acompanhando cor e intensidade."""

from pathlib import Path

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from .. import assets, theme
from ..dpi_model import DpiModel

# Em 70% o brilho reproduz a referência; acima disso a cor é reforçada.
REFERENCE_BRIGHTNESS = 70
UNKNOWN_GLOW = "#555a5e"  # cor do brilho enquanto a iluminação real não foi lida
DISPLAY_LIMIT = QSize(150, 236)  # ~43% do tamanho nativo


class MouseView(QWidget):
    """Desenha base + camada de brilho tingida, mantendo a proporção da imagem."""

    def __init__(self, model: DpiModel, assets_dir: Path | None = None) -> None:
        super().__init__()
        self._model = model
        self._base = assets.load_image("king_cobra_2_base.png", assets_dir)
        self._glow = assets.load_image("king_cobra_2_glow.png", assets_dir)
        self._cache_key: tuple | None = None
        self._cache: QImage | None = None
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(100, 150)
        model.changed.connect(self.update)

    @property
    def has_image(self) -> bool:
        return self._base is not None and self._glow is not None

    def image_rect(self) -> QRect:
        """Retângulo (em px lógicos) ocupado pela imagem, centrado no widget."""
        if not self.has_image:
            return self.rect()
        # Tamanho máximo reduzido (a arte nativa tem ~350×550 px): o mouse é só um detalhe da tela.
        limit = self.size().boundedTo(DISPLAY_LIMIT)
        size = self._base.size().scaled(limit, Qt.AspectRatioMode.KeepAspectRatio)
        return QRect(
            (self.width() - size.width()) // 2,
            (self.height() - size.height()) // 2,
            size.width(),
            size.height(),
        )

    def sizeHint(self) -> QSize:
        return QSize(150, 236)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.has_image:
            self._paint_placeholder(painter)
            return
        target = self.image_rect()
        dpr = self.devicePixelRatioF()
        image = self._composed(QSize(round(target.width() * dpr), round(target.height() * dpr)))
        image.setDevicePixelRatio(dpr)
        painter.drawImage(target.topLeft(), image)

    def _paint_placeholder(self, painter: QPainter) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(theme.OUTLINE), 1, Qt.PenStyle.DashLine))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(20, 20, -20, -20), 12, 12)
        painter.setPen(QColor(theme.TEXT_DIM))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Imagem do mouse indisponível")

    def _composed(self, size: QSize) -> QImage:
        color = self._model.light_hex or UNKNOWN_GLOW
        brightness = self._model.light_brightness_percent
        key = (size.width(), size.height(), color, brightness)
        if key == self._cache_key and self._cache is not None:
            return self._cache
        smooth = Qt.TransformationMode.SmoothTransformation
        result = self._base.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
        glow = self._glow.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, smooth)
        layer = assets.tinted(glow, color)
        painter = QPainter(result)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        intensity = brightness / REFERENCE_BRIGHTNESS
        while intensity > 0:
            painter.setOpacity(min(1.0, intensity))
            painter.drawImage(0, 0, layer)
            intensity -= 1.0
        painter.end()
        self._cache_key, self._cache = key, result
        return result


class MousePanel(QWidget):
    """Coluna esquerda, parte de cima: só a ilustração do mouse (o nome está no cabeçalho)."""

    def __init__(self, model: DpiModel, assets_dir: Path | None = None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = MouseView(model, assets_dir)
        layout.addWidget(self.view, 1)
