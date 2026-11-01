import pytest
from button_feedback import ButtonFeedback


@pytest.mark.parametrize("key", ["save", "travel"])
def test_action_never_starts_highlighted(key):
    assert not ButtonFeedback().highlighted(key)


def test_click_then_leave_clears_action_feedback():
    state = ButtonFeedback()
    state.pointer_moved("save")
    state.mouse_clicked("save")
    assert state.highlighted("save")
    state.pointer_left()
    assert not state.highlighted("save")


def test_switching_buttons_and_moving_to_empty_space_clears_old_action():
    state = ButtonFeedback()
    state.pointer_moved("save")
    state.pointer_moved("travel")
    assert not state.highlighted("save")
    assert state.highlighted("travel")
    state.pointer_moved(None)
    assert not state.highlighted("travel")


def test_keyboard_focus_is_distinct_and_clears_when_mouse_takes_over():
    state = ButtonFeedback()
    state.cycle(["save", "load", "travel"])
    assert state.highlighted("save")
    state.cycle(["save", "load", "travel"])
    assert state.highlighted("load")
    state.pointer_moved(None)
    assert not state.highlighted("load")


def test_focus_loss_clears_keyboard_and_mouse_feedback():
    state = ButtonFeedback(hovered="save", keyboard_focus="travel")
    state.focus_lost()
    assert not state.highlighted("save")
    assert not state.highlighted("travel")


def test_disabled_action_cannot_be_highlighted():
    state = ButtonFeedback(hovered="travel", keyboard_focus="travel")
    assert not state.highlighted("travel", enabled=False)


def test_reverse_tab_enters_from_last_enabled_action():
    state = ButtonFeedback()
    state.cycle(["save", "load", "travel"], -1)
    assert state.keyboard_focus == "travel"
    state.cycle([])
    assert state.keyboard_focus is None
