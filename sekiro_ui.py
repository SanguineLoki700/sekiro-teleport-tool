"""Compact, resizable utility with Sekiro-inspired paper, frame and ink textures."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageTk

from button_feedback import ButtonFeedback
from brush_texture import extract_brush

TEXT = "#e7e4d9"
MUTED = "#c7c1b3"
AMBER = "#ffce94"
COLORS = {"ok": "#d4e2bd", "warning": "#ffe0a7", "error": "#ffc7ae"}
ROW_HEIGHT = 29


class SekiroMenu:
    def __init__(self, app, asset_dir):
        self.app = app
        self.root = app.root
        self.canvas = tk.Canvas(self.root, background="#181816", highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="both", expand=True)
        self.background = Image.open(asset_dir / "compact-background.png").convert("RGB")
        source = Image.open(asset_dir / "menu-background.png").convert("RGB").resize((1920, 1080), Image.Resampling.LANCZOS)
        self.brush_sources = {kind: extract_brush(source, kind) for kind in ("black", "orange")}
        self.logo_source = Image.open(asset_dir / "sekiro-teleport.png").convert("RGBA")
        self.scale = 1
        self.width, self.height = 600, 700
        self.art = self.logo = None
        self.size = None
        self.brush_cache = {}
        self.font_cache = {}
        self.buttons = {}
        self.feedback = ButtonFeedback()
        self.resize_job = None
        self.scroll = 0
        self.list_top = 350
        self.visible_rows = 6
        self.name_entry = self.entry()
        self.search_entry = self.entry(app.query)
        self.name_window = self.canvas.create_window(0, 0, window=self.name_entry, anchor="nw", tags="entry")
        self.search_window = self.canvas.create_window(0, 0, window=self.search_entry, anchor="nw", tags="entry")
        self.name_entry.bind("<Return>", lambda e: app.capture_named())
        self.canvas.bind("<Configure>", self.schedule_resize)
        self.canvas.bind("<Motion>", self.motion)
        self.canvas.bind("<Leave>", self.leave)
        self.canvas.bind("<FocusOut>", self.focus_lost)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<Up>", lambda e: self.move_selection(-1))
        self.canvas.bind("<Down>", lambda e: self.move_selection(1))
        self.canvas.bind("<Prior>", lambda e: app.change_page(-1))
        self.canvas.bind("<Next>", lambda e: app.change_page(1))
        self.canvas.bind("<Return>", self.activate_focused)
        self.canvas.bind("<space>", self.activate_focused)
        self.canvas.bind("<Tab>", self.focus_next)
        self.canvas.bind("<Shift-Tab>", lambda e: self.focus_next(e, -1))
        self.canvas.bind("<Button-1>", self.click)
        self.canvas.bind("<Double-1>", self.double_click)
        self.canvas.bind("<Escape>", self.clear_selection)
        for entry in (self.name_entry, self.search_entry):
            entry.bind("<FocusIn>", self.focus_lost)
            entry.bind("<Escape>", lambda e: self.canvas.focus_set())

    def entry(self, variable=None):
        return tk.Entry(self.canvas, textvariable=variable, bg="#33342e", fg=TEXT,
                        insertbackground=TEXT, selectbackground="#8c582c", relief="flat",
                        highlightthickness=1, highlightbackground="#77715e", highlightcolor="#c89a53")

    def xy(self, x, y):
        return x*self.scale, y*self.scale

    def font(self, size):
        pixels = max(10, round(size*self.scale))
        if pixels not in self.font_cache:
            self.font_cache[pixels] = tkfont.Font(self.root, family="Georgia", size=-pixels)
        return self.font_cache[pixels]

    def text(self, x, y, text, size=15, color=TEXT, anchor="w", width=None, **kw):
        px, py = self.xy(x, y)
        args = {"text": text, "font": self.font(size), "anchor": anchor, "tags": "scene", **kw}
        if width:
            args["width"] = round(width*self.scale)
        shadow = dict(args)
        tags = args["tags"] if isinstance(args["tags"], tuple) else (args["tags"],)
        shadow["tags"] = tuple(t for t in tags if not t.endswith("-text"))
        self.canvas.create_text(px, py+max(1, self.scale), fill="#25251f", **shadow)
        return self.canvas.create_text(px, py, fill=color, **args)

    def brush(self, kind, width, height):
        key = (kind, round(width*self.scale), round(height*self.scale))
        if key not in self.brush_cache:
            crop = self.brush_sources[kind]
            crop = crop.resize((max(1, key[1]), max(1, key[2])), Image.Resampling.LANCZOS)
            self.brush_cache[key] = ImageTk.PhotoImage(crop)
        return self.brush_cache[key]

    def button(self, key, rect, title, action, enabled=True, small=False):
        x1, y1, x2, y2 = rect
        tag = "button-"+key
        active = self.feedback.highlighted(key, enabled)
        image_item = self.canvas.create_image(*self.xy((x1+x2)/2, (y1+y2)/2),
                        image=self.brush("orange" if active else "black", x2-x1, y2-y1), tags=("scene", tag))
        self.text((x1+x2)/2, (y1+y2)/2, title, 12 if small else 15,
                  AMBER if active else TEXT if enabled else "#9a9587", "center", tags=("scene", tag, tag+"-text"))
        self.buttons[key] = {"action": action, "enabled": enabled, "rect": rect, "image": image_item, "tag": tag}

    def update_feedback(self):
        for key, button in self.buttons.items():
            active = self.feedback.highlighted(key, button["enabled"])
            x1, y1, x2, y2 = button["rect"]
            self.canvas.itemconfigure(button["image"], image=self.brush("orange" if active else "black", x2-x1, y2-y1))
            self.canvas.itemconfigure(button["tag"]+"-text", fill=AMBER if active else TEXT if button["enabled"] else "#9a9587")
        enabled_hover = self.feedback.hovered in self.buttons and self.buttons[self.feedback.hovered]["enabled"]
        self.canvas.configure(cursor="hand2" if enabled_hover else "")

    def button_at(self, x, y):
        for key, button in self.buttons.items():
            x1, y1, x2, y2 = button["rect"]
            if x1 <= x <= x2 and y1 <= y <= y2:
                return key
        return None

    def motion(self, event):
        key = self.button_at(event.x/self.scale, event.y/self.scale)
        before = (self.feedback.hovered, self.feedback.keyboard_focus)
        self.feedback.pointer_moved(key)
        if before != (self.feedback.hovered, self.feedback.keyboard_focus):
            self.update_feedback()

    def leave(self, _event=None):
        self.feedback.pointer_left()
        self.update_feedback()

    def focus_lost(self, _event=None):
        self.feedback.focus_lost()
        self.update_feedback()

    def click(self, event):
        x, y = event.x/self.scale, event.y/self.scale
        self.canvas.focus_set()
        key = self.button_at(x, y)
        self.feedback.mouse_clicked(key)
        if key:
            self.invoke(key)
        else:
            index = self.record_at(x, y)
            self.app.selected = self.app.names[index] if index is not None else None
            self.draw()
        if not self.app.closing:
            self.update_feedback()

    def invoke(self, key):
        button = self.buttons.get(key)
        if button and button["enabled"]:
            button["action"]()

    def activate_focused(self, _event=None):
        if self.feedback.keyboard_focus in self.buttons:
            self.invoke(self.feedback.keyboard_focus)
        else:
            self.app.travel_selected()
        return "break"

    def focus_next(self, _event=None, direction=1):
        self.feedback.cycle([k for k, b in self.buttons.items() if b["enabled"]], direction)
        self.update_feedback()
        return "break"

    def clear_selection(self, _event=None):
        self.app.selected = None
        self.feedback.focus_lost()
        self.draw()
        return "break"

    def double_click(self, event):
        index = self.record_at(event.x/self.scale, event.y/self.scale)
        if index is not None:
            self.app.selected = self.app.names[index]
            self.app.travel_selected()
        return "break"

    def record_at(self, x, y):
        bottom = self.list_top+self.visible_rows*ROW_HEIGHT
        if 36 <= x <= self.width-36 and self.list_top <= y < bottom:
            index = self.scroll+int((y-self.list_top)//ROW_HEIGHT)
            if index < len(self.app.names):
                return index
        return None

    def schedule_resize(self, _event=None):
        if self.resize_job:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(70, self.resize)

    def resize(self):
        self.resize_job = None
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 100 or h < 100:
            return
        self.scale = min(w/600, h/660, 1.4)
        self.width, self.height = w/self.scale, h/self.scale
        self.list_top = 350
        self.visible_rows = max(1, int((self.height-166-self.list_top)//ROW_HEIGHT))
        if self.size != (w, h):
            self.art = ImageTk.PhotoImage(self.background.resize((w, h), Image.Resampling.LANCZOS))
            self.logo = ImageTk.PhotoImage(self.logo_source.resize((round(265*self.scale), round(88*self.scale)), Image.Resampling.LANCZOS))
            self.brush_cache.clear()
            self.font_cache.clear()
            self.size = (w, h)
        for entry, item, rect in ((self.name_entry, self.name_window, (36, 237, self.width-172, 271)),
                                  (self.search_entry, self.search_window, (83, 309, self.width-36, 339))):
            x1, y1, x2, y2 = rect
            entry.configure(font=self.font(14))
            self.canvas.coords(item, *self.xy(x1, y1))
            self.canvas.itemconfigure(item, width=round((x2-x1)*self.scale), height=round((y2-y1)*self.scale))
        self.feedback.focus_lost()
        self.draw()

    def rule(self, y):
        self.canvas.create_line(*self.xy(34, y), *self.xy(self.width-34, y), fill="#494638", width=max(1, round(self.scale)), tags="scene")

    def draw(self):
        if self.art is None:
            return
        a, w, h = self.app, self.width, self.height
        self.canvas.delete("scene")
        self.buttons.clear()
        self.canvas.create_image(0, 0, anchor="nw", image=self.art, tags="scene")
        self.canvas.create_image(*self.xy(w/2, 63), image=self.logo, tags="scene")
        state = "Preview · simulated character" if a.demo else "Connected and ready" if a.game_ready else "Connection unavailable · see Diagnostics" if a.connection_state == "error" else "Waiting for Sekiro / player…"
        self.text(w/2, 121, "●  "+state, 13, COLORS["ok" if a.game_ready else "warning"], "center")
        self.button("save", (33, 143, w/2-5, 185), "Capture checkpoint  ·  F5", lambda: a.workers.submit("save"), a.game_ready)
        self.button("load", (w/2+5, 143, w-33, 185), "Return  ·  F9", lambda: a.workers.submit("load"), a.game_ready and a.quick is not None)
        quick = "  ·  ".join(f"{k} {v:.2f}" for k, v in zip("XYZ", a.quick)) if a.quick is not None else "No quick checkpoint captured"
        self.text(w/2, 201, quick, 12, MUTED, "center")
        self.text(36, 224, "Location name (optional)", 14)
        self.button("manual", (w-203, 211, w-33, 233), "Manual coordinates…", a.manual_coordinates, small=True)
        self.button("add", (w-164, 233, w-33, 275), "Save position", a.capture_named, a.game_ready and a.store_ready)
        self.text(36, 293, "Saved locations", 16)
        self.text(w-36, 293, f"{a.filtered_count:,} / {len(a.locations):,}", 12, MUTED, "e")
        self.text(36, 324, "Find", 13, MUTED)
        self.draw_records()
        travel_width = (w-72)/3
        self.button("travel", (33, h-157, 36+travel_width-3, h-118), "Travel", a.travel_selected, a.game_ready and a.selected_name() is not None)
        self.button("edit", (36+travel_width+1, h-157, 36+travel_width*2-3, h-118), "Edit", a.edit_selected, a.store_ready and a.selected_name() is not None)
        self.button("delete", (36+travel_width*2+1, h-157, w-33, h-118), "Remove", a.delete_selected, a.store_ready and a.selected_name() is not None)
        self.button("prev", (33, h-111, 70, h-82), "‹", lambda: a.change_page(-1), a.page > 0)
        self.text(118, h-97, f"{a.page+1} / {a.pages}", 12, MUTED, "center")
        self.button("next", (167, h-111, 204, h-82), "›", lambda: a.change_page(1), a.page+1 < a.pages)
        self.button("import", (w-218, h-111, w-127, h-82), "Import", a.import_locations, a.store_ready, small=True)
        self.button("export", (w-123, h-111, w-33, h-82), "Export", a.export_locations, a.store_ready, small=True)
        notice = a.notice_text if len(a.notice_text) <= 145 else a.notice_text[:120]+"… See Diagnostics."
        self.text(36, h-68, notice, 12, COLORS.get(a.notice_level, TEXT), width=w-72)
        self.rule(h-51)
        self.text(36, h-34, f"SanguineLoki700  ·  {a.version}", 10, MUTED)
        self.button("diagnostics", (w-240, h-48, w-139, h-20), "Diagnostics", a.diagnostics, small=True)
        self.button("reconnect", (w-135, h-48, w-33, h-20), "Reconnect", lambda: a.workers.submit("reconnect"), small=True)
        self.canvas.tag_raise("entry")

    def draw_records(self):
        a, w = self.app, self.width
        self.scroll = max(0, min(self.scroll, max(0, len(a.names)-self.visible_rows)))
        for index, name in enumerate(a.names[self.scroll:self.scroll+self.visible_rows]):
            y = self.list_top+index*ROW_HEIGHT+ROW_HEIGHT/2
            selected = name == a.selected_name()
            if selected:
                self.canvas.create_image(*self.xy(w/2, y), image=self.brush("black", w-68, ROW_HEIGHT), tags="scene")
                self.text(44, y, "›", 16, AMBER)
            self.text(59, y, self.ellipsize(name, w-116, 14), 14)
            self.canvas.create_line(*self.xy(40, y+ROW_HEIGHT/2), *self.xy(w-40, y+ROW_HEIGHT/2), fill="#5b574a", tags="scene")
        if not a.names:
            middle = self.list_top+self.visible_rows*ROW_HEIGHT/2
            self.text(w/2, middle-10, "No matching locations" if a.query.get().strip() else "No locations saved", 15, anchor="center")
            self.text(w/2, middle+14, "Save a position above or import your records.", 12, MUTED, "center")
        if len(a.names) > self.visible_rows:
            full = self.visible_rows*ROW_HEIGHT
            top = self.list_top+full*self.scroll/len(a.names)
            thumb = full*self.visible_rows/len(a.names)
            self.canvas.create_line(*self.xy(w-36, self.list_top), *self.xy(w-36, self.list_top+full), fill="#4a493f", tags="scene")
            self.canvas.create_line(*self.xy(w-36, top), *self.xy(w-36, top+thumb), fill="#c3b698", width=max(2, round(3*self.scale)), tags="scene")

    def wheel(self, event):
        y = event.y/self.scale
        if self.list_top <= y <= self.list_top+self.visible_rows*ROW_HEIGHT:
            self.scroll += -3 if event.delta > 0 else 3
            self.draw()
        return "break"

    def move_selection(self, delta):
        names = self.app.names
        if names:
            current = self.app.selected_name()
            index = names.index(current) if current in names else (-1 if delta > 0 else len(names))
            index = max(0, min(len(names)-1, index+delta))
            self.app.selected = names[index]
            if index < self.scroll:
                self.scroll = index
            if index >= self.scroll+self.visible_rows:
                self.scroll = index-self.visible_rows+1
            self.feedback.focus_lost()
            self.draw()
        return "break"

    def ellipsize(self, text, width, size):
        font = self.font(size)
        pixels = width*self.scale
        if font.measure(text) <= pixels:
            return text
        low, high = 0, len(text)
        while low < high:
            mid = (low+high+1)//2
            if font.measure(text[:mid]+"…") <= pixels:
                low = mid
            else:
                high = mid-1
        return text[:low]+"…"
