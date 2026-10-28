from aikvm.console import keys_for_event, point_on_frame


def test_keyboard_shortcuts_and_navigation():
    assert keys_for_event('l', '\x0c', 0x4) == ['CTRL', 'l']
    assert keys_for_event('Down', '', 0) == ['DOWN']
    assert keys_for_event('A', 'A', 1) == ['SHIFT', 'a']
    assert keys_for_event('Shift_L', '', 1) is None


def test_preview_pointer_mapping_rejects_letterbox_and_maps_edges():
    assert point_on_frame(0, 0, 960, 540, 1920, 1080) == (0, 0)
    assert point_on_frame(959, 539, 960, 540, 1920, 1080) == (1918, 1078)
    assert point_on_frame(-1, 20, 960, 540, 1920, 1080) is None
    assert point_on_frame(960, 20, 960, 540, 1920, 1080) is None
    assert point_on_frame(0, 0, 0, 540, 1920, 1080) is None
