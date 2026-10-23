"""Visual tokens. Black, white and one corporate red; nothing else.

Red only means "active": an enabled switch, the selected profile, the
primary action, a drop target under the cursor, an error. Everything at
rest is black, white or grey.

Type is Bahnschrift (ships with Windows 10/11, DIN-style): its condensed
widths carry headings, the regular width carries everything else.
"""
from __future__ import annotations

# Token names are roles, not literal colours: BLACK is the background and
# WHITE the strongest ink, so in the light theme BLACK is near-white and
# WHITE near-black. apply() swaps every token and rebuilds QSS; painted
# widgets read the module attributes at paint time, so they follow.
#
# Dark: charcoal, not pure black. True #000 only reads well on OLED; on IPS
# panels the backlight greys it and crushes the dark steps above it.
PALETTES = {
    "dark": {
        "BLACK": "#161616",
        "SURFACE": "#222222",    # panels on the background
        "LINE": "#3C3C3C",       # hairlines, idle borders, switch track off
        "FAINT": "#2A2A2A",      # row rules, progress track, disabled fills
        "DIM": "#646464",        # disabled text
        "MUTED": "#A8A8A8",      # secondary text
        "TEXT": "#F2F2F2",
        "WHITE": "#FFFFFF",
        "RED_HOVER": "#FF2233",
        "RED_DEEP": "#3D0A10",   # red-tinted fill behind active things
    },
    "light": {
        "BLACK": "#F3F3F1",
        "SURFACE": "#FFFFFF",
        "LINE": "#CFCFCF",
        "FAINT": "#E4E4E2",
        "DIM": "#A6A6A6",
        "MUTED": "#5C5C5C",
        "TEXT": "#1C1C1C",
        "WHITE": "#0A0A0A",
        "RED_HOVER": "#C20511",
        "RED_DEEP": "#FCE4E6",
    },
}
RED = "#E30613"
ON_RED = "#FFFFFF"  # text and marks drawn on a red fill, in both themes

MODE = "dark"
BLACK = SURFACE = LINE = FAINT = DIM = MUTED = TEXT = WHITE = RED_HOVER = RED_DEEP = ""

FONT = "Bahnschrift"
FONT_HEAD = "Bahnschrift SemiBold SemiCondensed"
FONT_CONDENSED = "Bahnschrift SemiLight SemiCondensed"

CHAMFER = 12  # cut-corner size, the one geometric signature of the app

def qss() -> str:
    return f"""
QWidget {{
    background: {BLACK};
    color: {TEXT};
    font-family: "{FONT}";
    font-size: 15px;
}}
QToolTip {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {LINE};
    padding: 6px;
}}
QLabel#title {{
    font-family: "{FONT_HEAD}";
    font-size: 36px;
    color: {WHITE};
}}
QLabel#tagline {{ color: {MUTED}; font-size: 15px; }}
QLabel#panelTitle {{
    font-family: "{FONT_HEAD}";
    font-size: 22px;
    color: {WHITE};
    background: transparent;
}}
QLabel#panelNote {{ color: {MUTED}; background: transparent; }}
QLabel#optTitle {{ font-size: 16px; color: {WHITE}; background: transparent; }}
QLabel#optDesc {{ font-size: 14px; color: {MUTED}; background: transparent; }}
QLabel#optTitle:disabled, QLabel#optDesc:disabled {{ color: {DIM}; }}
QLabel#fieldLabel {{ color: {MUTED}; font-size: 14px; }}
QLabel#dropMain {{
    font-family: "{FONT_CONDENSED}";
    font-size: 26px;
    color: {WHITE};
    background: transparent;
}}
QLabel#dropSub {{ color: {MUTED}; background: transparent; }}
QLabel#summary {{ color: {MUTED}; }}
QLabel#emptyQueue {{ color: {DIM}; font-size: 15px; background: {BLACK}; }}
QLabel#warn {{ color: {RED}; background: transparent; font-size: 14px; }}

#panel {{ background: {SURFACE}; }}

QLineEdit {{
    background: {SURFACE};
    border: none;
    border-bottom: 1px solid {LINE};
    padding: 8px 10px;
    color: {WHITE};
    selection-background-color: {RED};
}}
QLineEdit:focus {{ border-bottom: 1px solid {RED}; }}

QPushButton {{
    background: transparent;
    color: {TEXT};
    border: 1px solid {LINE};
    padding: 8px 16px;
}}
QPushButton:hover {{ border-color: {WHITE}; color: {WHITE}; }}
QPushButton:focus {{ border-color: {WHITE}; }}
QPushButton:disabled {{ color: {DIM}; border-color: {FAINT}; }}

QPushButton#seg {{
    border: 1px solid {LINE};
    padding: 7px 14px;
    color: {MUTED};
    background: transparent;
}}
QPushButton#seg:checked {{
    background: {RED_DEEP};
    border-color: {RED};
    color: {WHITE};
}}
QPushButton#seg:disabled {{ color: {DIM}; border-color: {FAINT}; background: transparent; }}

QTableWidget {{
    background: {BLACK};
    border: none;
    gridline-color: transparent;
    selection-background-color: {RED_DEEP};
    selection-color: {WHITE};
    outline: 0;
}}
QTableWidget::item {{ border-bottom: 1px solid {FAINT}; padding: 0 8px; }}
QTableWidget::item:selected {{ background: {RED_DEEP}; color: {WHITE}; }}
QHeaderView::section {{
    background: {BLACK};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {LINE};
    padding: 6px 8px;
    font-size: 14px;
}}
QScrollBar:vertical {{ background: {BLACK}; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {LINE}; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QProgressBar {{ background: {FAINT}; border: none; max-height: 2px; min-height: 2px; }}
QProgressBar::chunk {{ background: {RED}; }}

QCheckBox#pwShow {{ color: {MUTED}; background: transparent; }}
QCheckBox#pwShow::indicator {{ width: 14px; height: 14px; border: 1px solid {LINE}; }}
QCheckBox#pwShow::indicator:checked {{ background: {RED}; border-color: {RED}; }}
"""


def apply(mode: str) -> None:
    """Switch every colour token to `mode` ('dark' or 'light')."""
    global MODE
    MODE = mode
    globals().update(PALETTES[mode])


apply("dark")
