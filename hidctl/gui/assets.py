"""Carregamento dos assets locais (gerados por scripts/prepare_mouse_asset.py)."""

from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPainter

ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def load_image(name: str, assets_dir: Path | None = None) -> QImage | None:
    """Devolve a imagem ou ``None`` se o arquivo não existir ou for inválido."""
    image = QImage(str((assets_dir or ASSETS_DIR) / name))
    if image.isNull():
        return None
    return image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


def tinted(mask: QImage, color: str) -> QImage:
    """Pinta ``color`` usando o alfa de ``mask`` (o RGB da máscara é ignorado)."""
    result = QImage(mask.size(), QImage.Format.Format_ARGB32_Premultiplied)
    result.fill(QColor(color))
    painter = QPainter(result)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    painter.drawImage(0, 0, mask)
    painter.end()
    return result
