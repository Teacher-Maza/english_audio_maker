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
    COLOR_DIALOGUE_SURFACE,
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
from v2_kokoro.app.ui.materials import Inspector, WatermarkedText, brand_font, pulse_image, relief_image, surface_image, window_icon_images
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
    "synthesizing_reduced": "Gerando em ritmo reduzido",
    "checking_recovery": "Verificando progresso salvo",
    "restoring_audio": "Retomando trechos salvos",
    "saving_log": "Salvando log seguro",
    "paused": "Pausado",
    "completed": "Concluído",
    "cancelled": "Cancelado",
    "error": "Erro",
}
PROFILE_LABELS = {"Automatico (recomendado)": PROFILE_AUTOMATIC, "Econômico": PROFILE_ECONOMIC, "Equilibrado": PROFILE_BALANCED}
SPEECH_SPEED_LABELS = {"Slow (75%)": SPEECH_SPEED_SLOW, "Normal (100%)": SPEECH_SPEED_NORMAL, "Fast (125%)": SPEECH_SPEED_FAST}


class ShadowButton(tk.Canvas):
    """Primary action with stable sizing and keyboard-visible focus."""

    def __init__(self, parent: tk.Widget, *, text: str, command: Callable[[], None], **kwargs) -> None:
        super().__init__(parent, height=40, highlightthickness=2, bd=0, takefocus=True, cursor="hand2", **kwargs)
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
        self._image_cache = {}
        self.bind("<Configure>", lambda _event: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", lambda _event: self.invoke())
        self.bind("<space>", lambda _event: self.invoke())
        self.bind("<FocusIn>", lambda _event: self.configure(highlightbackground=COLOR_PRIMARY, highlightcolor=COLOR_PRIMARY))
        self.bind("<FocusOut>", lambda _event: self.configure(highlightbackground=COLOR_SURFACE_ALT, highlightcolor=COLOR_PRIMARY))
        self.configure(background=COLOR_SURFACE_ALT, highlightbackground=COLOR_SURFACE_ALT, highlightcolor=COLOR_PRIMARY)
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
        width = self.winfo_width() if self.winfo_width() > 1 else self.winfo_reqwidth()
        height = self.winfo_height() if self.winfo_height() > 1 else self.winfo_reqheight()
        if self._state == "disabled":
            background, foreground, shadow = DISABLED_BG, DISABLED_TEXT, None
        elif self._pressed:
            background, foreground, shadow = self._palette["pressed"], self._palette["foreground"], self._palette["shadow"]
        elif self._hovered:
            background, foreground, shadow = self._palette["hover"], self._palette["foreground"], self._palette["shadow"]
        else:
            background, foreground, shadow = self._palette["background"], self._palette["foreground"], self._palette["shadow"]
        key = (width, height, background, self._pressed, self._state, self._hovered)
        if key not in self._image_cache:
            if len(self._image_cache) >= 8:
                self._image_cache.clear()
            self._image_cache[key] = surface_image(self, background, '#73998C', COLOR_SURFACE_ALT,
                shadow=self._state != 'disabled' and not self._pressed, width=max(25, width), height=max(25, height),
                finish=0 if self._state == 'disabled' else .35 if self._pressed else 1.5 if self._hovered else 1)
        self.delete('all')
        self.create_image(0, 0, image=self._image_cache[key], anchor='nw')
        self.create_text(width // 2, height // 2-2, text=self._text, fill=foreground,
                         font=('Segoe UI Semibold', 11))



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
        self.speed_var = tk.StringVar(value="Normal (100%)")
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
        if len(voices) != 9:
            raise ValueError("A UI V2 exige as 9 vozes validadas")
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
            voice["display_label"] = f'{"★ " if favorite else ""}{name} · {"UK" if voice["locale"] == "en_GB" else "US"}'
            prepared.append(voice)
        return sorted(prepared, key=lambda item: (not item["favorite"], item["display_name"].casefold()))

    def _configure_root(self) -> None:
        self.root.title("English Audio Maker")
        icon_path = V2_ROOT / "app" / "ui" / "assets" / "EnglishAudioMaker.ico"
        self.root.iconbitmap(default=str(icon_path))
        self._window_icons = window_icon_images(self.root, icon_path)
        # Tk picks 16/32px when offered all sizes. Supply the full-size source
        # so the Windows shell can downsample it instead of enlarging a small one.
        large_icon = max(self._window_icons, key=lambda image: image.width())
        self.root.iconphoto(True, large_icon)
        self.root.iconphoto(False, large_icon)
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
        style.configure(".", font=(FONT_UI, 10), background=COLOR_APP_BG, foreground=COLOR_TEXT)
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
        # Static nine-slice materials simulate glass and depth without transparency
        # effects, animation timers or extra rendering dependencies.
        self._material_images = []
        for name, fill in (("Card", COLOR_SURFACE_ALT), ("Side", '#DCE5DA')):
            image = surface_image(self.root, fill, '#FFFFFF', COLOR_APP_BG, transparent=False)
            self._material_images.append(image)
            element = f"Organic{name}"
            style.element_create(element, 'image', image, border=12, sticky='nsew')
            style.layout(f"V2.{name}.TFrame", [(element, {'sticky':'nsew'})])
            style.configure(f"V2.{name}.TFrame", background=fill)
        for name, fill, foreground in (
            ('Secondary', '#EDF1E8', COLOR_PRIMARY), ('Compact.Secondary', '#EDF1E8', COLOR_PRIMARY),
            ('Danger', '#EDF1E8', COLOR_DANGER), ('Nav', '#EDF1E8', COLOR_TEXT),
            ('NavActive', COLOR_PRIMARY, COLOR_WHITE),
        ):
            images = [surface_image(self.root, fill, '#FFFFFF', COLOR_APP_BG, finish=1),
                      surface_image(self.root, COLOR_PRIMARY_SOFT if name != 'NavActive' else COLOR_PRIMARY_HOVER, '#A2B49F', COLOR_APP_BG, finish=1.5),
                      surface_image(self.root, '#D1DFCC' if name != 'NavActive' else COLOR_PRIMARY_PRESSED, COLOR_BORDER_STRONG, COLOR_APP_BG, shadow=False, finish=.35),
                      surface_image(self.root, COLOR_DISABLED_BG, COLOR_BORDER, COLOR_APP_BG, shadow=False)]
            self._material_images.extend(images)
            element = f'Organic{name}Button'
            style.element_create(element, 'image', images[0], ('disabled', images[3]), ('pressed', images[2]), ('active', images[1]), border=(10, 6, 10, 10), sticky='nsew')
            style.layout(f'V2.{name}.TButton', [(element, {'sticky':'nsew', 'children': [('Button.focus', {'sticky':'nsew', 'children': [('Button.padding', {'sticky':'nsew', 'children': [('Button.label', {'sticky':'nsew'})]})]})]})])
            style.configure(f'V2.{name}.TButton', foreground=foreground, padding=(7, 2), font=('Segoe UI Semibold', 10))
            style.map(f'V2.{name}.TButton', foreground=[('disabled', COLOR_DISABLED_TEXT), ('!disabled', foreground)])
            # ttk also clears the image element's rectangle before drawing it.
            # Its background must match the containing surface in every state.
            backdrop = '#DCE5DA' if name == 'Compact.Secondary' else COLOR_APP_BG if name in ('Nav', 'NavActive') else COLOR_SURFACE_ALT
            style.configure(f'V2.{name}.TButton', background=backdrop)
            style.map(f'V2.{name}.TButton', background=[('disabled', backdrop), ('!disabled', backdrop)])
        for name, backdrop in (('Header', COLOR_APP_BG), ('Footer', '#DCE5DA')):
            target = f'V2.{name}.Secondary.TButton'
            style.layout(target, style.layout('V2.Secondary.TButton'))
            style.configure(target, background=backdrop, foreground=COLOR_PRIMARY, padding=(7, 2), font=('Segoe UI Semibold', 10))
            style.map(target, background=[('disabled', backdrop), ('!disabled', backdrop)], foreground=[('disabled', COLOR_DISABLED_TEXT), ('!disabled', COLOR_PRIMARY)])
        for target, backdrop in (('V2.Icon.TButton', COLOR_SURFACE_ALT), ('V2.Playing.Icon.TButton', COLOR_PRIMARY_SOFT)):
            style.layout(target, style.layout('V2.Secondary.TButton'))
            style.configure(target, background=backdrop, foreground=COLOR_PRIMARY, padding=(5, 2), font=(FONT_SYMBOL, 10))
            style.map(target, background=[('disabled', backdrop), ('!disabled', backdrop)], foreground=[('disabled', COLOR_DISABLED_TEXT), ('!disabled', COLOR_PRIMARY)])
        style.configure('V2.SideInner.TFrame', background='#DCE5DA')
        style.configure('V2.Plain.TFrame', background=COLOR_SURFACE_ALT)
        style.configure('V2.Side.TLabel', background='#DCE5DA', foreground=COLOR_TEXT, font=(FONT_UI, 10, 'bold'))
        style.configure('V2.SideTitle.TLabel', background='#DCE5DA', foreground=COLOR_TEXT, font=(FONT_UI, 16, 'bold'))
        style.configure('V2.Link.TButton', background='#DCE5DA', foreground=COLOR_PRIMARY, borderwidth=0, padding=(0, 3), font=(FONT_UI, 10, 'underline'))
        style.configure('V2.Hint.TLabel', background=COLOR_PRIMARY_SOFT, foreground=COLOR_TEXT, font=(FONT_UI, 10))
        style.configure('V2.Muted.TLabel', background=COLOR_SURFACE_ALT)
        style.configure('V2.CardTitle.TLabel', background=COLOR_SURFACE_ALT, foreground=COLOR_TEXT, font=(FONT_UI, 13, 'bold'))
        style.configure('V2.ActionBar.TFrame', background=COLOR_SURFACE_ALT, borderwidth=0)
        style.configure('TCombobox', padding=5, font=(FONT_UI, 10))
        # Retain native editing, keyboard navigation and dropdown behavior;
        # replace only the field's rectangular skin in the reference workspace.
        fields = [surface_image(self.root, COLOR_SURFACE_ALT, color, '#DCE5DA', finish=.7)
                  for color in (COLOR_BORDER, COLOR_PRIMARY)]
        self._material_images.extend(fields)
        style.element_create('SculptedField', 'image', fields[0], ('focus', fields[1]),
                             border=(10, 6, 10, 10), sticky='nsew')
        for kind in ('Entry', 'Combobox'):
            children = [(f'{kind}.padding', {'sticky': 'nsew', 'children': [(f'{kind}.textarea', {'sticky': 'nsew'})]})]
            if kind == 'Combobox':
                children.insert(0, ('Combobox.downarrow', {'side': 'right', 'sticky': 'ns'}))
            name = f'V2.Sculpted.T{kind}'
            style.layout(name, [('SculptedField', {'sticky': 'nsew', 'children': children})])
            style.configure(name, background='#DCE5DA', fieldbackground=COLOR_SURFACE_ALT,
                            foreground=COLOR_TEXT, arrowcolor=COLOR_PRIMARY, arrowsize=12,
                            borderwidth=0, padding=(3, 4), font=(FONT_UI, 10))
            style.map(name, fieldbackground=[('readonly', COLOR_SURFACE_ALT)],
                      foreground=[('disabled', COLOR_DISABLED_TEXT), ('!disabled', COLOR_TEXT)],
                      background=[('disabled', '#DCE5DA'), ('!disabled', '#DCE5DA')])
        # Isolated styles keep the approved narration and auxiliary tabs intact.
        for name in ('Card', 'Side'):
            image = surface_image(self.root, COLOR_DIALOGUE_SURFACE, '#FFFFFF', COLOR_APP_BG, transparent=False)
            self._material_images.append(image)
            element = f'Dialogue{name}Surface'
            style.element_create(element, 'image', image, border=12, sticky='nsew')
            style.layout(f'V2.Dialogue.{name}.TFrame', [(element, {'sticky': 'nsew'})])
            style.configure(f'V2.Dialogue.{name}.TFrame', background=COLOR_DIALOGUE_SURFACE)
        for original in ('V2.SideInner.TFrame', 'V2.Plain.TFrame', 'V2.Side.TLabel',
                         'V2.SideTitle.TLabel', 'V2.Link.TButton', 'V2.Muted.TLabel',
                         'V2.Hint.TLabel', 'V2.CardTitle.TLabel', 'V2.Compact.Secondary.TButton',
                         'V2.Secondary.TButton', 'V2.Sculpted.TEntry', 'V2.Sculpted.TCombobox'):
            target = original.replace('V2.', 'V2.Dialogue.', 1)
            style.layout(target, style.layout(original))
            options = {key: value for key in ('font', 'padding', 'foreground', 'fieldbackground',
                                               'arrowcolor', 'arrowsize', 'borderwidth')
                       if (value := style.lookup(original, key)) != ''}
            options['background'] = COLOR_DIALOGUE_SURFACE
            if original.endswith('TLabel') or original == 'V2.Link.TButton':
                options['foreground'] = COLOR_TEXT
            if original.endswith('TEntry') or original.endswith('TCombobox'):
                options['fieldbackground'] = COLOR_SURFACE_ALT
            if original.endswith('TCombobox'):
                options['arrowcolor'] = COLOR_PRIMARY
            style.configure(target, **options)
            style.map(target, background=[('disabled', COLOR_DIALOGUE_SURFACE), ('!disabled', COLOR_DIALOGUE_SURFACE)])
            if 'foreground' in options:
                style.map(target, foreground=[('disabled', COLOR_DISABLED_TEXT), ('!disabled', options['foreground'])])
            if 'fieldbackground' in options:
                style.map(target, fieldbackground=[('readonly', COLOR_SURFACE_ALT)])

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
        canvas = tk.Canvas(parent, width=45, height=40, background=COLOR_APP_BG, highlightthickness=0, bd=0)
        canvas.logo_image = pulse_image(canvas, 36, COLOR_APP_BG)
        canvas.create_image(1, 2, image=canvas.logo_image, anchor='nw')
        return canvas


    def _build_ui(self) -> None:
        header = tk.Frame(self.root, background=COLOR_APP_BG, height=HEADER_HEIGHT)
        header.grid(row=0, column=0, sticky="ew", padx=18)
        header.grid_propagate(False)
        header.columnconfigure(1, weight=1)
        art = tk.Canvas(header, background=COLOR_APP_BG, highlightthickness=0, bd=0)
        self.header_art = art
        art.relief_image = relief_image(art, 720, HEADER_HEIGHT, COLOR_APP_BG)
        art_item = art.create_image(0, 0, image=art.relief_image, anchor='center')

        def paint_header():
            w, h = header.winfo_width(), header.winfo_height()
            edge = min((button.winfo_x() for button in self.nav_buttons.values()), default=w) - 8
            left = self.brand_title.winfo_x() + self.brand_title.winfo_reqwidth() + 12
            width = max(1, edge-left)
            geometry = (left, width, h)
            if getattr(art, '_relief_geometry', None) == geometry:
                return
            art._relief_geometry = geometry
            art.place(x=left, y=0, width=width, height=h)
            art.coords(art_item, width/2, h/2)

        header.bind('<Configure>', lambda _event: header.after_idle(paint_header))
        self.brand_mark = self._build_brand_mark(header)
        self.brand_mark.grid(row=0, column=0, padx=(0, 10), pady=5)
        self.brand_title = tk.Label(header, text="English Audio Maker", background=COLOR_APP_BG,
                                   foreground=COLOR_TEXT, font=(brand_font(self.root), 16))
        self.brand_title.grid(row=0, column=1, sticky="w")
        self.nav_buttons = {
            MODE_NARRATION_LABEL: ttk.Button(header, text="Narração", command=lambda: self.set_mode(MODE_NARRATION_LABEL)),
            MODE_DIALOGUE_LABEL: ttk.Button(header, text="Diálogo", command=lambda: self.set_mode(MODE_DIALOGUE_LABEL)),
            "Samples": ttk.Button(header, text="Biblioteca · 9 vozes", command=self._show_samples),
        }
        for column, button in enumerate(self.nav_buttons.values(), 2):
            button.grid(row=0, column=column, padx=3, pady=8)
        self.help_button = ttk.Button(header, text="Como usar", style="V2.Header.Secondary.TButton", command=self.on_help)
        self.help_button.grid(row=0, column=5, padx=(10, 0))
        self.body = ttk.Frame(self.root, style="V2.App.TFrame", padding=(16, 4, 16, 0))
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.rowconfigure(0, weight=1)
        self.body.columnconfigure(0, weight=1)
        self.workspace_tabs = ttk.Notebook(self.body, style="V2.Hidden.TNotebook")
        self.workspace_tabs.grid(row=0, column=0, sticky="nsew")
        self.narration_tab = ttk.Frame(self.workspace_tabs, style="V2.App.TFrame")
        self.dialogue_tab = ttk.Frame(self.workspace_tabs, style="V2.App.TFrame")
        self.samples_tab = ttk.Frame(self.workspace_tabs, style="V2.App.TFrame")
        self.help_tab = ttk.Frame(self.workspace_tabs, style="V2.App.TFrame")
        for tab, label in ((self.narration_tab, "Narração"), (self.dialogue_tab, "Conversação"), (self.samples_tab, "Samples de vozes"), (self.help_tab, "Como usar")):
            self.workspace_tabs.add(tab, text=label)
        self.workspace_tabs.bind("<<NotebookTabChanged>>", self._on_workspace_tab_changed)
        self.generate_buttons = []
        self.cancel_buttons = []
        self.pause_buttons = []
        self.progress_bars = []
        self.job_status_labels = []
        self.profile_boxes = []
        self.speed_boxes = []
        self.choose_output_buttons = []
        self.open_output_buttons = []
        self.narration_text_input = self._build_generation_tab(self.narration_tab, MODE_NARRATION_LABEL)
        self.dialogue_text_input = self._build_generation_tab(self.dialogue_tab, MODE_DIALOGUE_LABEL)
        self.text_input = self.narration_text_input
        self._build_samples_tab()
        self._build_help_tab()
        self._build_action_bar()
        self._build_activity_panel()
        self._build_footer()
        self.generate_button = self.generate_buttons[0]
        self.cancel_button = self.cancel_buttons[0]
        self.profile_box = self.profile_boxes[0]
        self.speed_box = self.speed_boxes[0]
        self.choose_output_button = self.choose_output_buttons[0]
        self.open_output_button = self.open_output_buttons[0]
        self.workspace_tabs.select(self.narration_tab)

    def on_help(self) -> None:
        self.on_preview_stop("Como usar aberto. Prévia parada.")
        self.workspace_tabs.select(self.help_tab)
        self._apply_workspace_tab_theme()

    def _build_help_tab(self) -> None:
        self.help_tab.columnconfigure(0, weight=1)
        self.help_tab.rowconfigure(0, weight=1)
        panel = ttk.Frame(self.help_tab, style="V2.Card.TFrame", padding=24)
        panel.grid(row=0, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(2, weight=1)
        ttk.Label(panel, text="Como usar", style="V2.CardTitle.TLabel", font=('Segoe UI Semibold', 20)).grid(row=0, column=0, sticky="w")
        ttk.Label(panel, text="Do texto ao MP3, no seu computador.", style="V2.Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(4, 16))
        self.help_text = tk.Text(panel, wrap="word", font=(FONT_UI, 11), background=COLOR_SURFACE_ALT,
                                 foreground=COLOR_TEXT, relief="flat", borderwidth=0, highlightthickness=0,
                                 padx=8, pady=8, width=50, height=8, cursor='arrow')
        scroll = ttk.Scrollbar(panel, orient='vertical', command=self.help_text.yview)
        self.help_text.configure(yscrollcommand=scroll.set)
        self.help_text.grid(row=2, column=0, sticky='nsew')
        scroll.grid(row=2, column=1, sticky='ns')
        self.help_text.tag_configure('heading', font=('Segoe UI Semibold', 13), foreground=COLOR_PRIMARY, spacing1=16, spacing3=6)
        self.help_text.tag_configure('body', spacing3=10, lmargin1=0, lmargin2=0)
        self.help_text.tag_configure('example', font=(FONT_MONO, 11), background=COLOR_PRIMARY_SOFT, lmargin1=12, lmargin2=12, spacing1=8, spacing3=8)
        sections = (
            ('1. Prepare o projeto', 'Dê um nome sem espaços ou acentos. Use letras, números, _ ou -. Escolha Narração para um texto com uma voz, incluindo monólogos; ou Diálogo para duas vozes.'),
            ('2. Escolha e ouça as vozes', 'Selecione uma voz na narração, ou Voz A e Voz B no diálogo. Ouvir toca uma amostra pronta, não o texto digitado. Na Biblioteca, ouça, pause, reinicie ou pare as amostras; ouvir não muda sua seleção.'),
            ('3. Insira o texto em inglês', 'Cole ou escreva no editor, ou use Importar TXT. No diálogo, comece cada fala com A: ou B:. Linhas sem novo marcador continuam a fala anterior.'),
            ('4. Ajuste velocidade e destino', 'Slow (75%) reduz o ritmo; Normal (100%) mantém o padrão; Fast (125%) acelera. Em Recursos, prefira Automático para ajustar o processamento à disponibilidade do computador. Alterar escolhe onde o MP3 será salvo.'),
            ('5. Gere e acompanhe', 'Clique em Gerar áudio. Pausar permite continuar com Retomar. Cancelar descarta os trechos temporários da tarefa; áudios finais anteriores são preservados. Abrir pasta mostra o destino escolhido.'),
            ('Se ocorrer uma falha', 'Gere novamente com o mesmo texto, vozes e velocidade para reutilizar os trechos recuperáveis. O trabalho cancelado intencionalmente não é retomado.'),
            ('Antes de usar o áudio', 'Revise a pronúncia e a naturalidade. O Kokoro pode ler perguntas com entonação neutra ou diferente da intenção, mesmo com pontuação correta. O uso é local e offline.'),
            ('Uso responsável', 'O English Audio Maker destina-se à criação de narrações e diálogos em inglês. Repudiamos e não incentivamos seu uso para discursos de ódio, discriminação, ameaças, assédio, incitação à violência, fraudes ou falsificação de identidade.\n\nCada usuário é responsável pelos textos inseridos, pelos áudios produzidos e por sua utilização e divulgação, respeitando a legislação e os direitos de terceiros.'),
        )
        for heading, body in sections:
            self.help_text.insert('end', heading + '\n', 'heading')
            self.help_text.insert('end', body + '\n', 'body')
            if heading.startswith('3.'):
                self.help_text.insert('end', 'A: Good morning. How are you?\nB: I am fine, thank you.\n', 'example')
        self.help_text.configure(state='disabled')


    def _build_generation_tab(self, parent: ttk.Frame, mode_label: str) -> tk.Text:
        parent.columnconfigure(0, weight=0, minsize=292)
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(0, weight=1)
        inspector = Inspector(parent, dialogue=mode_label == MODE_DIALOGUE_LABEL)
        inspector.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        settings = inspector.content
        settings.columnconfigure(0, weight=1)
        ttk.Label(settings, text="Configurações", style="V2.SideTitle.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))
        ttk.Label(settings, text="Projeto", style="V2.Side.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 4))
        ttk.Entry(settings, textvariable=self.project_var, width=22,
                  style='V2.Sculpted.TEntry').grid(row=2, column=0, sticky="ew")
        variables = [("Voz", self.narration_voice_var)] if mode_label == MODE_NARRATION_LABEL else [("Voz A", self.voice_a_var), ("Voz B", self.voice_b_var)]
        selectors = []
        for number, (label, variable) in enumerate(variables):
            row = 3 + number * 2
            ttk.Label(settings, text=label, style="V2.Side.TLabel").grid(row=row, column=0, sticky="w", pady=(8, 3))
            line = ttk.Frame(settings, style="V2.SideInner.TFrame")
            line.grid(row=row + 1, column=0, sticky="ew")
            line.columnconfigure(0, weight=1)
            box = ttk.Combobox(line, textvariable=variable, values=[""] + self.voice_display_values,
                               width=17, state="readonly", style='V2.Sculpted.TCombobox')
            box.configure(postcommand=lambda widget=box: self._style_voice_dropdown(widget))
            box.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            ttk.Button(line, text="▶ Ouvir", style="V2.Compact.Secondary.TButton",
                       command=lambda selected=variable: self.on_preview_selected(selected)).grid(row=0, column=1)
            selectors.append(box)
        if mode_label == MODE_NARRATION_LABEL:
            self.narration_box = selectors[0]
        else:
            self.voice_a_box, self.voice_b_box = selectors
        ttk.Button(settings, text="Biblioteca · 9 vozes", style="V2.Link.TButton", command=self._show_samples).grid(row=7, column=0, sticky="w", pady=(8, 3))
        for row, label, variable, values, destination in (
            (8, "Velocidade", self.speed_var, SPEECH_SPEED_LABELS, self.speed_boxes),
            (10, "Recursos", self.profile_var, PROFILE_LABELS, self.profile_boxes),
        ):
            ttk.Label(settings, text=label, style="V2.Side.TLabel").grid(row=row, column=0, sticky="w", pady=(8, 3))
            box = ttk.Combobox(settings, textvariable=variable, values=list(values), width=22, state="readonly",
                               style='V2.Sculpted.TCombobox')
            box.grid(row=row + 1, column=0, sticky="ew")
            destination.append(box)
        editor = ttk.Frame(parent, style="V2.Card.TFrame", padding=18)
        editor.grid(row=0, column=1, sticky="nsew")
        editor.columnconfigure(0, weight=1)
        editor.rowconfigure(3, weight=1)
        hint = "Cole seu texto em inglês ou importe um TXT." if mode_label == MODE_NARRATION_LABEL else "Comece cada fala com A: ou B:."
        ttk.Label(editor, text=hint, style="V2.Muted.TLabel").grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 14))
        editor_header = ttk.Frame(editor, style='V2.Plain.TFrame')
        editor_header.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(0, 10))
        editor_header.columnconfigure(0, weight=1)
        ttk.Label(editor_header, text="Diálogo · Texto em inglês" if mode_label == MODE_DIALOGUE_LABEL else "Texto em inglês", style="V2.CardTitle.TLabel",
                  font=(FONT_UI, 18, 'bold')).grid(row=0, column=0, sticky="w")
        if mode_label == MODE_DIALOGUE_LABEL:
            tk.Frame(editor_header, background=COLOR_PRIMARY, height=2).grid(row=1, column=0, columnspan=2, sticky='ew', pady=(6, 0))
        text_input = WatermarkedText(editor, wrap="word", undo=True, font=(FONT_UI, 12), width=36, height=8,
                             relief="flat", borderwidth=0, highlightthickness=1, padx=14, pady=12)
        text_scrollbar = ttk.Scrollbar(editor, orient="vertical", command=text_input.yview)
        def editor_scrolled(first, last):
            text_scrollbar.set(first, last)
            text_input._schedule_mark()
        text_input.configure(yscrollcommand=editor_scrolled)
        text_input.grid(row=3, column=0, sticky="nsew")
        text_scrollbar.grid(row=3, column=1, sticky="ns", padx=(4, 0))
        # A wide header must not reserve blank space beside the script scrollbar.
        editor.columnconfigure(1, weight=0)
        ttk.Button(editor_header, text="Importar TXT", style="V2.Secondary.TButton", command=lambda: self.on_load_file(text_input)).grid(row=0, column=1, sticky="e")
        if mode_label == MODE_DIALOGUE_LABEL:
            def apply_dialogue_style(widget):
                if isinstance(widget, ttk.Widget):
                    original = str(widget.cget('style'))
                    if original.startswith('V2.') and not original.startswith('V2.Dialogue.'):
                        widget.configure(style=original.replace('V2.', 'V2.Dialogue.', 1))
                for child in widget.winfo_children():
                    apply_dialogue_style(child)
            for child in parent.winfo_children():
                apply_dialogue_style(child)
        return text_input


    def _build_activity_panel(self) -> None:
        self.activity_panel = ttk.Frame(self.root, style="V2.Card.TFrame", padding=(16, 6))
        self.activity_panel.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 8))
        self.activity_panel.columnconfigure(0, weight=1)
        status = ttk.Label(self.activity_panel, textvariable=self.status_var, style="V2.Muted.TLabel", wraplength=650)
        status.grid(row=0, column=0, sticky="w")
        self.activity_panel.bind("<Configure>", lambda event: status.configure(wraplength=max(100, event.width - 35)))
        self.job_status_labels.append(status)
        ttk.Label(self.activity_panel, textvariable=self.output_var, style="V2.Muted.TLabel", wraplength=650).grid(row=1, column=0, sticky="ew")


    def _build_action_bar(self) -> None:
        self.action_bar = ttk.Frame(self.root, style="V2.ActionBar.TFrame", padding=(12, 10))
        self.action_bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 0))
        self.action_bar.columnconfigure(3, weight=1)
        generate = ShadowButton(self.action_bar, text="▶  Gerar áudio", command=self.on_generate, width=175)
        generate.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        pause = ttk.Button(self.action_bar, text="Ⅱ   PAUSAR", style="V2.Secondary.TButton", command=self.on_pause, state="disabled")
        pause.grid(row=0, column=1, padx=(0, 8))
        cancel = ttk.Button(self.action_bar, text="✕ Cancelar", style="V2.Danger.TButton", command=self.on_cancel, state="disabled")
        cancel.grid(row=0, column=2, padx=(0, 14))
        progress_host = ttk.Frame(self.action_bar, style="V2.Plain.TFrame")
        progress_host.grid(row=0, column=3, sticky="ew")
        progress_host.columnconfigure(0, weight=1)
        ttk.Label(progress_host, textvariable=self.progress_stage_var, style="V2.Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(progress_host, textvariable=self.progress_percent_var, style="V2.Muted.TLabel").grid(row=0, column=1)
        progress = ttk.Progressbar(progress_host, variable=self.progress_value, maximum=100, style="V2.Horizontal.TProgressbar", length=80)
        progress.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        self.progress = progress
        self.progress_bars.append(progress)
        self.generate_buttons.append(generate)
        self.pause_buttons.append(pause)
        self.cancel_buttons.append(cancel)


    def _build_footer(self) -> None:
        self.footer = ttk.Frame(self.root, style="V2.Side.TFrame", padding=(16, 12))
        self.footer.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.footer.columnconfigure(2, weight=1)
        ttk.Label(self.footer, text="Local · Offline", style="V2.Side.TLabel").grid(row=0, column=0, padx=(0, 22))
        ttk.Label(self.footer, text="Destino", style="V2.Side.TLabel").grid(row=0, column=1, padx=(0, 8))
        ttk.Entry(self.footer, textvariable=self.output_directory_var, state="readonly", width=15).grid(row=0, column=2, sticky="ew")
        choose = ttk.Button(self.footer, text="Alterar", style="V2.Footer.Secondary.TButton", command=self.on_choose_output_directory)
        choose.grid(row=0, column=3, padx=(12, 8))
        open_button = ttk.Button(self.footer, text="Abrir pasta", style="V2.Footer.Secondary.TButton", command=self.on_open_output_directory)
        open_button.grid(row=0, column=4)
        self.choose_output_buttons.append(choose)
        self.open_output_buttons.append(open_button)

    def _show_samples(self) -> None:
        self.workspace_tabs.select(self.samples_tab)

    def _build_samples_tab(self) -> None:
        self.samples_tab.columnconfigure(0, weight=1)
        self.samples_tab.rowconfigure(0, weight=1)
        preview_panel = self._panel(self.samples_tab, "Samples das 9 vozes")
        preview_panel.grid(row=0, column=0, sticky="nsew")
        preview_panel.rowconfigure(3, weight=1)
        ttk.Label(preview_panel, text="Ouça uma voz por vez. A reprodução não altera as vozes escolhidas para gerar.", style="V2.Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(0, SPACE_2))
        controls = ttk.Frame(preview_panel, style="V2.Plain.TFrame")
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
        if self.workspace_tabs.select() not in (str(self.samples_tab), str(self.help_tab)):
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
        sample_selected = self.workspace_tabs.select() == str(self.samples_tab)
        help_selected = self.workspace_tabs.select() == str(self.help_tab)
        active_key = "Samples" if sample_selected else None if help_selected else self.mode_var.get()
        for key, button in self.nav_buttons.items():
            button.configure(style="V2.NavActive.TButton" if key == active_key else "V2.Nav.TButton")
        self.help_button.configure(style='V2.NavActive.TButton' if help_selected else 'V2.Header.Secondary.TButton')
        if sample_selected or help_selected:
            self.activity_panel.grid_remove()
            self.action_bar.grid_remove()
            self.mode_status_var.set("Como usar" if help_selected else "Biblioteca de vozes")
        else:
            self.activity_panel.grid()
            self.action_bar.grid()
            self.mode_status_var.set(f"Modo ativo: {self.mode_var.get()}")
        if self.generate_buttons:
            self.generate_buttons[0].configure(state="disabled" if self.is_running or sample_selected or help_selected else "normal")

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
            button.configure(text="■" if active else "▶", style="V2.Playing.Icon.TButton" if active else "V2.Icon.TButton")

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
        samples_selected = hasattr(self, "workspace_tabs") and self.workspace_tabs.select() in (str(self.samples_tab), str(self.help_tab))
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
                self.status_var.set(
                    "Geração cancelada. Progresso temporário descartado."
                    if result.metadata.get('recovery_discarded', True) else
                    "Geração cancelada. Alguns arquivos temporários não puderam ser apagados."
                )
                return
            self._finish_error(self._friendly_error(result.errors[0] if result.errors else ""))
            return
        self.progress_value.set(100)
        self.progress_percent_var.set("100%")
        self.progress_stage_var.set("Concluído")
        final_mp3 = next((path for path in result.created_files if path.endswith("_complete.mp3")), "")
        self.output_var.set(f"MP3 salvo em: {self._display_output_path(final_mp3)}")
        reused = result.metadata.get("reused_chunks", 0)
        self.status_var.set(f"Áudio criado com sucesso. {reused} trechos recuperados." if reused else "Áudio criado com sucesso.")

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
