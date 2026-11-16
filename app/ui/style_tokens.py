from __future__ import annotations

"""Pure visual tokens for the Tkinter UI.

This module deliberately has no imports from app.core or any audio/runtime
package.  Keeping visual constants here prevents a theme change from touching
generation contracts or loading heavy dependencies.
"""


COLOR_HEADER = "#DCE5DA"
COLOR_HEADER_BOTTOM = "#DCE5DA"
COLOR_HEADER_TEXT_MUTED = "#52665A"
COLOR_NAV_TEXT = "#26372F"
COLOR_NAV_HOVER = "#E7EDE3"
COLOR_NAV_PRESSED = "#CCDACC"
COLOR_APP_BG = "#E4EADF"
COLOR_SURFACE = "#FFFFFF"
COLOR_SURFACE_ALT = "#F4F3ED"
COLOR_DIALOGUE_SURFACE = "#DDE8E4"
COLOR_BORDER = "#BECABB"
COLOR_BORDER_STRONG = "#A2B49F"
COLOR_TEXT = "#26372F"
COLOR_MUTED = "#4F6257"
COLOR_SUBTLE = "#5B6D61"
COLOR_PRIMARY = "#285B50"
COLOR_PRIMARY_HOVER = "#326D5F"
COLOR_PRIMARY_PRESSED = "#1D473E"
COLOR_PRIMARY_SOFT = "#E3ECE0"
COLOR_SECONDARY = "#285B50"
COLOR_SECONDARY_HOVER = "#1D473E"
COLOR_SECONDARY_SOFT = "#E7EDE3"
COLOR_SECONDARY_PRESSED_SOFT = "#D1DFCC"
COLOR_DANGER = "#DC2626"
COLOR_DANGER_HOVER = "#B91C1C"
COLOR_DANGER_SOFT = "#FEF2F2"
COLOR_WARNING = "#D97706"
COLOR_DISABLED_BG = "#E1E5DD"
COLOR_DISABLED_TEXT = "#687469"
COLOR_PROGRESS_TROUGH = "#DEE4D9"
COLOR_STATUS_BORDER = "#BACBB5"
COLOR_WHITE = "#FFFFFF"

FONT_UI = "Segoe UI"
FONT_SYMBOL = "Segoe UI Symbol"
FONT_MONO = "Consolas"

SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 24

# Dense spacing is reserved for the taller A/B settings form.  Font sizes and
# controls stay unchanged; only internal whitespace is reduced.
COMPACT_PANEL_PADDING = 8
COMPACT_SECTION_GAP = 4
COMPACT_FIELD_GAP = 2
COMPACT_BUTTON_PADDING = (10, 4)
COMPACT_ENTRY_PADDING = 3
COMPACT_COMBO_PADDING = 2

HEADER_HEIGHT = 58
ACTION_BAR_HEIGHT = 72
FOOTER_HEIGHT = 28

WINDOW_TARGET_WIDTH = 1280
WINDOW_TARGET_HEIGHT = 800
WINDOW_MIN_WIDTH = 1000
WINDOW_MIN_HEIGHT = 680
WINDOW_SCREEN_FRACTION = 0.94


MODE_THEMES = {
    "Narração": {
        "primary": COLOR_PRIMARY,
        "hover": COLOR_PRIMARY_HOVER,
        "pressed": COLOR_PRIMARY_PRESSED,
        "accent": "#CEE3CA",
        "focus": "#285B50",
        "surface": COLOR_SURFACE,
        "background": COLOR_APP_BG,
        "text": COLOR_TEXT,
        "secondary_text": COLOR_MUTED,
        "border": COLOR_BORDER,
        "progress": COLOR_PRIMARY,
        "button_text": COLOR_WHITE,
    },
    "Conversação A/B": {
        "primary": COLOR_PRIMARY,
        "hover": COLOR_PRIMARY_HOVER,
        "pressed": COLOR_PRIMARY_PRESSED,
        "accent": "#CEE3CA",
        "focus": "#285B50",
        "surface": COLOR_SURFACE,
        "background": COLOR_APP_BG,
        "text": COLOR_TEXT,
        "secondary_text": COLOR_MUTED,
        "border": COLOR_BORDER,
        "progress": COLOR_SECONDARY,
        "button_text": COLOR_WHITE,
    },
}
