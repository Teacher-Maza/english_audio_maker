from __future__ import annotations

"""Pure visual tokens for the Tkinter UI.

This module deliberately has no imports from app.core or any audio/runtime
package.  Keeping visual constants here prevents a theme change from touching
generation contracts or loading heavy dependencies.
"""


COLOR_HEADER = "#011641"
COLOR_HEADER_BOTTOM = "#00163F"
COLOR_HEADER_TEXT_MUTED = "#C9D7EE"
COLOR_NAV_TEXT = "#D9E5FA"
COLOR_NAV_HOVER = "#0A2859"
COLOR_NAV_PRESSED = "#0D326C"
COLOR_APP_BG = "#F7F8FA"
COLOR_SURFACE = "#FFFFFF"
COLOR_SURFACE_ALT = "#F8FAFC"
COLOR_BORDER = "#D8E0EA"
COLOR_BORDER_STRONG = "#C7D2E0"
COLOR_TEXT = "#0F172A"
COLOR_MUTED = "#475569"
COLOR_SUBTLE = "#64748B"
COLOR_PRIMARY = "#057E33"
COLOR_PRIMARY_HOVER = "#046B2B"
COLOR_PRIMARY_PRESSED = "#035A24"
COLOR_PRIMARY_SOFT = "#EAF7EF"
COLOR_SECONDARY = "#1A45A5"
COLOR_SECONDARY_HOVER = "#143797"
COLOR_SECONDARY_SOFT = "#EEF4FF"
COLOR_SECONDARY_PRESSED_SOFT = "#DCE8FF"
COLOR_DANGER = "#DC2626"
COLOR_DANGER_HOVER = "#B91C1C"
COLOR_DANGER_SOFT = "#FEF2F2"
COLOR_WARNING = "#D97706"
COLOR_DISABLED_BG = "#E5E7EB"
COLOR_DISABLED_TEXT = "#94A3B8"
COLOR_PROGRESS_TROUGH = "#E7ECF2"
COLOR_STATUS_BORDER = "#A8DDBB"
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

HEADER_HEIGHT = 74
ACTION_BAR_HEIGHT = 72
FOOTER_HEIGHT = 28

WINDOW_TARGET_WIDTH = 1440
WINDOW_TARGET_HEIGHT = 800
WINDOW_MIN_WIDTH = 1180
WINDOW_MIN_HEIGHT = 700
WINDOW_SCREEN_FRACTION = 0.94


MODE_THEMES = {
    "Narração": {
        "primary": COLOR_PRIMARY,
        "hover": COLOR_PRIMARY_HOVER,
        "pressed": COLOR_PRIMARY_PRESSED,
        "accent": "#BDE8CD",
        "focus": "#7CD49D",
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
        "accent": "#CFE1FF",
        "focus": "#93B8FF",
        "surface": COLOR_SURFACE,
        "background": COLOR_APP_BG,
        "text": COLOR_TEXT,
        "secondary_text": COLOR_MUTED,
        "border": COLOR_BORDER,
        "progress": COLOR_SECONDARY,
        "button_text": COLOR_WHITE,
    },
}
