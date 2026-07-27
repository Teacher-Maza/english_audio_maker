from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable

from v2_kokoro.app.core.dialogue_parser import parse_dialogue_ab
from v2_kokoro.app.core.generation_contracts import (
    GenerationRequest,
    MODE_DIALOGUE_AB,
    MODE_NARRATION,
)
from v2_kokoro.app.core.speech_speed import (
    SPEECH_SPEED_FAST,
    SPEECH_SPEED_NORMAL,
    SPEECH_SPEED_SLOW,
)
from v2_kokoro.app.core.output_location import current_output_directory, save_selected_output_directory, validate_output_directory
from v2_kokoro.app.core.progress_events import ProgressEvent
from v2_kokoro.app.core.project_paths import V2_ROOT, load_paths
from v2_kokoro.app.core.resource_manager import PROFILE_AUTOMATIC, PROFILE_BALANCED, PROFILE_ECONOMIC, evaluate_resources
from v2_kokoro.app.core.validators import MAX_INPUT_FILE_BYTES, PROJECT_RE, validate_text_content
from v2_kokoro.app.ui.audio_preview import PreviewError, PreviewPlayer
from v2_kokoro.app.ui.style_tokens import (
    ACTION_BAR_HEIGHT,
    COLOR_APP_BG,
    COLOR_BORDER,
    COLOR_BORDER_STRONG,
    COLOR_DANGER,
    COLOR_DANGER_HOVER,
    COLOR_DANGER_SOFT,
    COLOR_DISABLED_BG,
    COLOR_DISABLED_TEXT,
    COLOR_HEADER,
    COLOR_HEADER_TEXT_MUTED,
    COLOR_NAV_HOVER,
    COLOR_NAV_PRESSED,
    COLOR_NAV_TEXT,
    COLOR_MUTED,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_PRIMARY_PRESSED,
    COLOR_PRIMARY_SOFT,
    COLOR_PROGRESS_TROUGH,
    COLOR_SECONDARY,
    COLOR_SECONDARY_HOVER,
    COLOR_SECONDARY_PRESSED_SOFT,
    COLOR_SECONDARY_SOFT,
    COLOR_SUBTLE,
    COLOR_STATUS_BORDER,
    COLOR_SURFACE,
    COLOR_SURFACE_ALT,
    COLOR_TEXT,
    COLOR_WHITE,
    COMPACT_BUTTON_PADDING,
    COMPACT_COMBO_PADDING,
    COMPACT_ENTRY_PADDING,
    COMPACT_FIELD_GAP,
    COMPACT_PANEL_PADDING,
    COMPACT_SECTION_GAP,
    FONT_MONO,
    FONT_SYMBOL,
    FONT_UI,
    FOOTER_HEIGHT,
    HEADER_HEIGHT,
    MODE_THEMES,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_4,
    SPACE_5,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_SCREEN_FRACTION,
    WINDOW_TARGET_HEIGHT,
    WINDOW_TARGET_WIDTH,
)
from v2_kokoro.app.ui.ui_helpers import progress_label


MODE_NARRATION_LABEL = "Narração"
MODE_DIALOGUE_LABEL = "Conversação A/B"
MODE_MAP = {MODE_NARRATION_LABEL: MODE_NARRATION, MODE_DIALOGUE_LABEL: MODE_DIALOGUE_AB}
DISABLED_BG = COLOR_DISABLED_BG
DISABLED_TEXT = COLOR_DISABLED_TEXT
STAGE_LABELS = {
    "validating": "Validando pedido",
    "preparing": "Preparando arquivos",
    "synthesizing": "Gerando voz",
    "assembling_wav": "Montando WAV final",
    "creating_mp3": "Criando MP3",
    "waiting_resources": "Aguardando recursos com seguranca",
    "saving_log": "Salvando log seguro",
    "paused": "Pausado",
    "completed": "Concluído",
    "cancelled": "Cancelado",
    "error": "Erro",
}
PROFILE_LABELS = {"Automatico (recomendado)": PROFILE_AUTOMATIC, "Econômico": PROFILE_ECONOMIC, "Equilibrado": PROFILE_BALANCED}
SPEECH_SPEED_LABELS = {"Devagar": SPEECH_SPEED_SLOW, "Normal": SPEECH_SPEED_NORMAL, "Rápido": SPEECH_SPEED_FAST}


