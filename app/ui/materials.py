"""Small static Tk images: rounded surfaces and tactile buttons, no blur loop."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
import math
import os
import struct
import zlib
from pathlib import Path
from v2_kokoro.app.ui.style_tokens import COLOR_DIALOGUE_SURFACE


def _load_brand_font():
    """Register before Tk caches font families; no system installation."""
    if os.name == 'nt':
        import ctypes
        path = Path(__file__).parent / 'assets/fonts/Manrope-Semibold.ttf'
        add_font = ctypes.windll.gdi32.AddFontResourceExW
        add_font.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        add_font(str(path.resolve()), 0x10, None)


_load_brand_font()


def brand_font(master):
    """Use the bundled 600-weight face privately, never install a system font."""
    from tkinter import font
    families = font.families(master)
    return next((name for name in ('Manrope ExtraLight SemiBold', 'Manrope SemiBold', 'Manrope Semibold', 'Manrope') if name in families), 'Segoe UI')


def window_icon_images(master, icon_path):
    """Reuse every PNG resolution in our ICO, without resizing a small bitmap."""
    data = Path(icon_path).read_bytes()
    count = struct.unpack_from('<H', data, 4)[0]
    images = []
    for index in range(count):
        size, offset = struct.unpack_from('<II', data, 6 + index * 16 + 8)
        images.append(tk.PhotoImage(master=master, data=data[offset:offset+size], format='png'))
    return images


def _rgb(color):
    return tuple(int(color[i:i+2], 16) for i in (1, 3, 5))


def _blend(base, top, alpha):
    return tuple(round(a + (b-a) * max(0, min(1, alpha))) for a, b in zip(base, top))


def _distance(x, y, left, top, right, bottom, radius):
    qx = abs(x - (left+right)/2) - (right-left)/2 + radius
    qy = abs(y - (top+bottom)/2) - (bottom-top)/2 + radius
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - radius


def _photo(master, width, height, pixel, *, alpha=False):
    if alpha:
        # PNG alpha lets the actual parent surface show through the shadow.
        # Precomposing against one fixed color leaves a rectangular matte.
        raw = bytearray()
        for y in range(height):
            raw.append(0)
            for x in range(width):
                raw.extend(pixel(x+.5, y+.5))

        def chunk(kind, data):
            return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)

        png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
               + chunk(b'IDAT', zlib.compress(bytes(raw))) + chunk(b'IEND', b''))
        return tk.PhotoImage(master=master, data=png, format='png')
    image = tk.PhotoImage(master=master, width=width, height=height)
    rows = []
    for y in range(height):
        rows.append('{' + ' '.join('#%02x%02x%02x' % pixel(x+.5, y+.5) for x in range(width)) + '}')
    image.put(' '.join(rows))
    return image


def pulse_image(master, size=40, backdrop='#E4EADF', *, watermark=False):
    """Rasterize the approved geometric pulse from scalable geometry."""
    bg = _rgb(backdrop)
    fg = _blend(bg, _rgb('#285B50'), .035) if watermark else _rgb('#285B50')
    width = round(size * 1.2)
    def pixel(x, y):
        x, y = x / size, y / size
        distances = [
            _distance(x, y, .27, .27, .47, .91, .1),
            _distance(x, y, .53, .10, .73, .85, .1),
            math.hypot(x-.91, y-.55)-.135,
            max(math.hypot(x-.23, y-.59)-.18, x-.23),
        ]
        coverage = max(0, min(1, .5 - min(distances) * size))
        return _blend(bg, fg, coverage)
    return _photo(master, width, size, pixel)


class WatermarkedText(tk.Text):
    """Faint mark in unused editor space; never part of the document."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._mark_image = pulse_image(self, 150, '#FFFFFF', watermark=True)
        self._mark = tk.Label(self, image=self._mark_image, background='#FFFFFF', bd=0, takefocus=False)
        self._pending_mark = None
        self.bind('<Configure>', self._schedule_mark, add='+')
        self.bind('<<Modified>>', self._modified, add='+')
        self.bind('<KeyRelease>', self._schedule_mark, add='+')
        self.bind('<ButtonPress-1>', lambda e: self._mark.place_forget(), add='+')
        self._mark.bind('<ButtonPress-1>', self._click_mark)

    def _click_mark(self, event):
        x = self._mark.winfo_x() + event.x
        y = self._mark.winfo_y() + event.y
        self._mark.place_forget()
        self.focus_set()
        self.mark_set('insert', self.index(f'@{x},{y}'))

    def _modified(self, event=None):
        if self.edit_modified():
            self.edit_modified(False)
            self._schedule_mark()

    def _schedule_mark(self, event=None):
        if self._pending_mark is None:
            self._pending_mark = self.after_idle(self.refresh_watermark)

    def refresh_watermark(self):
        self._pending_mark = None
        top = self.winfo_height() - 155
        visible = self.index('@0,0')
        end = self.index('end-1c')
        safe = top > 50 and self.winfo_width() > 240 and self.tag_ranges('sel') == ()
        while safe and self.compare(visible, '<=', end):
            line = self.dlineinfo(visible)
            if line is None:
                break
            if line[1] + line[3] >= top:
                safe = False
                break
            following = self.index(f'{visible} + 1 display lines')
            if self.compare(following, '<=', visible):
                break
            visible = following
        if safe:
            self._mark.place(relx=1, rely=1, anchor='se', x=-8, y=-5)
        else:
            self._mark.place_forget()


