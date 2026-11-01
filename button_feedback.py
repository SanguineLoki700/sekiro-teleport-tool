"""Transient action feedback, kept separate from a selected destination."""
from dataclasses import dataclass


@dataclass
class ButtonFeedback:
    hovered: str | None = None
    keyboard_focus: str | None = None

    def pointer_moved(self, key):
        self.hovered = key
        self.keyboard_focus = None

    def pointer_left(self):
        self.hovered = None

    def mouse_clicked(self, key):
        self.hovered = key
        self.keyboard_focus = None

    def focus_lost(self):
        self.hovered = None
        self.keyboard_focus = None

    def cycle(self, keys, direction=1):
        self.hovered = None
        if not keys:
            self.keyboard_focus = None
            return
        if self.keyboard_focus in keys:
            index = (keys.index(self.keyboard_focus) + direction) % len(keys)
        else:
            index = 0 if direction > 0 else len(keys) - 1
        self.keyboard_focus = keys[index]

    def highlighted(self, key, enabled=True):
        return enabled and key in (self.hovered, self.keyboard_focus)
