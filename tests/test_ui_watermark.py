from _rc_bootstrap import V2_ROOT

import tkinter as tk
from unittest.mock import Mock

from v2_kokoro.app.ui.main_window import KokoroV2Window, MODE_DIALOGUE_LABEL


root = tk.Tk()
root.withdraw()
preview = Mock()
preview.voice_id = None
preview.current_mode.return_value = 'stopped'
ui = KokoroV2Window(root, preview_player=preview)
root.deiconify()
root.geometry('1280x800')
root.update()
for mode, editor, text in (
    ('Narração', ui.narration_text_input, 'This text must stay unchanged.'),
    (MODE_DIALOGUE_LABEL, ui.dialogue_text_input, 'A: Hello.\nB: Welcome.'),
):
    ui.set_mode(mode)
    editor.insert('1.0', text)
    root.update()
    editor.refresh_watermark()
    assert editor.get('1.0', 'end-1c') == text
    assert editor._mark.winfo_ismapped()
    editor.tag_add('sel', '1.0', 'end-1c')
    editor.refresh_watermark()
    assert not editor._mark.winfo_ismapped()
    editor.tag_remove('sel', '1.0', 'end')
    editor.insert('end', '\nAdditional text.' * 80)
    expected = editor.get('1.0', 'end-1c')
    editor.yview_moveto(1)
    root.update()
    editor.refresh_watermark()
    assert not editor._mark.winfo_ismapped()
    assert editor.get('1.0', 'end-1c') == expected
assert int(ui.action_bar.grid_info()['padx']) == 16
assert ui.brand_mark.logo_image.width() > 0
ui.on_close()
print('Watermark: narration/dialogue text preserved; mark hides for selection and overlapping content; full-width actions OK')