def relief_image(master, width=720, height=90, backdrop='#E4EADF'):
    """Bake sculpted waves once; no animation, texture dependency or resize work."""
    base = _rgb(backdrop)
    profiles = []
    for x in range(width):
        u = x / width
        fade = math.sin(math.pi * u) ** 2
        profiles.append((fade, height * (.40 + .18 * math.sin(u * math.pi * 2.3)),
                         height * (.78 + .16 * math.sin(u * math.pi * 2.3 + 1.8))))
    def pixel(x, y):
        fade, crest, lower = profiles[min(int(x), width-1)]
        fade *= math.sin(math.pi * y / height) ** .6
        light = 0.0
        for ridge in (crest, lower):
            distance = y-ridge
            light += .76 * math.exp(-((distance+1.2)/1.8)**2)
            light += .27 * math.exp(-((distance+height*.10)/(height*.19))**2)
            light -= .30 * math.exp(-((distance-height*.08)/(height*.12))**2)
        return _blend(base, (255, 255, 249) if light >= 0 else (113, 140, 106), abs(light)*fade)
    return _photo(master, width, height, pixel)


class Inspector(ttk.Frame):
    """Scroll only this panel when DPI or a small window needs extra room."""

    def __init__(self, master, *, dialogue=False):
        backdrop = COLOR_DIALOGUE_SURFACE if dialogue else '#DCE5DA'
        super().__init__(master, style='V2.Dialogue.Side.TFrame' if dialogue else 'V2.Side.TFrame', padding=12)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, width=264, background=backdrop, highlightthickness=0, bd=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.scrollbar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.content = ttk.Frame(self.canvas, style='V2.Dialogue.SideInner.TFrame' if dialogue else 'V2.SideInner.TFrame')
        self.item = self.canvas.create_window(0, 0, window=self.content, anchor='nw')
        self.relief_footer = None
        if dialogue:
            self.relief_footer = tk.Canvas(self, width=264, height=64, background=backdrop, highlightthickness=0, bd=0)
            self.relief_footer.grid(row=1, column=0, columnspan=2, sticky='ew')
        relief_host = self.relief_footer if dialogue else self.canvas
        self._relief = relief_image(relief_host, 264, 64 if dialogue else 100, backdrop)
        self._relief_item = relief_host.create_image(0, 64 if dialogue else 0, image=self._relief,
                                                   anchor='sw', state='normal' if dialogue else 'hidden')
        if dialogue:
            self.relief_footer.bind('<Configure>', lambda event: relief_host.coords(
                self._relief_item, max(0, (event.width-264)/2), event.height))
        self._width = None
        self._scroll_visible = False
        self.content.bind('<Configure>', self._layout)
        self.canvas.bind('<Configure>', self._layout)
        self.canvas.bind('<MouseWheel>', self._wheel)

    def _layout(self, event=None):
        width = self.canvas.winfo_width()
        if width != self._width:
            self._width = width
            self.canvas.itemconfigure(self.item, width=width)
        self.canvas.configure(scrollregion=self.canvas.bbox(self.item))
        needed = self.content.winfo_reqheight() > self.canvas.winfo_height()
        free = self.canvas.winfo_height() - self.content.winfo_reqheight()
        if self.relief_footer is None:
            self.canvas.coords(self._relief_item, max(0, (width-264)/2), self.canvas.winfo_height())
            self.canvas.itemconfigure(self._relief_item, state='normal' if free > 110 else 'hidden')
        if needed != self._scroll_visible:
            self._scroll_visible = needed
            if needed:
                self.scrollbar.grid(row=0, column=1, sticky='ns')
            else:
                self.scrollbar.grid_remove()
                self.canvas.yview_moveto(0)

    def _wheel(self, event):
        if self.content.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, 'units')
        return 'break'


def surface_image(master, fill, border, backdrop, *, shadow=True, width=48, height=40, transparent=True, finish=0.0):
    face, edge = _rgb(fill), _rgb(border)
    def pixel(x, y):
        distance = _distance(x, y, 4, 3, width-4, height-7, 8)
        color = _rgb('#465A49')
        alpha = 0.0
        if shadow:
            sd = max(0, _distance(x, y, 4, 6, width-4, height-4, 8))
            alpha = .23 * math.exp(-sd*sd/9)
        button_face, button_edge = face, edge
        if finish:
            # Restrained lighting, baked into the state image once. No animation.
            reflection = math.exp(-((x/width-.72)**2/.23 + (y/height-.08)**2/.12))
            button_face = _blend(face, (255, 255, 255), .065 * finish * reflection)
            button_edge = _blend(edge, (255, 255, 255), .4 * finish * reflection)
            # A small green bounce, without changing the established palette.
            bounce = math.exp(-((x/width-.16)**2/.09 + (y/height-.77)**2/.18))
            button_face = _blend(button_face, _rgb('#6B9984'), .035 * finish * bounce)
            # Broad face lighting survives nine-slice stretching; avoid a flat fill.
            light = math.exp(-((y/height-.19)/.25)**2)
            shade = math.exp(-((y/height-.78)/.18)**2)
            button_face = _blend(button_face, (255, 255, 250), .12 * finish * light)
            button_face = _blend(button_face, (103, 127, 102), .07 * finish * shade)
            glow = .055 * max(0, finish-1) * math.exp(-max(distance, 0)**2/12)
            combined = glow + alpha * (1-glow)
            if combined:
                color = tuple((b*glow + a*alpha*(1-glow))/combined for a, b in zip(color, _rgb('#799C87')))
            alpha = combined
        for top, coverage in ((button_edge, .7 * max(0, min(1, .5-distance))),
                              (button_face, max(0, min(1, -.3-distance)))):
            combined = coverage + alpha * (1-coverage)
            if combined:
                color = tuple((b*coverage + a*alpha*(1-coverage))/combined for a, b in zip(color, top))
            alpha = combined
        if transparent:
            return tuple(round(c) for c in color) + (round(alpha*255),)
        return _blend(_rgb(backdrop), color, alpha)
    return _photo(master, width, height, pixel, alpha=transparent)
