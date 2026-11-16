from _rc_bootstrap import V2_ROOT

import sys
import os
import tkinter as tk
from tkinter import ttk

from v2_kokoro.app.ui.main_window import KokoroV2Window, MODE_DIALOGUE_LABEL


class Preview:
    voice_id = None
    def stop(self): pass
    def close(self): pass
    def current_mode(self): return 'stopped'


root = tk.Tk()
root.withdraw()
errors = []
root.report_callback_exception = lambda *args: errors.append(args)
window = KokoroV2Window(root, preview_player=Preview())
assert [icon.width() for icon in window._window_icons] == [16, 24, 32, 48, 64, 128, 256]
window.set_mode(MODE_DIALOGUE_LABEL)
root.deiconify()
for scaling, size in ((4/3, '1280x800'), (5/3, '1000x680'), (2, '1200x800')):
    root.tk.call('tk', 'scaling', scaling)
    root.geometry(size)
    root.update()
    inspector = window.dialogue_tab.winfo_children()[0]
    assert inspector.canvas.winfo_height() > 100
    if inspector.content.winfo_reqheight() > inspector.canvas.winfo_height():
        assert inspector.scrollbar.winfo_ismapped()
    assert window.dialogue_text_input.winfo_height() > 100
    assert window.header_art.winfo_x() >= window.brand_title.winfo_x() + window.brand_title.winfo_reqwidth()
    assert window.header_art.winfo_x() + window.header_art.winfo_width() <= window.nav_buttons['Narração'].winfo_x()
    assert inspector.relief_footer.winfo_ismapped()
    assert inspector.relief_footer.itemcget(inspector._relief_item, 'state') == 'normal'
    assert inspector.relief_footer.winfo_y() >= inspector.canvas.winfo_y() + inspector.canvas.winfo_height()
    for button in (window.generate_button, window.cancel_button, window.choose_output_button, window.open_output_button):
        assert button.winfo_ismapped()
        assert button.winfo_rootx() >= root.winfo_rootx()
        assert button.winfo_rootx() + button.winfo_width() <= root.winfo_rootx() + root.winfo_width()
        assert button.winfo_rooty() + button.winfo_height() <= root.winfo_rooty() + root.winfo_height()
window.dialogue_text_input.insert('1.0', 'A: Hello.\nB: Good morning.')
window.help_button.invoke()
root.update()
assert window.workspace_tabs.select() == str(window.help_tab)
assert window.help_button.cget('style') == 'V2.NavActive.TButton'
assert str(window.help_text.cget('state')) == 'disabled'
assert 'A: ou B:' in window.help_text.get('1.0', 'end')
help_content = window.help_text.get('1.0', 'end-1c')
assert help_content.index('Uso responsável') > help_content.index('Antes de usar o áudio')
assert 'Repudiamos e não incentivamos' in help_content
assert 'Cada usuário é responsável' in help_content
assert window.help_text.tag_cget('heading', 'font') != window.help_text.cget('font')
assert not window.action_bar.winfo_ismapped()
window.set_mode(MODE_DIALOGUE_LABEL)
root.update()
assert window.action_bar.winfo_ismapped()
assert window.dialogue_text_input.get('1.0', 'end-1c') == 'A: Hello.\nB: Good morning.'
window._show_samples()
root.update()
window._highlight_preview('af_heart')
assert window.preview_rows['af_heart'][3].cget('style') == 'V2.Playing.Icon.TButton'
window._highlight_preview(None)
assert all(row[3].cget('style') == 'V2.Icon.TButton' for row in window.preview_rows.values())
assert not errors, errors
if os.name == 'nt':
    import ctypes
    user32 = ctypes.windll.user32
    user32.GetParent.restype = ctypes.c_void_p
    user32.SendMessageW.restype = ctypes.c_void_p
    hwnd = user32.GetParent(root.winfo_id())
    # WM_GETICON: the window itself supplies both taskbar and titlebar icons.
    assert user32.SendMessageW(ctypes.c_void_p(hwnd), 0x7F, 0, 0)
    assert user32.SendMessageW(ctypes.c_void_p(hwnd), 0x7F, 1, 0)
    from ctypes import wintypes
    class IconInfo(ctypes.Structure):
        _fields_ = [('icon', wintypes.BOOL), ('x', wintypes.DWORD), ('y', wintypes.DWORD),
                    ('mask', wintypes.HBITMAP), ('color', wintypes.HBITMAP)]
    class Bitmap(ctypes.Structure):
        _fields_ = [('type', wintypes.LONG), ('width', wintypes.LONG), ('height', wintypes.LONG),
                    ('stride', wintypes.LONG), ('planes', wintypes.WORD), ('bits', wintypes.WORD),
                    ('data', ctypes.c_void_p)]
    user32.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(IconInfo)]
    gdi32 = ctypes.windll.gdi32
    gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    for kind in (0, 1):
        info, bitmap = IconInfo(), Bitmap()
        icon = user32.SendMessageW(ctypes.c_void_p(hwnd), 0x7F, kind, 0)
        assert user32.GetIconInfo(icon, ctypes.byref(info))
        try:
            assert gdi32.GetObjectW(info.color, ctypes.sizeof(bitmap), ctypes.byref(bitmap))
            assert (bitmap.width, bitmap.height) == (256, 256)
        finally:
            gdi32.DeleteObject(info.color)
            gdi32.DeleteObject(info.mask)
assert window.narration_box.cget('style') == 'V2.Sculpted.TCombobox'
assert str(window.narration_box.cget('state')) == 'readonly'
styles = ttk.Style(root)
assert styles.lookup('V2.Dialogue.Side.TLabel', 'background') == '#DDE8E4'
assert styles.lookup('V2.Dialogue.Side.TLabel', 'foreground') == '#26372F'
assert styles.lookup('V2.Side.TLabel', 'background') == '#DCE5DA'
assert styles.lookup('V2.Dialogue.Sculpted.TCombobox', 'arrowcolor') == '#285B50'
assert window.dialogue_text_input.cget('background') == '#FFFFFF'
assert 'torch' not in sys.modules and 'kokoro' not in sys.modules
assert 'v2_kokoro.app.core.job_runner' not in sys.modules
window.on_close()
print('Organic UI: small windows, 100/125/150% scale, scrollable inspector, visible actions, help and lazy backend OK')
