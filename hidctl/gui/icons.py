"""Ícones de traço desenhados em SVG inline e renderizados com QSvgRenderer."""

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

# Corpos SVG em grade 24×24 (traço arredondado, sem preenchimento).
_BODIES: dict[str, str] = {
    "home": '<path d="M3 11.5 12 4l9 7.5M5.5 10v10.5h4.5v-6h4v6h4.5V10"/>',
    "crosshair": (
        '<circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="1.2"/>'
        '<path d="M12 2.5v5M12 16.5v5M2.5 12h5M16.5 12h5"/>'
    ),
    "bulb": (
        '<path d="M9.5 18.5h5M10.5 21.5h3"/>'
        '<path d="M12 2.5a6.5 6.5 0 0 0-3.8 11.8c.8.6 1.3 1.4 1.3 2.2h5c0-.8.5-1.6 1.3-2.2A6.5 6.5 0 0 0 12 2.5Z"/>'
    ),
    "document": ('<path d="M6 3h8l5 5v13H6Z"/><path d="M14 3v5h5M9 13h7M9 17h7"/>'),
    "macro": (
        '<path d="M7 7.5V3.5h9.5L20 7v10.5h-3"/><path d="M4 7.5h9l3 3v10H4Z"/>'
        '<path d="M7 14h6M7 17.5h6"/>'
    ),
    "gear": (
        '<circle cx="12" cy="12" r="3.2"/><circle cx="12" cy="12" r="7"/>'
        '<path d="M12 2.5v2.5M12 19v2.5M2.5 12H5M19 12h2.5M5.3 5.3l1.8 1.8M16.9 16.9l1.8 1.8M5.3 18.7l1.8-1.8M16.9 7.1l1.8-1.8"/>'
    ),
    "mouse": (
        '<rect x="6.5" y="2.5" width="11" height="19" rx="5.5"/><path d="M12 2.5v6.5M6.5 9h11"/>'
    ),
    "pencil": '<path d="m4 20 1-4.2L16.3 4.5a2 2 0 0 1 2.8 0l.4.4a2 2 0 0 1 0 2.8L8.2 19Z"/><path d="m14.5 6.3 3.2 3.2"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "chevron-right": '<path d="m9 5.5 6.5 6.5L9 18.5"/>',
    "chevron-down": '<path d="m5.5 9 6.5 6.5L18.5 9"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h9"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "eyedropper": (
        '<path d="m4 20 .8-3.6L14.6 6.6l2.8 2.8L7.6 19.2Z"/>'
        '<path d="m13.5 7.5 3 3M15.5 5.5l2.6-2.6a2 2 0 0 1 2.8 2.8l-2.6 2.6"/>'
    ),
}

ICON_NAMES = tuple(_BODIES)


@lru_cache(maxsize=256)
def pixmap(name: str, color: str, size: int, dpr: float = 2.0, stroke: float = 1.7) -> QPixmap:
    """Renderiza o ícone ``name`` com ``color`` em ``size`` px lógicos."""
    if name not in _BODIES:
        raise KeyError(f"Ícone desconhecido: {name!r}")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{_BODIES[name]}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    target = QPixmap(round(size * dpr), round(size * dpr))
    target.setDevicePixelRatio(dpr)
    target.fill(Qt.GlobalColor.transparent)
    painter = QPainter(target)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return target


def icon(name: str, color: str, size: int = 24) -> QIcon:
    return QIcon(pixmap(name, color, size))