class ShadowButton(tk.Canvas):
    """Primary action with stable sizing and keyboard-visible focus."""

    def __init__(self, parent: tk.Widget, *, text: str, command: Callable[[], None], **kwargs) -> None:
        super().__init__(parent, height=44, highlightthickness=2, bd=0, takefocus=True, cursor="hand2", **kwargs)
        self._text = text
        self._command = command
        self._state = "normal"
        self._hovered = False
        self._pressed = False
        self._palette = {
            "background": COLOR_PRIMARY,
            "hover": COLOR_PRIMARY_HOVER,
            "pressed": COLOR_PRIMARY_PRESSED,
            "foreground": COLOR_WHITE,
            "shadow": None,
        }
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", lambda _event: self.invoke())
        self.bind("<space>", lambda _event: self.invoke())
        self.bind("<FocusIn>", lambda _event: self.configure(highlightbackground=COLOR_WHITE, highlightcolor=COLOR_WHITE))
        self.bind("<FocusOut>", lambda _event: self.configure(highlightbackground=COLOR_PRIMARY, highlightcolor=COLOR_PRIMARY))
        self.configure(highlightbackground=COLOR_PRIMARY, highlightcolor=COLOR_PRIMARY)
        self._draw()

    def set_palette(self, *, background: str, hover: str, pressed: str, foreground: str, shadow: str | None) -> None:
        self._palette = {
            "background": background,
            "hover": hover,
            "pressed": pressed,
            "foreground": foreground,
            "shadow": shadow,
        }
        self._draw()

    def configure(self, cnf=None, **kwargs):
        if "state" in kwargs:
            self._state = kwargs.pop("state")
        if "text" in kwargs:
            self._text = kwargs.pop("text")
        result = super().configure(cnf, **kwargs)
        self._draw()
        return result

    config = configure

    def cget(self, key: str):
        if key == "state":
            return self._state
        if key == "text":
            return self._text
        return super().cget(key)

    def invoke(self) -> None:
        if self._state != "disabled":
            self._command()

    def _on_enter(self, _event) -> None:
        if self._state != "disabled":
            self._hovered = True
            self._draw()

    def _on_leave(self, _event) -> None:
        self._hovered = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event) -> None:
        if self._state != "disabled":
            self._pressed = True
            self._draw()

    def _on_release(self, _event) -> None:
        should_invoke = self._state != "disabled" and self._pressed and self._hovered
        self._pressed = False
        self._draw()
        if should_invoke:
            self._command()

    def _draw(self) -> None:
        width = max(self.winfo_width(), self.winfo_reqwidth(), 1)
        height = max(self.winfo_height(), self.winfo_reqheight(), 1)
        if self._state == "disabled":
            background, foreground, shadow = DISABLED_BG, DISABLED_TEXT, None
        elif self._pressed:
            background, foreground, shadow = self._palette["pressed"], self._palette["foreground"], self._palette["shadow"]
        elif self._hovered:
            background, foreground, shadow = self._palette["hover"], self._palette["foreground"], self._palette["shadow"]
        else:
            background, foreground, shadow = self._palette["background"], self._palette["foreground"], self._palette["shadow"]
        self.delete("all")
        self.create_rectangle(0, 0, width, height, fill=background, outline=background)
        if shadow:
            self.create_text(width // 2 + 1, height // 2 + 1, text=self._text, fill=shadow, font=(FONT_UI, 10, "bold"))
        self.create_text(width // 2, height // 2, text=self._text, fill=foreground, font=(FONT_UI, 10, "bold"))


class KokoroV2Window:
    def __init__(
        self,
        root: tk.Tk,
        *,
        job_runner: Callable | None = None,
        preview_player: PreviewPlayer | None = None,
        resource_checker: Callable | None = None,
        folder_chooser: Callable[[Path], str] | None = None,
        folder_opener: Callable[[str], None] | None = None,
    ) -> None:
        self.root = root
        self.job_runner = job_runner
        self.preview = preview_player or PreviewPlayer()
        self.event_queue: queue.Queue = queue.Queue()
        self.is_running = False
        self.cancel_event: threading.Event | None = None
        self.pause_event: threading.Event | None = None
        self.paths = load_paths()
        self.output_directory = current_output_directory()
        self.resource_checker = resource_checker or (
            lambda profile_id: evaluate_resources(profile_id, output_dir=self.output_directory)
        )
        self.folder_chooser = folder_chooser or self._choose_folder_dialog
        self.folder_opener = folder_opener or getattr(os, "startfile", None)
        self.voices = self._load_voices()
        self.voice_ids = [item["voice_id"] for item in self.voices]
        self.voice_by_id = {item["voice_id"]: item for item in self.voices}
        self.voice_display_values = [item["display_label"] for item in self.voices]
        self.voice_id_by_display = {item["display_label"]: item["voice_id"] for item in self.voices}
        self.preview_rows: dict[str, tuple[ttk.Frame, ttk.Label, ttk.Label, ttk.Button]] = {}

        self.project_var = tk.StringVar(value="")
        self.mode_var = tk.StringVar(value=MODE_NARRATION_LABEL)
        self.narration_voice_var = tk.StringVar(value="")
        self.voice_a_var = tk.StringVar(value="")
        self.voice_b_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Pronto. Escolha o modo, as vozes e informe o texto.")
        self.output_var = tk.StringVar(value="")
        self.output_directory_var = tk.StringVar(value=str(self.output_directory))
        self.progress_stage_var = tk.StringVar(value="Aguardando")
        self.progress_item_var = tk.StringVar(value="")
        self.progress_percent_var = tk.StringVar(value="0%")
        self.progress_value = tk.DoubleVar(value=0.0)
        self.preview_status_var = tk.StringVar(value="Nenhuma prévia ativa.")
        self.mode_status_var = tk.StringVar(value="")
        self.profile_var = tk.StringVar(value="Automatico (recomendado)")
        self.speed_var = tk.StringVar(value="Normal")
        self.resource_status_var = tk.StringVar(value="Recursos serão verificados antes de gerar.")

        self._configure_root()
        self._configure_styles()
        self._build_ui()
        self.mode_var.trace_add("write", self._on_mode_changed)
        self.project_var.trace_add("write", self._on_project_changed)
        self._apply_mode_theme()
        self._update_mode_controls()
        self._refresh_output_preview()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(100, self._poll_events)
        self.root.after(400, self._poll_preview)

    def _load_voices(self) -> list[dict]:
        data = json.loads(self.paths["voices_catalog"].read_text(encoding="utf-8"))
        if data.get("default_voice_id") is not None:
            raise ValueError("A UI V2 não aceita voz padrão")
        voices = data.get("voices", [])
        if len(voices) != 28:
            raise ValueError("A UI V2 exige as 28 vozes validadas")
        prepared = []
        for source in voices:
            voice = dict(source)
            metadata = voice.get("review_metadata", {})
            name = metadata.get("display_name") or voice["voice_id"].split("_", 1)[-1].replace("_", " ").title()
            gender = metadata.get("gender") or "Não classificada"
            accent = metadata.get("accent") or "Não classificada"
            favorite = metadata.get("favorite") is True
            voice["display_name"] = name
            voice["favorite"] = favorite
            voice["display_label"] = f'{"★ " if favorite else ""}{name} — {gender} — {accent}'
            prepared.append(voice)
        return sorted(prepared, key=lambda item: (not item["favorite"], item["display_name"].casefold()))

    def _configure_root(self) -> None:
        self.root.title("English Audio Maker V2 — B2 Official")
        self.root.iconbitmap(default=str(V2_ROOT / "app" / "ui" / "assets" / "app_icon.ico"))
        screen_width = max(1, self.root.winfo_screenwidth())
        screen_height = max(1, self.root.winfo_screenheight())
        width = min(WINDOW_TARGET_WIDTH, max(WINDOW_MIN_WIDTH, int(screen_width * WINDOW_SCREEN_FRACTION)))
        height = min(WINDOW_TARGET_HEIGHT, max(WINDOW_MIN_HEIGHT, int(screen_height * WINDOW_SCREEN_FRACTION)))
        width = min(width, screen_width)
        height = min(height, screen_height)
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min(WINDOW_MIN_WIDTH, width), min(WINDOW_MIN_HEIGHT, height))
        self.root.configure(background=COLOR_APP_BG)
        self.root.rowconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)

    def _configure_styles(self) -> None:
        self.style = ttk.Style(self.root)
        self.style.theme_use("clam")
        style = self.style
        style.configure(".", font=(FONT_UI, 9), background=COLOR_APP_BG, foreground=COLOR_TEXT)
        style.configure("V2.App.TFrame", background=COLOR_APP_BG)
        style.configure("V2.Card.TFrame", background=COLOR_SURFACE, bordercolor=COLOR_BORDER, relief="solid", borderwidth=1)
        style.configure("V2.Card.TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT)
        style.configure("V2.CardTitle.TLabel", background=COLOR_SURFACE, foreground=COLOR_PRIMARY, font=(FONT_UI, 11, "bold"))
        style.configure("V2.Section.TLabel", background=COLOR_SURFACE, foreground=COLOR_PRIMARY, font=(FONT_UI, 10, "bold"))
        style.configure("V2.Field.TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT, font=(FONT_UI, 9))
        style.configure("V2.Muted.TLabel", background=COLOR_SURFACE, foreground=COLOR_MUTED, font=(FONT_UI, 9))
        style.configure("V2.Footer.TFrame", background=COLOR_SURFACE_ALT)
        style.configure("V2.Footer.TLabel", background=COLOR_SURFACE_ALT, foreground=COLOR_SUBTLE, font=(FONT_UI, 8))
        style.configure("V2.ActionBar.TFrame", background=COLOR_SURFACE, bordercolor=COLOR_BORDER, relief="solid", borderwidth=1)
        style.configure("V2.Nav.TButton", background=COLOR_HEADER, foreground=COLOR_NAV_TEXT, borderwidth=0, padding=(15, 11), font=(FONT_UI, 10, "bold"))
        style.map("V2.Nav.TButton", background=[("active", COLOR_NAV_HOVER), ("pressed", COLOR_NAV_PRESSED)], foreground=[("active", COLOR_WHITE)])
        style.configure("V2.NavActive.TButton", background=COLOR_SURFACE, foreground=COLOR_PRIMARY, borderwidth=0, padding=(15, 11), font=(FONT_UI, 10, "bold"))
        style.map("V2.NavActive.TButton", background=[("active", COLOR_SURFACE_ALT), ("pressed", COLOR_PRIMARY_SOFT)], foreground=[("active", COLOR_PRIMARY)])
        style.configure("V2.Primary.TButton", background=COLOR_PRIMARY, foreground=COLOR_WHITE, bordercolor=COLOR_PRIMARY, padding=(18, 10), font=(FONT_UI, 10, "bold"))
        style.map("V2.Primary.TButton", background=[("pressed", COLOR_PRIMARY_PRESSED), ("active", COLOR_PRIMARY_HOVER), ("disabled", COLOR_DISABLED_BG)], foreground=[("disabled", COLOR_DISABLED_TEXT)])
        style.configure("V2.Secondary.TButton", background=COLOR_SURFACE, foreground=COLOR_SECONDARY, bordercolor=COLOR_BORDER_STRONG, padding=(14, 9), font=(FONT_UI, 9, "bold"))
        style.map("V2.Secondary.TButton", background=[("pressed", COLOR_SECONDARY_SOFT), ("active", COLOR_SECONDARY_SOFT), ("disabled", COLOR_DISABLED_BG)], foreground=[("disabled", COLOR_DISABLED_TEXT)])
        style.configure("V2.Compact.Secondary.TButton", background=COLOR_SURFACE, foreground=COLOR_SECONDARY, bordercolor=COLOR_BORDER_STRONG, padding=COMPACT_BUTTON_PADDING, font=(FONT_UI, 9, "bold"))
        style.map("V2.Compact.Secondary.TButton", background=[("pressed", COLOR_SECONDARY_SOFT), ("active", COLOR_SECONDARY_SOFT), ("disabled", COLOR_DISABLED_BG)], foreground=[("disabled", COLOR_DISABLED_TEXT)])
        style.configure("V2.Danger.TButton", background=COLOR_SURFACE, foreground=COLOR_DANGER, bordercolor=COLOR_BORDER_STRONG, padding=(14, 9), font=(FONT_UI, 9, "bold"))
        style.map("V2.Danger.TButton", background=[("pressed", COLOR_DANGER_SOFT), ("active", COLOR_DANGER_SOFT), ("disabled", COLOR_DISABLED_BG)], foreground=[("active", COLOR_DANGER_HOVER), ("disabled", COLOR_DISABLED_TEXT)])
        style.configure("V2.Icon.TButton", background=COLOR_SURFACE, foreground=COLOR_SECONDARY, bordercolor=COLOR_BORDER, padding=(7, 5), font=(FONT_SYMBOL, 10, "bold"))
        style.map("V2.Icon.TButton", background=[("active", COLOR_SECONDARY_SOFT), ("pressed", COLOR_SECONDARY_PRESSED_SOFT)], foreground=[("disabled", COLOR_DISABLED_TEXT)])
        style.configure("V2.Status.TFrame", background=COLOR_PRIMARY_SOFT, bordercolor=COLOR_STATUS_BORDER, relief="solid", borderwidth=1)
        style.configure("V2.Status.TLabel", background=COLOR_PRIMARY_SOFT, foreground=COLOR_PRIMARY, font=(FONT_UI, 9, "bold"))
        style.configure("V2.PreviewRow.TFrame", background=COLOR_SURFACE_ALT)
        style.configure("V2.PreviewRow.TLabel", background=COLOR_SURFACE_ALT, foreground=COLOR_TEXT)
        style.configure("V2.PreviewMeta.TLabel", background=COLOR_SURFACE_ALT, foreground=COLOR_SUBTLE, font=(FONT_UI, 8))
        style.configure("V2.PreviewPlaying.TFrame", background=COLOR_PRIMARY_SOFT)
        style.configure("V2.PreviewPlaying.TLabel", background=COLOR_PRIMARY_SOFT, foreground=COLOR_PRIMARY, font=(FONT_UI, 9, "bold"))
        style.configure("V2.PreviewPlayingMeta.TLabel", background=COLOR_PRIMARY_SOFT, foreground=COLOR_PRIMARY, font=(FONT_UI, 8))
        style.configure("V2.Horizontal.TProgressbar", troughcolor=COLOR_PROGRESS_TROUGH, background=COLOR_PRIMARY, bordercolor=COLOR_PROGRESS_TROUGH, lightcolor=COLOR_PRIMARY, darkcolor=COLOR_PRIMARY)
        style.configure("TCombobox", fieldbackground=COLOR_SURFACE, background=COLOR_SURFACE, foreground=COLOR_TEXT, arrowcolor=COLOR_SECONDARY, bordercolor=COLOR_BORDER, lightcolor=COLOR_BORDER, darkcolor=COLOR_BORDER, padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", COLOR_SURFACE), ("disabled", COLOR_DISABLED_BG)], foreground=[("readonly", COLOR_TEXT), ("disabled", COLOR_DISABLED_TEXT)], selectbackground=[("readonly", COLOR_SECONDARY_SOFT)])
        style.configure("V2.Compact.TCombobox", fieldbackground=COLOR_SURFACE, background=COLOR_SURFACE, foreground=COLOR_TEXT, arrowcolor=COLOR_SECONDARY, bordercolor=COLOR_BORDER, lightcolor=COLOR_BORDER, darkcolor=COLOR_BORDER, padding=COMPACT_COMBO_PADDING)
        style.map("V2.Compact.TCombobox", fieldbackground=[("readonly", COLOR_SURFACE), ("disabled", COLOR_DISABLED_BG)], foreground=[("readonly", COLOR_TEXT), ("disabled", COLOR_DISABLED_TEXT)], selectbackground=[("readonly", COLOR_SECONDARY_SOFT)])
        for voice_style, voice_padding in (("V2.Voice.TCombobox", 4), ("V2.CompactVoice.TCombobox", COMPACT_COMBO_PADDING)):
            style.configure(voice_style, fieldbackground=COLOR_PRIMARY, background=COLOR_PRIMARY, foreground=COLOR_WHITE, arrowcolor=COLOR_WHITE, bordercolor=COLOR_PRIMARY, lightcolor=COLOR_PRIMARY, darkcolor=COLOR_PRIMARY, padding=voice_padding)
            style.map(
                voice_style,
                fieldbackground=[("disabled", COLOR_DISABLED_BG), ("pressed", COLOR_PRIMARY_PRESSED), ("focus", COLOR_PRIMARY_PRESSED), ("active", COLOR_PRIMARY_HOVER), ("readonly", COLOR_PRIMARY)],
                background=[("disabled", COLOR_DISABLED_BG), ("pressed", COLOR_PRIMARY_PRESSED), ("focus", COLOR_PRIMARY_PRESSED), ("active", COLOR_PRIMARY_HOVER), ("readonly", COLOR_PRIMARY)],
                foreground=[("disabled", COLOR_DISABLED_TEXT), ("readonly", COLOR_WHITE)],
                arrowcolor=[("disabled", COLOR_DISABLED_TEXT), ("readonly", COLOR_WHITE)],
                selectbackground=[("readonly", COLOR_PRIMARY_HOVER)],
                selectforeground=[("readonly", COLOR_WHITE)],
            )
        style.configure("TEntry", fieldbackground=COLOR_SURFACE, foreground=COLOR_TEXT, insertcolor=COLOR_PRIMARY, bordercolor=COLOR_BORDER, lightcolor=COLOR_BORDER, darkcolor=COLOR_BORDER, padding=6)
        style.configure("V2.Compact.TEntry", fieldbackground=COLOR_SURFACE, foreground=COLOR_TEXT, insertcolor=COLOR_PRIMARY, bordercolor=COLOR_BORDER, lightcolor=COLOR_BORDER, darkcolor=COLOR_BORDER, padding=COMPACT_ENTRY_PADDING)
        style.configure("V2.Hidden.TNotebook", background=COLOR_APP_BG, borderwidth=0, tabmargins=0)
        style.layout("V2.Hidden.TNotebook.Tab", [])
        style.layout("V2.Hidden.TNotebook", [("Notebook.client", {"sticky": "nswe"})])

    def _panel(self, parent: tk.Widget, title: str, *, compact: bool = False) -> ttk.Frame:
        panel = ttk.Frame(parent, style="V2.Card.TFrame", padding=COMPACT_PANEL_PADDING if compact else SPACE_4)
        panel.columnconfigure(0, weight=1)
        title_gap = COMPACT_SECTION_GAP if compact else SPACE_3
        ttk.Label(panel, text=title.upper(), style="V2.CardTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, title_gap))
        return panel

    def _section_heading(self, parent: tk.Widget, row: int, text: str, *, compact: bool = False) -> None:
        section_gap = COMPACT_SECTION_GAP if compact else SPACE_3
        label_gap = COMPACT_SECTION_GAP if compact else SPACE_2
        ttk.Separator(parent).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(section_gap, section_gap))
        ttk.Label(parent, text=text.upper(), style="V2.Section.TLabel").grid(row=row + 1, column=0, columnspan=2, sticky="w", pady=(0, label_gap))

    @staticmethod
    def _build_brand_mark(parent: tk.Widget) -> tk.Canvas:
        canvas = tk.Canvas(parent, width=48, height=46, background=COLOR_HEADER, highlightthickness=0, bd=0)
        canvas.create_rectangle(6, 4, 42, 42, fill=COLOR_WHITE, outline=COLOR_WHITE)
        canvas.create_line(11, 29, 23, 34, 23, 39, 11, 34, 11, 29, fill=COLOR_SECONDARY, width=2)
        canvas.create_line(37, 29, 25, 34, 25, 39, 37, 34, 37, 29, fill=COLOR_SECONDARY, width=2)
        for x, height in ((15, 10), (20, 16), (25, 22), (30, 15), (35, 9)):
            canvas.create_line(x, 27, x, 27 - height, fill=COLOR_PRIMARY, width=3)
        return canvas

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, background=COLOR_HEADER, height=HEADER_HEIGHT)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.columnconfigure(1, weight=1)
        self.brand_mark = self._build_brand_mark(header)
        self.brand_mark.grid(row=0, column=0, rowspan=2, sticky="w", padx=(SPACE_5, SPACE_3), pady=SPACE_3)
        tk.Label(header, text="English Audio Maker V2", background=COLOR_HEADER, foreground=COLOR_WHITE, font=(FONT_UI, 18, "bold")).grid(row=0, column=1, sticky="sw", pady=(10, 0))
        tk.Label(header, text="Local e offline · Texto em inglês · Kokoro · MP3", background=COLOR_HEADER, foreground=COLOR_HEADER_TEXT_MUTED, font=(FONT_UI, 9)).grid(row=1, column=1, sticky="nw", pady=(0, 10))

        nav = tk.Frame(header, background=COLOR_HEADER)
        nav.grid(row=0, column=2, rowspan=2, sticky="e", padx=(SPACE_4, SPACE_5), pady=SPACE_3)
        self.nav_buttons = {
            MODE_NARRATION_LABEL: ttk.Button(nav, text="●  Narração", command=lambda: self.set_mode(MODE_NARRATION_LABEL)),
            MODE_DIALOGUE_LABEL: ttk.Button(nav, text="◉  Conversação A/B", command=lambda: self.set_mode(MODE_DIALOGUE_LABEL)),
            "Samples": ttk.Button(nav, text="▥  Samples de vozes", command=self._show_samples),
        }
        for column, button in enumerate(self.nav_buttons.values()):
            button.grid(row=0, column=column, padx=(0 if column == 0 else SPACE_2, 0), sticky="ns")

        self.body = ttk.Frame(self.root, style="V2.App.TFrame", padding=(SPACE_3, SPACE_3, SPACE_3, SPACE_2))
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.rowconfigure(0, weight=1)
        self.body.columnconfigure(0, weight=75, uniform="main")
        self.body.columnconfigure(1, weight=25, minsize=286, uniform="main")

        self.workspace_tabs = ttk.Notebook(self.body, style="V2.Hidden.TNotebook")
        self.workspace_tabs.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_3))
        self.narration_tab = ttk.Frame(self.workspace_tabs, style="V2.App.TFrame")
        self.dialogue_tab = ttk.Frame(self.workspace_tabs, style="V2.App.TFrame")
        self.samples_tab = ttk.Frame(self.workspace_tabs, style="V2.App.TFrame")
        self.workspace_tabs.add(self.narration_tab, text="Narração")
        self.workspace_tabs.add(self.dialogue_tab, text="Conversação")
        self.workspace_tabs.add(self.samples_tab, text="Samples de vozes")
        self.workspace_tabs.bind("<<NotebookTabChanged>>", self._on_workspace_tab_changed)

        self.generate_buttons: list[ShadowButton] = []
        self.cancel_buttons: list[ttk.Button] = []
        self.pause_buttons: list[ttk.Button] = []
        self.progress_bars: list[ttk.Progressbar] = []
        self.job_status_labels: list[ttk.Label] = []
        self.profile_boxes: list[ttk.Combobox] = []
        self.speed_boxes: list[ttk.Combobox] = []
        self.choose_output_buttons: list[ttk.Button] = []
        self.open_output_buttons: list[ttk.Button] = []
        self.narration_text_input = self._build_generation_tab(self.narration_tab, MODE_NARRATION_LABEL)
        self.dialogue_text_input = self._build_generation_tab(self.dialogue_tab, MODE_DIALOGUE_LABEL)
        self.text_input = self.narration_text_input
        self._build_samples_tab()
        self._build_activity_panel()
        self._build_action_bar()
        self._build_footer()
        self.generate_button = self.generate_buttons[0]
        self.cancel_button = self.cancel_buttons[0]
        self.profile_box = self.profile_boxes[0]
        self.speed_box = self.speed_boxes[0]
        self.choose_output_button = self.choose_output_buttons[0]
        self.open_output_button = self.open_output_buttons[0]
        self.workspace_tabs.select(self.narration_tab)

    def _build_generation_tab(self, parent: ttk.Frame, mode_label: str) -> tk.Text:
        compact = mode_label == MODE_DIALOGUE_LABEL
        field_gap = COMPACT_FIELD_GAP if compact else SPACE_1
        control_gap = COMPACT_SECTION_GAP if compact else SPACE_2
        entry_style = "V2.Compact.TEntry" if compact else "TEntry"
        combo_style = "V2.Compact.TCombobox" if compact else "TCombobox"
        secondary_style = "V2.Compact.Secondary.TButton" if compact else "V2.Secondary.TButton"
        parent.columnconfigure(0, weight=37, minsize=294, uniform="generation")
        parent.columnconfigure(1, weight=63, minsize=440, uniform="generation")
        parent.rowconfigure(0, weight=1)

        settings = self._panel(parent, "Projeto", compact=compact)
        settings.grid(row=0, column=0, sticky="nsew", padx=(0, SPACE_3))
        settings.columnconfigure(0, weight=0)
        settings.columnconfigure(1, weight=1)

        ttk.Label(settings, text="Nome do projeto", style="V2.Field.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, field_gap))
        ttk.Entry(settings, textvariable=self.project_var, style=entry_style).grid(row=2, column=0, columnspan=2, sticky="ew")

        self._section_heading(settings, 3, "Voz", compact=compact)
        if mode_label == MODE_NARRATION_LABEL:
            selector_label, selector_var = "Voz", self.narration_voice_var
        else:
            selector_label, selector_var = "Voz A", self.voice_a_var
        selector = self._voice_selector(settings, 5, selector_label, selector_var, compact=compact)
        if mode_label == MODE_NARRATION_LABEL:
            self.narration_box = selector
        else:
            self.voice_a_box = selector
        preview_a = ttk.Button(
            settings,
            text="▶  Ouvir voz" if mode_label == MODE_NARRATION_LABEL else "▶  Ouvir voz A",
            style=secondary_style,
            command=lambda variable=selector_var: self.on_preview_selected(variable),
        )
        preview_a.grid(row=6, column=0, columnspan=2, sticky="w", pady=(control_gap, 0))
        if mode_label == MODE_DIALOGUE_LABEL:
            self.voice_b_box = self._voice_selector(settings, 7, "Voz B", self.voice_b_var, compact=True)
            preview_b = ttk.Button(settings, text="▶  Ouvir voz B", style=secondary_style, command=lambda: self.on_preview_selected(self.voice_b_var))
            preview_b.grid(row=8, column=0, columnspan=2, sticky="w", pady=(control_gap, 0))
            adjustment_row = 9
        else:
            adjustment_row = 7

        self._section_heading(settings, adjustment_row, "Ajustes", compact=compact)
        ttk.Label(settings, text="Perfil", style="V2.Field.TLabel").grid(row=adjustment_row + 2, column=0, columnspan=2, sticky="w", pady=(0, field_gap))
        profile = ttk.Combobox(settings, textvariable=self.profile_var, values=list(PROFILE_LABELS), state="readonly", style=combo_style)
        profile.grid(row=adjustment_row + 3, column=0, columnspan=2, sticky="ew")
        self.profile_boxes.append(profile)
        ttk.Label(settings, text="Velocidade da fala", style="V2.Field.TLabel").grid(row=adjustment_row + 4, column=0, columnspan=2, sticky="w", pady=(control_gap, field_gap))
        speed = ttk.Combobox(settings, textvariable=self.speed_var, values=list(SPEECH_SPEED_LABELS), state="readonly", style=combo_style)
        speed.grid(row=adjustment_row + 5, column=0, columnspan=2, sticky="ew")
        self.speed_boxes.append(speed)

        output_row = adjustment_row + 6
        self._section_heading(settings, output_row, "Saída", compact=compact)
        ttk.Label(settings, text="Pasta de destino", style="V2.Field.TLabel").grid(row=output_row + 2, column=0, columnspan=2, sticky="w", pady=(0, field_gap))
        ttk.Entry(settings, textvariable=self.output_directory_var, state="readonly", style=entry_style).grid(row=output_row + 3, column=0, columnspan=2, sticky="ew")
        output_actions = ttk.Frame(settings, style="V2.Card.TFrame")
        output_actions.grid(row=output_row + 4, column=0, columnspan=2, sticky="w", pady=(control_gap, 0))
        choose = ttk.Button(output_actions, text="Escolher pasta...", style=secondary_style, command=self.on_choose_output_directory)
        choose.pack(side="left")
        open_button = ttk.Button(output_actions, text="Abrir pasta", style=secondary_style, command=self.on_open_output_directory)
        open_button.pack(side="left", padx=(SPACE_2, 0))
        self.choose_output_buttons.append(choose)
        self.open_output_buttons.append(open_button)

        editor = self._panel(parent, "Texto da narração" if mode_label == MODE_NARRATION_LABEL else "Texto da conversação A/B")
        editor.grid(row=0, column=1, sticky="nsew")
        editor.columnconfigure(0, weight=1)
        editor.rowconfigure(3, weight=1)
        hint = "Escreva ou cole o texto em inglês que será convertido em áudio." if mode_label == MODE_NARRATION_LABEL else "Comece cada fala com A: ou B:. Ex.: A: Olá!  B: Oi!\nLinhas vazias continuam a fala anterior."
        hint_alignment = {} if mode_label == MODE_NARRATION_LABEL else {"justify": "left"}
        ttk.Label(editor, text=hint, style="V2.Muted.TLabel", wraplength=680, **hint_alignment).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, SPACE_2))
        text_input = tk.Text(
            editor,
            wrap="word",
            undo=True,
            font=(FONT_MONO, 10),
            relief="solid",
            borderwidth=1,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        text_scrollbar = ttk.Scrollbar(editor, orient="vertical", command=text_input.yview)
        text_input.configure(yscrollcommand=text_scrollbar.set)
        text_input.grid(row=3, column=0, sticky="nsew")
        text_scrollbar.grid(row=3, column=1, sticky="ns", padx=(SPACE_2, 0))
        import_button = ttk.Button(settings, text="Importar TXT", style="V2.Secondary.TButton", command=lambda target=None: self.on_load_file(target or text_input))
        import_button.grid(row=0, column=1, sticky="e")
        return text_input

    def _build_activity_panel(self) -> None:
        self.activity_panel = self._panel(self.body, "Atividade")
        self.activity_panel.grid(row=0, column=1, sticky="nsew")
        self.activity_panel.columnconfigure(0, weight=1)

        status_card = ttk.Frame(self.activity_panel, style="V2.Status.TFrame", padding=(SPACE_3, SPACE_3))
        status_card.grid(row=1, column=0, sticky="ew", pady=(0, SPACE_4))
        status_card.columnconfigure(0, weight=1)
        job_status = ttk.Label(status_card, textvariable=self.status_var, style="V2.Status.TLabel", wraplength=270, justify="left")
        job_status.grid(row=0, column=0, sticky="ew")
        self.job_status_labels.append(job_status)

        progress_header = ttk.Frame(self.activity_panel, style="V2.Card.TFrame")
        progress_header.grid(row=2, column=0, sticky="ew")
        progress_header.columnconfigure(0, weight=1)
        ttk.Label(progress_header, text="Progresso", style="V2.Field.TLabel", font=(FONT_UI, 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(progress_header, textvariable=self.progress_percent_var, style="V2.Field.TLabel", font=(FONT_UI, 9, "bold")).grid(row=0, column=1, sticky="e")
        progress = ttk.Progressbar(self.activity_panel, variable=self.progress_value, maximum=100, style="V2.Horizontal.TProgressbar")
        progress.grid(row=3, column=0, sticky="ew", pady=(SPACE_2, SPACE_1))
        self.progress_bars.append(progress)
        self.progress = progress
        ttk.Label(self.activity_panel, textvariable=self.progress_stage_var, style="V2.Card.TLabel", font=(FONT_UI, 9, "bold")).grid(row=4, column=0, sticky="w", pady=(SPACE_2, 0))
        ttk.Label(self.activity_panel, textvariable=self.progress_item_var, style="V2.Muted.TLabel").grid(row=5, column=0, sticky="w")

        ttk.Separator(self.activity_panel).grid(row=6, column=0, sticky="ew", pady=SPACE_4)
        ttk.Label(self.activity_panel, text="Arquivo final", style="V2.Field.TLabel", font=(FONT_UI, 9, "bold")).grid(row=7, column=0, sticky="w")
        ttk.Label(self.activity_panel, textvariable=self.output_var, style="V2.Muted.TLabel", wraplength=270, justify="left").grid(row=8, column=0, sticky="ew", pady=(SPACE_2, 0))

        ttk.Separator(self.activity_panel).grid(row=9, column=0, sticky="ew", pady=SPACE_4)
        ttk.Label(self.activity_panel, text="Recursos", style="V2.Field.TLabel", font=(FONT_UI, 9, "bold")).grid(row=10, column=0, sticky="w")
        ttk.Label(self.activity_panel, textvariable=self.resource_status_var, style="V2.Muted.TLabel", wraplength=270, justify="left").grid(row=11, column=0, sticky="ew", pady=(SPACE_2, 0))

    def _build_action_bar(self) -> None:
        self.action_bar = ttk.Frame(self.root, style="V2.ActionBar.TFrame", height=ACTION_BAR_HEIGHT, padding=(SPACE_5, SPACE_3))
        self.action_bar.grid(row=2, column=0, sticky="ew", padx=SPACE_3, pady=(0, SPACE_2))
        self.action_bar.grid_propagate(False)
        self.action_bar.columnconfigure(0, weight=1)
        self.action_bar.columnconfigure(1, weight=1)
        self.action_bar.columnconfigure(2, weight=1)

        generate = ShadowButton(self.action_bar, text="▶   GERAR ÁUDIO", command=self.on_generate)
        generate.set_palette(background=COLOR_PRIMARY, hover=COLOR_PRIMARY_HOVER, pressed=COLOR_PRIMARY_PRESSED, foreground=COLOR_WHITE, shadow=None)
        generate.grid(row=0, column=0, sticky="ew", padx=(0, SPACE_3))
        pause = ttk.Button(self.action_bar, text="Ⅱ   PAUSAR", style="V2.Secondary.TButton", command=self.on_pause, state="disabled")
        pause.grid(row=0, column=1, sticky="ew", padx=(0, SPACE_3))
        cancel = ttk.Button(self.action_bar, text="✕   CANCELAR", style="V2.Danger.TButton", command=self.on_cancel, state="disabled")
        cancel.grid(row=0, column=2, sticky="ew")
        self.generate_buttons.append(generate)
        self.pause_buttons.append(pause)
        self.cancel_buttons.append(cancel)

    def _build_footer(self) -> None:
        footer = ttk.Frame(self.root, style="V2.Footer.TFrame", height=FOOTER_HEIGHT, padding=(SPACE_4, 4))
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.mode_status_var, style="V2.Footer.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(footer, text="Execução local · offline", style="V2.Footer.TLabel").grid(row=0, column=1, sticky="e")

    def _show_samples(self) -> None:
        self.workspace_tabs.select(self.samples_tab)

    def _build_samples_tab(self) -> None:
        self.samples_tab.columnconfigure(0, weight=1)
        self.samples_tab.rowconfigure(0, weight=1)
        preview_panel = self._panel(self.samples_tab, "Samples das 28 vozes")
        preview_panel.grid(row=0, column=0, sticky="nsew")
        preview_panel.rowconfigure(3, weight=1)
        ttk.Label(preview_panel, text="Ouça uma voz por vez. A reprodução não altera as vozes escolhidas para gerar.", style="V2.Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(0, SPACE_2))
        controls = ttk.Frame(preview_panel, style="V2.Card.TFrame")
        controls.grid(row=2, column=0, sticky="ew", pady=(0, SPACE_3))
        ttk.Button(controls, text="Ⅱ  Pausar/Retomar", style="V2.Secondary.TButton", command=self.on_preview_pause).pack(side="left")
        ttk.Button(controls, text="↺  Reiniciar", style="V2.Secondary.TButton", command=self.on_preview_restart).pack(side="left", padx=SPACE_2)
        ttk.Button(controls, text="■  Parar", style="V2.Secondary.TButton", command=self.on_preview_stop).pack(side="left")
        ttk.Label(controls, textvariable=self.preview_status_var, style="V2.Muted.TLabel", wraplength=600).pack(side="left", padx=(SPACE_4, 0))
        list_host = ttk.Frame(preview_panel, style="V2.Card.TFrame")
        list_host.grid(row=3, column=0, sticky="nsew")
        list_host.columnconfigure(0, weight=1)
        list_host.rowconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(list_host, background=COLOR_SURFACE, highlightthickness=1, highlightbackground=COLOR_BORDER, bd=0)
        scrollbar = ttk.Scrollbar(list_host, orient="vertical", command=self.preview_canvas.yview)
        self.preview_canvas.configure(yscrollcommand=scrollbar.set)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(SPACE_2, 0))
        inner = ttk.Frame(self.preview_canvas, style="V2.Card.TFrame", padding=SPACE_2)
        window_id = self.preview_canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda _event: self.preview_canvas.configure(scrollregion=self.preview_canvas.bbox("all")))
        self.preview_canvas.bind("<Configure>", lambda event: self.preview_canvas.itemconfigure(window_id, width=event.width))
        for voice in self.voices:
            self._add_preview_row(inner, voice)
        self._bind_preview_mousewheel(inner)

    def _scroll_preview_canvas(self, event) -> str:
        if event.delta:
            self.preview_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"

    def _bind_preview_mousewheel(self, content: tk.Widget) -> None:
        self.preview_canvas.bind("<MouseWheel>", self._scroll_preview_canvas)

        def bind_tree(widget: tk.Widget) -> None:
            widget.bind("<MouseWheel>", self._scroll_preview_canvas)
            for child in widget.winfo_children():
                bind_tree(child)

        bind_tree(content)

    def _voice_selector(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, *, compact: bool = False) -> ttk.Combobox:
        row_gap = COMPACT_FIELD_GAP if compact else 3
        style = "V2.CompactVoice.TCombobox" if compact else "V2.Voice.TCombobox"
        ttk.Label(parent, text=label, style="V2.Field.TLabel").grid(row=row, column=0, sticky="w", padx=(0, SPACE_2), pady=row_gap)
        box = ttk.Combobox(parent, textvariable=variable, values=[""] + self.voice_display_values, state="readonly", style=style)
        box.configure(postcommand=lambda widget=box: self._style_voice_dropdown(widget))
        box.grid(row=row, column=1, sticky="ew", pady=row_gap)
        box.set("")
        return box

    @staticmethod
    def _style_voice_dropdown(box: ttk.Combobox) -> None:
        popdown = box.tk.call("ttk::combobox::PopdownWindow", str(box))
        box.tk.call(
            f"{popdown}.f.l",
            "configure",
            "-background",
            COLOR_SURFACE,
            "-foreground",
            COLOR_TEXT,
            "-selectbackground",
            COLOR_PRIMARY_HOVER,
            "-selectforeground",
            COLOR_WHITE,
            "-activestyle",
            "none",
        )

    def _add_preview_row(self, parent: ttk.Frame, voice: dict) -> None:
        voice_id = voice["voice_id"]
        row = ttk.Frame(parent, style="V2.PreviewRow.TFrame", padding=(8, 6))
        row.pack(fill="x", pady=2)
        row.columnconfigure(0, weight=1)
        label = ttk.Label(row, text=voice["display_label"], style="V2.PreviewRow.TLabel")
        label.grid(row=0, column=0, sticky="w")
        meta = ttk.Label(row, text=voice_id, style="V2.PreviewMeta.TLabel")
        meta.grid(row=1, column=0, sticky="w")
        button = ttk.Button(row, text="▶", style="V2.Icon.TButton", width=4, command=lambda value=voice_id: self.on_preview_voice(value))
        button.grid(row=0, column=1, rowspan=2, padx=(8, 0))
        self.preview_rows[voice_id] = (row, label, meta, button)

    def _on_mode_changed(self, *_args) -> None:
        self.on_preview_stop("Modo alterado. Prévia parada.")
        self.text_input = self.narration_text_input if self.mode_var.get() == MODE_NARRATION_LABEL else self.dialogue_text_input
        self._apply_mode_theme()
        self._refresh_output_preview()

    def set_mode(self, mode_label: str) -> None:
        if mode_label not in MODE_MAP:
            raise ValueError("Modo visual inválido")
        target_tab = self.narration_tab if mode_label == MODE_NARRATION_LABEL else self.dialogue_tab
        self.workspace_tabs.select(target_tab)
        if self.mode_var.get() == mode_label:
            self._apply_mode_theme()
            return
        self.mode_var.set(mode_label)

    def _apply_mode_theme(self) -> None:
        mode = self.mode_var.get()
        theme = MODE_THEMES.get(mode, MODE_THEMES[MODE_NARRATION_LABEL])
        self.preview_canvas.configure(background=theme["surface"])
        for text_input in (self.narration_text_input, self.dialogue_text_input):
            text_input.configure(
                background=theme["surface"],
                foreground=theme["text"],
                insertbackground=theme["primary"],
                selectbackground=theme["accent"],
                selectforeground=theme["text"],
                highlightbackground=theme["border"],
                highlightcolor=theme["focus"],
            )
        for button in self.generate_buttons:
            self._apply_colored_button_theme(button, theme)
        self._apply_workspace_tab_theme()
        if self.workspace_tabs.select() != str(self.samples_tab):
            self.mode_status_var.set(f"Modo ativo: {mode}")

    @staticmethod
    def _apply_colored_button_theme(button: ShadowButton, theme: dict) -> None:
        button.set_palette(
            background=theme["primary"],
            hover=theme["hover"],
            pressed=theme["pressed"],
            foreground=COLOR_WHITE,
            shadow=None,
        )

    def _on_workspace_tab_changed(self, _event=None) -> None:
        selected = self.workspace_tabs.select()
        if selected == str(self.narration_tab) and self.mode_var.get() != MODE_NARRATION_LABEL:
            self.mode_var.set(MODE_NARRATION_LABEL)
            return
        if selected == str(self.dialogue_tab) and self.mode_var.get() != MODE_DIALOGUE_LABEL:
            self.mode_var.set(MODE_DIALOGUE_LABEL)
            return
        self._apply_workspace_tab_theme()

    def _apply_workspace_tab_theme(self) -> None:
        if not hasattr(self, "workspace_tabs"):
            return
        selected = self.workspace_tabs.select()
        sample_selected = selected == str(self.samples_tab)
        active_key = "Samples" if sample_selected else self.mode_var.get()
        for key, button in self.nav_buttons.items():
            button.configure(style="V2.NavActive.TButton" if key == active_key else "V2.Nav.TButton")
        if sample_selected:
            self.activity_panel.grid_remove()
            self.action_bar.grid_remove()
            self.workspace_tabs.grid_configure(columnspan=2, padx=0)
            self.mode_status_var.set("Área ativa: Samples de vozes")
        else:
            self.workspace_tabs.grid_configure(columnspan=1, padx=(0, SPACE_3))
            self.activity_panel.grid()
            self.action_bar.grid()
            self.mode_status_var.set(f"Modo ativo: {self.mode_var.get()}")
        if self.generate_buttons:
            self.generate_buttons[0].configure(state="disabled" if self.is_running or sample_selected else "normal")

    def _on_project_changed(self, *_args) -> None:
        self._refresh_output_preview()

    def _update_mode_controls(self) -> None:
        self.text_input = self.narration_text_input if self.mode_var.get() == MODE_NARRATION_LABEL else self.dialogue_text_input

    def _refresh_output_preview(self) -> None:
        self.output_directory_var.set(str(self.output_directory))

    def _choose_folder_dialog(self, initial_directory: Path) -> str:
        return filedialog.askdirectory(
            title="Escolher pasta de saída",
            initialdir=str(initial_directory),
            mustexist=True,
        )

    def on_choose_output_directory(self) -> None:
        selected = self.folder_chooser(self.output_directory)
        if not selected:
            return
        try:
            self.output_directory = save_selected_output_directory(Path(selected))
        except (OSError, ValueError, PermissionError):
            self.status_var.set("Não foi possível usar essa pasta. Escolha uma pasta comum com permissão de gravação.")
            return
        self.output_var.set("")
        self._refresh_output_preview()
        self.status_var.set("Pasta de saída atualizada.")

    def on_open_output_directory(self) -> None:
        try:
            directory = validate_output_directory(self.output_directory, verify_writable=False)
            if self.folder_opener is None:
                raise OSError("Abertura de pasta indisponível.")
            self.folder_opener(str(directory))
        except (OSError, ValueError):
            self.status_var.set("Não foi possível abrir a pasta de saída.")

    def _preview_path(self, voice_id: str) -> Path:
        voice = self.voice_by_id[voice_id]
        path = (V2_ROOT / voice["preview_wav_path"]).resolve()
        if V2_ROOT not in path.parents:
            raise PreviewError("Caminho de prévia inválido.")
        return path

    def on_preview_selected(self, variable: tk.StringVar) -> None:
        voice_id = self.voice_id_by_display.get(variable.get().strip())
        if not voice_id:
            message = "Escolha uma voz antes de ouvir a prévia."
            self.preview_status_var.set(message)
            self.status_var.set(message)
            return
        self.on_preview_voice(voice_id)
        if self.preview.voice_id == voice_id:
            self.status_var.set(f"Tocando prévia: {voice_id}")

    def on_preview_voice(self, voice_id: str) -> None:
        try:
            self.preview.play(voice_id, self._preview_path(voice_id))
            self.preview_status_var.set(f"Tocando: {voice_id}")
            self._highlight_preview(voice_id)
        except PreviewError as exc:
            self.preview_status_var.set(str(exc))
            self._highlight_preview(None)

    def on_preview_pause(self) -> None:
        try:
            state = self.preview.pause_resume()
            if self.preview.voice_id:
                action = "Pausada" if state == "paused" else "Tocando"
                self.preview_status_var.set(f"{action}: {self.preview.voice_id}")
        except PreviewError:
            self.preview_status_var.set("Não foi possível pausar ou retomar a prévia.")

    def on_preview_restart(self) -> None:
        try:
            self.preview.restart()
            if self.preview.voice_id:
                self.preview_status_var.set(f"Reiniciando: {self.preview.voice_id}")
        except PreviewError:
            self.preview_status_var.set("Não foi possível reiniciar a prévia.")

    def on_preview_stop(self, message: str = "Prévia parada.") -> None:
        self.preview.stop()
        self.preview_status_var.set(message)
        self._highlight_preview(None)

    def _highlight_preview(self, active_voice_id: str | None) -> None:
        for voice_id, (row, label, meta, button) in self.preview_rows.items():
            active = voice_id == active_voice_id
            row.configure(style="V2.PreviewPlaying.TFrame" if active else "V2.PreviewRow.TFrame")
            label.configure(style="V2.PreviewPlaying.TLabel" if active else "V2.PreviewRow.TLabel")
            meta.configure(style="V2.PreviewPlayingMeta.TLabel" if active else "V2.PreviewMeta.TLabel")
            button.configure(text="■" if active else "▶")

    def _poll_preview(self) -> None:
        if self.preview.voice_id and self.preview.state == "playing" and self.preview.current_mode() == "stopped":
            self.on_preview_stop("Prévia concluída.")
        self.root.after(400, self._poll_preview)

    def on_load_file(self, target: tk.Text | None = None) -> None:
        file_name = filedialog.askopenfilename(title="Carregar texto", filetypes=(("Texto", "*.txt"),))
        if not file_name:
            return
        path = Path(file_name)
        try:
            if path.is_symlink() or not path.is_file() or path.suffix.lower() != ".txt":
                self.status_var.set("Escolha um arquivo TXT comum e valido.")
                return
            if path.stat().st_size > MAX_INPUT_FILE_BYTES:
                self.status_var.set("O arquivo TXT e grande demais para esta versao.")
                return
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="cp1252")
        except OSError:
            self.status_var.set("Não foi possível carregar o arquivo.")
            return
        target = target or self.text_input
        target.delete("1.0", "end")
        target.insert("1.0", content)
        self.status_var.set(f"Arquivo carregado: {path.name}")

    def build_request(self) -> GenerationRequest | str:
        project = self.project_var.get().strip()
        mode = MODE_MAP[self.mode_var.get()]
        text_input = self.narration_text_input if mode == MODE_NARRATION else self.dialogue_text_input
        text = text_input.get("1.0", "end").strip()
        if not project or not PROJECT_RE.fullmatch(project):
            return "Use um nome de projeto com letras, números, _ ou -."
        if not text:
            return "Digite ou carregue o texto antes de gerar."
        try:
            self.output_directory = validate_output_directory(self.output_directory)
        except (OSError, ValueError, PermissionError):
            return "Escolha uma pasta de saída válida com permissão de gravação."
        try:
            validate_text_content(text)
        except ValueError:
            return "O texto excede os limites seguros ou contem caracteres invalidos."
        speed = SPEECH_SPEED_LABELS.get(self.speed_var.get())
        if speed is None:
            return "Escolha uma velocidade da fala válida."
        if mode == MODE_NARRATION:
            voice_label = self.narration_voice_var.get().strip()
            voice = self.voice_id_by_display.get(voice_label)
            if not voice:
                return "Escolha uma voz de narração."
            return GenerationRequest(
                mode=mode,
                project_name=project,
                text=text,
                narration_voice_id=voice,
                speed=speed,
                output_base_dir=self.output_directory,
            )
        try:
            parse_dialogue_ab(text)
        except ValueError:
            return "Confira o diálogo: inicie o primeiro turno com A: ou B:."
        voice_a = self.voice_id_by_display.get(self.voice_a_var.get().strip())
        voice_b = self.voice_id_by_display.get(self.voice_b_var.get().strip())
        if not voice_a or not voice_b:
            return "Escolha a voz A e a voz B."
        return GenerationRequest(
            mode=mode,
            project_name=project,
            text=text,
            voice_a_id=voice_a,
            voice_b_id=voice_b,
            speed=speed,
            output_base_dir=self.output_directory,
        )

    def on_generate(self) -> None:
        self.on_preview_stop("Geração iniciada. Prévia parada.")
        if self.is_running:
            self.status_var.set("Já existe uma geração em andamento.")
            return
        request = self.build_request()
        if isinstance(request, str):
            self.status_var.set(request)
            return
        profile_id = PROFILE_LABELS[self.profile_var.get()]
        decision = self.resource_checker(profile_id)
        snapshot = decision.snapshot
        self.resource_status_var.set(
            f"RAM livre: {snapshot.available_ram_gb:.1f} GB · Disco: {snapshot.disk_free_gb:.1f} GB"
        )
        if not decision.allowed:
            self.status_var.set("Geração bloqueada: " + " ".join(decision.blocks))
            return
        if decision.warnings:
            self.status_var.set("Aviso: " + " ".join(decision.warnings))
        self.is_running = True
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self._set_running_controls(True)
        self.progress_value.set(0)
        self.progress_percent_var.set("0%")
        self.progress_stage_var.set("Iniciando...")
        self.progress_item_var.set("")
        if not decision.warnings:
            self.status_var.set(
                f"Gerando localmente com Kokoro · velocidade {self.speed_var.get()} · perfil {self.profile_var.get()}."
            )
        threading.Thread(target=self._run_generation_worker, args=(request, profile_id, self.cancel_event, self.pause_event), daemon=True).start()

    def _run_generation_worker(self, request: GenerationRequest, profile_id: str, cancel_event: threading.Event, pause_event: threading.Event) -> None:
        try:
            runner = self.job_runner
            if runner is None:
                from v2_kokoro.app.core.job_runner import run_generation

                runner = run_generation
            result = runner(
                request,
                progress_callback=lambda event: self.event_queue.put(("progress", event)),
                resource_profile=profile_id,
                resource_callback=lambda snapshot: self.event_queue.put(("resource", snapshot)),
                cancel_event=cancel_event,
                pause_event=pause_event,
            )
            self.event_queue.put(("result", result))
        except Exception as exc:
            self.event_queue.put(("exception", str(exc)))

    def _poll_events(self) -> None:
        while True:
            try:
                kind, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                self._apply_progress(payload)
            elif kind == "resource":
                self._apply_resource_snapshot(payload)
            elif kind == "result":
                self._finish_result(payload)
            else:
                self._finish_error("Não foi possível gerar o áudio. Revise os dados e tente novamente.")
        self.root.after(100, self._poll_events)

    def _apply_progress(self, event: ProgressEvent) -> None:
        self.progress_value.set(event.percent)
        self.progress_percent_var.set(f"{event.percent}%")
        self.progress_stage_var.set(progress_label(event.stage, STAGE_LABELS))
        if event.current is not None and event.total is not None:
            self.progress_item_var.set(f"Item {event.current} de {event.total}")
        else:
            self.progress_item_var.set("")

    def _apply_resource_snapshot(self, snapshot: dict) -> None:
        self.resource_status_var.set(
            f"CPU do sistema: {snapshot['system_cpu_percent']:.0f}% · RAM do processamento: {snapshot['process_ram_mb']:.0f} MB · "
            f"RAM livre: {snapshot['available_ram_gb']:.1f} GB · Disco: {snapshot['disk_free_gb']:.1f} GB"
        )

    def on_cancel(self) -> None:
        if not self.is_running or self.cancel_event is None:
            return
        self.cancel_event.set()
        if self.pause_event is not None:
            self.pause_event.clear()
        for button in self.cancel_buttons:
            button.configure(state="disabled")
        for button in self.pause_buttons:
            button.configure(state="disabled")
        self.progress_stage_var.set("Cancelamento solicitado")
        self.status_var.set("Cancelando com segurança após o item ou etapa atual.")

    def on_pause(self) -> None:
        if not self.is_running or self.pause_event is None:
            return
        if self.pause_event.is_set():
            self.pause_event.clear()
            for button in self.pause_buttons:
                button.configure(text="Ⅱ   PAUSAR")
            self.progress_stage_var.set("Retomando")
            self.status_var.set("Geração retomada no mesmo job.")
            return
        self.pause_event.set()
        for button in self.pause_buttons:
            button.configure(text="▶   RETOMAR")
        self.progress_stage_var.set("Pausado")
        self.status_var.set("Geração pausada com segurança após o item ou etapa atual.")

    def _set_running_controls(self, running: bool) -> None:
        samples_selected = hasattr(self, "workspace_tabs") and self.workspace_tabs.select() == str(self.samples_tab)
        for button in self.generate_buttons:
            button.configure(state="disabled" if running or samples_selected else "normal")
        for button in self.cancel_buttons:
            button.configure(state="normal" if running else "disabled")
        for button in self.pause_buttons:
            button.configure(state="normal" if running else "disabled")
            if not running:
                button.configure(text="Ⅱ   PAUSAR")
        for box in self.profile_boxes:
            box.configure(state="disabled" if running else "readonly")
        for box in self.speed_boxes:
            box.configure(state="disabled" if running else "readonly")
        for button in self.choose_output_buttons:
            button.configure(state="disabled" if running else "normal")
        for button in self.open_output_buttons:
            button.configure(state="disabled" if running else "normal")
        if not running:
            self._update_mode_controls()

    def _finish_result(self, result) -> None:
        self.is_running = False
        self.cancel_event = None
        self.pause_event = None
        self._set_running_controls(False)
        if not result.success:
            if result.metadata.get("cancelled"):
                self.progress_stage_var.set("Cancelado")
                self.status_var.set("Geração cancelada com segurança. Nenhum áudio final incompleto foi mantido.")
                return
            self._finish_error(self._friendly_error(result.errors[0] if result.errors else ""))
            return
        self.progress_value.set(100)
        self.progress_percent_var.set("100%")
        self.progress_stage_var.set("Concluído")
        final_mp3 = next((path for path in result.created_files if path.endswith("_complete.mp3")), "")
        self.output_var.set(f"MP3 salvo em: {self._display_output_path(final_mp3)}")
        self.status_var.set("Áudio criado com sucesso.")

    @staticmethod
    def _display_output_path(path: str) -> str:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = V2_ROOT / candidate
        return str(candidate.resolve(strict=False))

    def _finish_error(self, message: str) -> None:
        self.is_running = False
        self.cancel_event = None
        self.pause_event = None
        self._set_running_controls(False)
        self.progress_stage_var.set("Erro")
        self.status_var.set(message)

    @staticmethod
    def _friendly_error(message: str) -> str:
        lowered = message.lower()
        if "voice" in lowered:
            return "Escolha uma voz válida."
        if "dialogue" in lowered or "a:" in lowered:
            return "Confira o diálogo: inicie cada turno com A: ou B:. Linhas seguintes continuam o turno atual."
        if "project" in lowered:
            return "Use um nome de projeto mais seguro."
        if "text" in lowered:
            return "Confira o texto informado."
        if "already_running" in lowered:
            return "Já existe uma geração em andamento."
        if "memoria" in lowered or "disco" in lowered or "bateria" in lowered:
            return message
        return "Não foi possível gerar o áudio. Revise os dados e tente novamente."

    def on_close(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()
        self.preview.close()
        self.root.destroy()


def create_main_window(**kwargs) -> tk.Tk:
    root = tk.Tk()
    KokoroV2Window(root, **kwargs)
    return root
