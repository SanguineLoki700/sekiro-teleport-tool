"""Manual coordinate entry and editing; all game/disk work uses existing queues."""
from __future__ import annotations

import tkinter as tk
from uuid import uuid4

from teleport_core import parse_coordinates

BG = "#353830"
TEXT = "#eee5cf"
MUTED = "#c1bcae"


class CoordinateEditor:
    def __init__(self, app, name=None):
        self.app = app
        self.original_name = name
        self.expected = list(app.locations[name]) if name is not None else None
        self.pending = None
        self.window = tk.Toplevel(app.root)
        self.window.title("Edit location" if name is not None else "Manual coordinates")
        self.window.geometry("490x480")
        self.window.resizable(False, False)
        self.window.configure(bg=BG)
        self.window.transient(app.root)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda e: self.close())
        self.window.bind("<Control-Return>", lambda e: self.save())
        self.name = tk.StringVar(self.window, value=name if name is not None else app.view.name_entry.get().strip())
        self.values = [tk.StringVar(self.window, value=repr(v) if self.expected is not None else "")
                       for v in (self.expected if self.expected is not None else (None, None, None))]
        self.status = tk.StringVar(self.window, value="Changes are saved only when you click Save.")
        body = tk.Frame(self.window, bg=BG, padx=22, pady=18)
        body.pack(fill="both", expand=True)
        self.title_label = self.label(body, "Edit saved location" if name is not None else "Manual coordinates", 18)
        self.title_label.pack(anchor="w")
        self.label(body, "Enter X, Y and Z to save a position or travel to it.", 11, MUTED).pack(anchor="w", pady=(5, 15))
        self.name_label = self.label(body, "Location name" if name is not None else "Location name (optional)", 11)
        self.name_label.pack(anchor="w")
        self.name_entry = self.entry(body, self.name)
        self.name_entry.pack(fill="x", ipady=5, pady=(5, 12))
        fields = tk.Frame(body, bg=BG)
        fields.pack(fill="x")
        self.entries = [self.name_entry]
        for index, (axis, value) in enumerate(zip("XYZ", self.values)):
            fields.columnconfigure(index, weight=1)
            column = tk.Frame(fields, bg=BG)
            column.grid(row=0, column=index, sticky="ew", padx=(0 if index == 0 else 10, 0))
            self.label(column, axis, 12).pack(anchor="w")
            entry = self.entry(column, value)
            entry.pack(fill="x", ipady=6, pady=(4, 0))
            self.entries.append(entry)
        self.current_button = self.button(body, "Use current player position", self.read_current)
        self.current_button.pack(fill="x", pady=(14, 9))
        self.status_label = tk.Label(body, textvariable=self.status, bg=BG, fg=MUTED,
            font=("Segoe UI", 10), wraplength=440, justify="left", anchor="w", height=3)
        self.status_label.pack(fill="x")
        self.label(body, "Coordinates do not load maps. Use a point in the same loaded area.",
                   10, MUTED, wraplength=440, justify="left").pack(anchor="w", pady=(6, 12))
        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", side="bottom")
        self.save_button = self.button(actions, "Save changes" if name is not None else "Save location", self.save)
        self.save_button.pack(side="left")
        self.teleport_button = self.button(actions, "Teleport", self.teleport)
        self.teleport_button.pack(side="left", padx=9)
        self.button(actions, "Close", self.close).pack(side="right")
        self.window.update_idletasks()
        self.window.geometry(f"490x{max(480, body.winfo_reqheight())}")
        self.refresh_state()
        self.window.after(100, self.entries[1].focus_set)

    def label(self, parent, text, size=12, color=TEXT, **kw):
        return tk.Label(parent, text=text, font=("Georgia", size), bg=BG, fg=color, **kw)

    def entry(self, parent, variable):
        return tk.Entry(parent, textvariable=variable, font=("Segoe UI", 11), width=12,
                        bg="#24271f", fg=TEXT, insertbackground=TEXT, relief="flat",
                        highlightthickness=1, highlightbackground="#8b8063", highlightcolor="#d68d43")

    def button(self, parent, text, command):
        return tk.Button(parent, text=text, command=command, font=("Georgia", 10),
                         bg="#1c1e1b", fg=TEXT, activebackground="#a65a27", activeforeground=TEXT,
                         disabledforeground="#888576", relief="flat", padx=13, pady=8, cursor="hand2")

    def exists(self):
        return bool(self.window.winfo_exists())

    def set_status(self, text, error=False):
        self.status.set(text)
        self.status_label.configure(fg="#f4b29b" if error else "#d4e2bd")

    def refresh_state(self):
        if not self.exists():
            return
        idle = self.pending is None
        for entry in self.entries:
            entry.configure(state="normal" if idle else "disabled")
        self.save_button.configure(state="normal" if idle and self.app.store_ready else "disabled")
        for button in (self.current_button, self.teleport_button):
            button.configure(state="normal" if idle and self.app.game_ready else "disabled")

    def start(self, kind, *args, disk=False):
        if self.pending is not None:
            return
        request = uuid4().hex
        self.pending = request
        accepted = self.app.workers.submit(kind, request, *args, disk=disk)
        if not accepted:
            self.pending = None
            self.set_status("The action could not be queued. Please try again in a moment.", True)
        else:
            self.set_status("Saving…" if disk else "Reading player position…" if kind == "read_coordinates" else "Teleporting…")
        self.refresh_state()

    def read_current(self):
        if self.pending is None and self.app.game_ready:
            self.start("read_coordinates")

    def parse(self):
        try:
            return parse_coordinates([value.get() for value in self.values])
        except ValueError as exc:
            self.set_status(str(exc), True)
            return None

    def save(self):
        if self.pending is not None or not self.app.store_ready:
            return
        pos = self.parse()
        if pos is not None:
            self.start("save_coordinates", self.original_name, self.name.get().strip(), pos, self.expected, disk=True)

    def teleport(self):
        if self.pending is not None or not self.app.game_ready:
            return
        pos = self.parse()
        if pos is not None:
            self.start("teleport_coordinates", pos)

    def handle(self, kind, request, *args):
        if not self.exists() or request != self.pending:
            return
        self.pending = None
        if kind == "coordinate_saved":
            name, pos = args
            was_existing = self.original_name is not None
            self.original_name = name
            self.expected = list(pos)
            self.name.set(name)
            self.save_button.configure(text="Save changes")
            self.window.title("Edit location")
            self.title_label.configure(text="Edit saved location")
            self.name_label.configure(text="Location name")
            self.set_status(f"Updated: {name}. The previous record is kept in the backup." if was_existing else f"Saved: {name}.")
        elif kind == "coordinate_read":
            for variable, number in zip(self.values, args[0]):
                variable.set(repr(number))
            self.set_status("Current position filled in. Click Save changes to update the record." if self.original_name else
                            "Current position filled in. Click Save location to keep it.")
        elif kind == "coordinate_teleported":
            self.set_status("Teleported to the entered coordinates. Saved records were not changed.")
        else:
            self.set_status(args[0], True)
        self.refresh_state()

    def close(self):
        self.window.destroy()
