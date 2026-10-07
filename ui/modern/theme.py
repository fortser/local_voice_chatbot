"""Design tokens: change the palette here, not inside page implementations."""

COLORS = {
    "background": "#14191d", "sidebar": "#101518", "surface": "#1c2328",
    "raised": "#242d33", "border": "#303a40", "text": "#edf3f2",
    "muted": "#9cabb2", "accent": "#a8ebce", "ink": "#152c24",
    "error": "#ffafa8",
}


def stylesheet() -> str:
    c = COLORS
    return f"""
    QWidget {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 14px; }}
    QMainWindow, QWidget#root, QWidget#page {{ background: {c['background']}; }}
    QFrame#sidebar {{ background: {c['sidebar']}; border-right: 1px solid {c['border']}; }}
    QFrame[card='true'] {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 18px; }}
    QLabel {{ background: transparent; border: none; }}
    QLabel[role='muted'] {{ color: {c['muted']}; }}
    QLabel[role='eyebrow'] {{ color: {c['accent']}; font-size: 11px; font-weight: 600; letter-spacing: 2px; }}
    QLabel[role='title'] {{ font-size: 30px; font-weight: 600; }}
    QLabel[role='hero'] {{ font-size: 36px; font-weight: 600; }}
    QLabel[role='section'] {{ font-size: 18px; font-weight: 600; }}
    QLabel[role='error'] {{ color: {c['error']}; background: #362727; padding: 12px; border-radius: 8px; }}
    QPushButton {{ background: {c['raised']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 11px 16px; }}
    QPushButton:hover {{ background: #313e44; border-color: #677b7d; }}
    QPushButton:pressed {{ background: #394b50; }}
    QPushButton:disabled {{ color: #6f7c83; background: #1b2227; border-color: #293238; }}
    QPushButton:focus, QLineEdit:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
    QPushButton[role='primary'] {{ background: {c['accent']}; color: {c['ink']}; font-weight: 600; border-color: {c['accent']}; }}
    QPushButton[role='primary']:hover {{ background: #c6f6df; }}
    QPushButton[role='primary']:disabled {{ background: #34483e; color: #81998e; border-color: #34483e; }}
    QPushButton[role='nav'] {{ text-align: left; background: transparent; border: 1px solid transparent; padding: 14px 16px; color: {c['muted']}; }}
    QPushButton[role='nav']:checked {{ background: #25392f; color: {c['accent']}; border-color: #354e40; }}
    QPushButton[role='nav']:hover {{ background: #202a2b; }}
    QLineEdit, QComboBox, QTextBrowser, QListWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; padding: 12px; selection-background-color: #385e50; }}
    QComboBox QAbstractItemView {{ background: {c['raised']}; selection-background-color: #385e50; }}
    QListWidget::item {{ padding: 14px; border-bottom: 1px solid {c['border']}; }}
    QListWidget::item:selected {{ background: #2b443a; border-radius: 8px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: #405059; border-radius: 4px; min-height: 28px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QCheckBox {{ spacing: 10px; padding: 6px 0; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid #64776f; background: #242d33; }}
    QCheckBox::indicator:checked {{ background: {c['accent']}; border: 3px solid #527a66; }}
    QToolTip {{ background: {c['raised']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 6px; }}
    """
