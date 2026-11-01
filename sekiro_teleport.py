"""Sekiro Teleport: Windows desktop application."""
from __future__ import annotations

import argparse
import ctypes
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import sys
import tempfile
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from teleport_core import VERSION, PAGE_SIZE, DataFolderLock, LocationStore, application_dir, default_data_dir, previous_data_dir, filtered_page
from connection_diagnostics import diagnostic_text
from coordinate_editor import CoordinateEditor
from teleport_workers import Workers
from sekiro_ui import SekiroMenu


def asset_dir():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"


class SekiroTeleport:
    def __init__(self, root, directory, demo=False):
        self.root = root
        self.directory = Path(directory)
        self.demo = demo
        self.version = VERSION
        self.locations = {}
        self.page = 0
        self.pages = 1
        self.filtered_count = 0
        self.names = []
        self.selected = None
        self.store_ready = False
        self.game_ready = False
        self.quick = None
        self.closing = False
        self.search_after = None
        self.notice_deadline = 0
        self.connection_state = "waiting"
        self.connection_text = "Looking for Sekiro…"
        self.notice_text = "Preparing travel records…"
        self.notice_level = ""
        self.connection_report = {}
        self.diagnostic_window = None
        self.diagnostic_body = None
        self.diagnostic_last_text = None
        self.coordinate_editor = None
        self.storage_mode = "portable" if self.directory.resolve() == application_dir().resolve() else "custom"
        self.query = tk.StringVar(root)
        root.title("Sekiro Teleport" + (" — PREVIEW" if demo else ""))
        root.geometry("600x700")
        root.minsize(520, 600)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.iconbitmap(default=str(asset_dir() / "sekiro-original.ico"))
        old_records = previous_data_dir() / "locations.json"
        legacy = () if demo else (old_records, application_dir() / "locations.json", Path.cwd() / "locations.json")
        recovery = old_records if not demo and self.storage_mode == "portable" else None
        self.workers = Workers(LocationStore(directory, legacy, recovery_source=recovery), demo=demo)
        self.view = SekiroMenu(self, asset_dir())
        self.query.trace_add("write", self.schedule_search)
        root.bind("<F5>", lambda e: self.local_hotkey("save"))
        root.bind("<F9>", lambda e: self.local_hotkey("load"))
        self.workers.start()
        root.after(40, self.pump)

    def local_hotkey(self, action):
        focused = self.root.focus_get()
        if focused is not None and (isinstance(focused, (tk.Entry, tk.Text)) or focused.winfo_toplevel() != self.root):
            return
        self.workers.submit(action)
        return "break"

    def show_notice(self, message, level="ok"):
        self.notice_text = message
        self.notice_level = level
        self.notice_deadline = time.monotonic() + (14 if level == "ok" else 60)
        self.view.draw()

    def pump(self):
        if self.closing:
            return
        changed = False
        for _ in range(80):
            try:
                event = self.workers.events.get_nowait()
            except queue.Empty:
                break
            kind, *args = event
            if kind == "diagnostics":
                self.connection_report = args[0]
                self.refresh_diagnostics()
                continue
            changed = True
            if kind == "connection":
                self.connection_state, self.connection_text = args
                self.game_ready = self.connection_state == "ready"
            elif kind == "locations":
                self.locations = args[0]
                self.refresh_list(draw=False)
            elif kind == "storage":
                self.store_ready = args[0]
                if not self.notice_deadline:
                    self.notice_text = "F5: Capture checkpoint     F9: Return     Select a record to travel."
            elif kind == "notice":
                self.show_notice(*args)
            elif kind == "quick":
                self.quick = args[0]
            elif kind == "saved":
                if self.view.name_entry.get().strip() == args[0]:
                    self.view.name_entry.delete(0, "end")
            elif kind in ("coordinate_saved", "coordinate_read", "coordinate_teleported", "coordinate_error"):
                if self.coordinate_editor is not None:
                    self.coordinate_editor.handle(kind, *args)
                if kind == "coordinate_saved":
                    self.focus_saved_location(args[1])
        if self.notice_deadline and time.monotonic() > self.notice_deadline:
            self.notice_text = "F5: Capture checkpoint     F9: Return     Travel within the same loaded area."
            self.notice_level = ""
            self.notice_deadline = 0
            changed = True
        if changed:
            self.view.draw()
            if self.coordinate_editor is not None:
                self.coordinate_editor.refresh_state()
        self.root.after(40, self.pump)

    def schedule_search(self, *_):
        if self.search_after:
            self.root.after_cancel(self.search_after)
        self.search_after = self.root.after(160, self.search_changed)

    def search_changed(self):
        self.search_after = None
        self.page = 0
        self.view.scroll = 0
        self.refresh_list()

    def change_page(self, delta):
        self.page += delta
        self.view.scroll = 0
        self.refresh_list()

    def refresh_list(self, draw=True):
        self.names, self.filtered_count, self.page, self.pages = filtered_page(self.locations, self.query.get(), self.page)
        if self.selected not in self.names:
            self.selected = None
        if draw:
            self.view.draw()

    def selected_name(self):
        return self.selected if self.selected in self.locations else None

    def capture_named(self):
        if self.game_ready and self.store_ready:
            self.workers.submit("capture", self.view.name_entry.get().strip())

    def travel_selected(self):
        name = self.selected_name()
        if name is not None and self.game_ready:
            self.workers.submit("teleport", list(self.locations[name]))

    def manual_coordinates(self):
        self.open_coordinate_editor()

    def edit_selected(self):
        name = self.selected_name()
        if name is not None:
            self.open_coordinate_editor(name)

    def open_coordinate_editor(self, name=None):
        if self.coordinate_editor is not None and self.coordinate_editor.exists():
            self.coordinate_editor.window.lift()
            self.coordinate_editor.window.focus_set()
            return
        self.coordinate_editor = CoordinateEditor(self, name)

    def focus_saved_location(self, name):
        query = self.query.get().strip().casefold()
        matches = [item for item in self.locations if query in item.casefold()]
        if name not in matches:
            return
        index = matches.index(name)
        self.page = index // PAGE_SIZE
        self.refresh_list(draw=False)
        self.selected = name
        self.view.scroll = max(0, index % PAGE_SIZE-self.view.visible_rows+1)

    def delete_selected(self):
        name = self.selected_name()
        if name is not None and messagebox.askyesno("Remove location", f'Remove “{name}”?\nThe previous JSON will be kept as a backup.', parent=self.root):
            self.workers.submit("delete", name, disk=True)

    def import_locations(self):
        path = filedialog.askopenfilename(title="Import locations (merged; existing names are preserved)", filetypes=[("JSON records", "*.json")], parent=self.root)
        if path:
            self.workers.submit("import", path, disk=True)

    def export_locations(self):
        path = filedialog.asksaveasfilename(title="Export locations", initialfile="sekiro-locations.json", defaultextension=".json", filetypes=[("JSON records", "*.json")], parent=self.root)
        if path:
            self.workers.submit("export", path, disk=True)

    def diagnostics(self):
        if self.diagnostic_window is not None and self.diagnostic_window.winfo_exists():
            self.diagnostic_window.lift()
            return
        window = tk.Toplevel(self.root)
        window.title("Connection help")
        window.geometry("580x540")
        window.minsize(500, 440)
        window.configure(bg="#f2f0e9")
        window.transient(self.root)
        self.diagnostic_window = window
        self.diagnostic_last_text = None
        tk.Label(window, text=f"Sekiro Teleport {VERSION} — Connection help", bg="#f2f0e9",
                 fg="#292721", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=20, pady=(18, 10))
        self.diagnostic_body = tk.Text(window, wrap="word", bg="#f2f0e9", fg="#292721",
                 font=("Segoe UI", 10), relief="flat", padx=3, pady=3, height=18)
        self.diagnostic_body.pack(fill="both", expand=True, padx=18)
        actions = tk.Frame(window, bg="#f2f0e9")
        actions.pack(fill="x", padx=20, pady=15)
        tk.Button(actions, text="Save report…", command=self.save_connection_report, padx=12).pack(side="left")
        tk.Button(actions, text="Close", command=window.destroy, padx=20).pack(side="right")
        self.refresh_diagnostics()

    def refresh_diagnostics(self):
        if self.diagnostic_window is None or not self.diagnostic_window.winfo_exists():
            return
        text = diagnostic_text(self.connection_report, self.directory, self.storage_mode)
        if text != self.diagnostic_last_text:
            self.diagnostic_body.configure(state="normal")
            self.diagnostic_body.delete("1.0", "end")
            self.diagnostic_body.insert("1.0", text)
            self.diagnostic_body.configure(state="disabled")
            self.diagnostic_last_text = text

    def save_connection_report(self):
        path = filedialog.asksaveasfilename(title="Save connection report", initialdir=self.directory,
            initialfile="sekiro-connection-report.json", defaultextension=".json",
            filetypes=[("Connection report", "*.json")], parent=self.diagnostic_window)
        if path:
            report = {**self.connection_report, "storage": {"mode": self.storage_mode,
                      "folder": str(self.directory), "location_count": len(self.locations)}}
            self.workers.submit("report", path, report, disk=True)

    def close(self):
        if self.closing:
            return
        self.closing = True
        if self.coordinate_editor is not None and self.coordinate_editor.exists():
            self.coordinate_editor.close()
        self.root.withdraw()
        self.workers.shutdown()
        self.wait_close()

    def wait_close(self):
        if self.workers.finished():
            self.root.destroy()
        else:
            self.root.after(50, self.wait_close)


