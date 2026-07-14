from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "users": """
        <circle cx="9" cy="8" r="3"/>
        <path d="M3.5 19v-1.5A4.5 4.5 0 0 1 8 13h2a4.5 4.5 0 0 1 4.5 4.5V19"/>
        <path d="M15 5.5a3 3 0 0 1 0 5.5m2 2a4 4 0 0 1 3.5 4V19"/>
    """,
    "inbox": """
        <path d="M4 5h16l2 9v5H2v-5z"/><path d="M2.5 14H8l1.5 2h5l1.5-2h5.5"/>
    """,
    "warning": """
        <path d="M10.3 3.8 2.5 18a2 2 0 0 0 1.8 3h15.4a2 2 0 0 0 1.8-3L13.7 3.8a2 2 0 0 0-3.4 0z"/>
        <path d="M12 9v4m0 4h.01"/>
    """,
    "check": '<path d="m5 12 4 4L19 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
    "globe": """
        <circle cx="12" cy="12" r="9"/>
        <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>
    """,
    "refresh": """
        <path d="M20 7v5h-5M4 17v-5h5"/>
        <path d="M6.1 8a7 7 0 0 1 11.7-2.2L20 8m-16 8 2.2 2.2A7 7 0 0 0 17.9 16"/>
    """,
    "download": """
        <path d="M12 3v12m0 0-4.5-4.5M12 15l4.5-4.5"/>
        <path d="M4 18v2h16v-2"/>
    """,
    "sparkles": """
        <path d="m12 2 1.4 4.1L17.5 7.5l-4.1 1.4L12 13l-1.4-4.1-4.1-1.4 4.1-1.4z"/>
        <path d="m19 13 .8 2.2L22 16l-2.2.8L19 19l-.8-2.2L16 16l2.2-.8z"/>
        <path d="m5 14 1.1 3L9 18l-2.9 1L5 22l-1.1-3L1 18l2.9-1z"/>
    """,
    "filter": """
        <path d="M3 5h18l-7 8v6l-4 2v-8z"/>
    """,
    "bolt": """
        <path d="M13 2 4.5 13H11l-1 9 8.5-12H12z"/>
    """,
    "mail": """
        <rect x="3" y="5" width="18" height="14" rx="2"/>
        <path d="m4 7 8 6 8-6"/>
    """,
    "mail-plus": """
        <rect x="3" y="5" width="15" height="14" rx="2"/>
        <path d="m4 7 6.5 5 6.5-5M20 13v8m-4-4h8"/>
    """,
    "folder": """
        <path d="M3 8h18v9.5A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z"/>
        <path d="M3 8V6.5A1.5 1.5 0 0 1 4.5 5H9l3 3"/>
    """,
    "import": """
        <path d="M4 12.5v5.5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5.5"/>
        <path d="M12 3v11m0 0-4-4m4 4 4-4"/>
    """,
    "paste": """
        <rect x="5" y="5" width="14" height="16" rx="2"/>
        <path d="M9 5V3h6v2M9 10h6m-6 4h6m-6 4h4"/>
    """,
    "export": """
        <path d="M4 11.5V18a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-6.5"/>
        <path d="M12 15V4m0 0L8 8m4-4 4 4"/>
    """,
    "play": '<path d="M8 5.5v13l10-6.5z" fill="{color}" stroke="none"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="{color}" stroke="none"/>',
    "moon": '<path d="M19 15.5A8 8 0 0 1 8.5 5a8.2 8.2 0 1 0 10.5 10.5z"/>',
    "sun": """
        <circle cx="12" cy="12" r="3.5"/>
        <path d="M12 2v2m0 16v2M2 12h2m16 0h2"/>
        <path d="M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4"/>
        <path d="m19.1 4.9-1.4 1.4M6.3 17.7l-1.4 1.4"/>
    """,
    "settings": """
        <path d="M4 6h5m4 0h7M4 12h9m4 0h3M4 18h2m4 0h10"/>
        <circle cx="11" cy="6" r="2"/>
        <circle cx="15" cy="12" r="2"/>
        <circle cx="8" cy="18" r="2"/>
    """,
    "tools": """
        <path d="M14.5 6.5a4 4 0 0 0-5-5l2.2 2.2-2 2-2.2-2.2a4 4 0 0 0 5 5L20 16l-4 4-7.5-7.5"/>
    """,
    "audit": """
        <path d="M12 2.5 19 5v5.8c0 4.4-2.8 8.3-7 10.7-4.2-2.4-7-6.3-7-10.7V5z"/>
        <path d="m8.7 12 2.1 2.1 4.6-4.6"/>
    """,
}


def line_icon(name: str, color: str = "#64748b", size: int = 20) -> QIcon:
    path = _PATHS[name].format(color=color)
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
      <g fill="none" stroke="{color}" stroke-width="1.8"
         stroke-linecap="round" stroke-linejoin="round">{path}</g>
    </svg>
    """
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    canvas_size = max(size * 2, 32)
    pixmap = QPixmap(canvas_size, canvas_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, canvas_size, canvas_size))
    painter.end()
    pixmap.setDevicePixelRatio(canvas_size / size)
    return QIcon(pixmap)
