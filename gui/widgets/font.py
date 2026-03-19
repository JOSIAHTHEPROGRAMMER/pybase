from PyQt6.QtGui import QFont, QFontDatabase


def get_mono_font(size: int = 12) -> QFont:
    """
    Return the first available monospace font from a priority list.
    Falls back to the system default monospace if none are found.
    Qt does not support CSS-style comma-separated font fallbacks.
    """
    preferred = ["JetBrains Mono", "Cascadia Code", "Cascadia Mono", "Consolas", "Courier New"]
    available = QFontDatabase.families()

    for name in preferred:
        if name in available:
            return QFont(name, size)

    # Last resort - system default monospace
    font = QFont()
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(size)
    return font