def main():
    parser = argparse.ArgumentParser(description="Sekiro Teleport — coordinate checkpoint tool")
    parser.add_argument("--demo", action="store_true", help="Preview with a simulated character; never attach to Sekiro")
    parser.add_argument("--data-dir", type=Path, help="Choose a data folder instead of storing beside the executable")
    args = parser.parse_args()
    demo_dir = tempfile.TemporaryDirectory(prefix="SekiroTeleportPreview-") if args.demo and args.data_dir is None else None
    directory = args.data_dir or (Path(demo_dir.name) if demo_dir else default_data_dir())
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SanguineLoki700.SekiroTeleport")
    root = tk.Tk()
    data_lock = DataFolderLock(directory)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        data_lock.acquire()
        handler = RotatingFileHandler(directory / "teleport.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(name)s %(message)s")
        app = SekiroTeleport(root, directory, args.demo)
        def report_exception(kind, value, tb):
            logging.getLogger(__name__).error("UI error", exc_info=(kind, value, tb))
            app.show_notice("An interface error occurred. See teleport.log in the data folder.", "error")
        root.report_callback_exception = report_exception
        root.mainloop()
    except Exception as exc:
        logging.getLogger(__name__).exception("Startup failed")
        messagebox.showerror("Sekiro Teleport", f"Could not start: {exc}\nTry a writable folder with --data-dir.", parent=root)
        root.destroy()
        return 1
    finally:
        logging.shutdown()
        data_lock.close()
        if demo_dir:
            demo_dir.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
