"""Queue-based workers. No worker or keyboard hook ever touches a Tk widget."""
import ctypes
import logging
import os
import queue
import threading
import time
from datetime import datetime, timezone

from teleport_core import VERSION, GameMemory, GameUnavailable, atomic_json, position
from connection_diagnostics import classify_failure

LOG = logging.getLogger(__name__)


class DemoMemory:
    def __init__(self):
        self.pm = None
        self.pid = os.getpid()
        self.pos = [155.4, -42.8, 18.2]

    def attach(self):
        self.pm = True

    def alive(self):
        return bool(self.pm)

    def read_position(self):
        return list(self.pos)

    def teleport(self, pos):
        self.pos = list(pos)

    def close(self):
        self.pm = None


def foreground_pid():
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetForegroundWindow.restype = ctypes.c_void_p
    user.GetWindowThreadProcessId.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    pid = ctypes.c_ulong()
    user.GetWindowThreadProcessId(user.GetForegroundWindow(), ctypes.byref(pid))
    return pid.value


class Workers:
    def __init__(self, store, demo=False, memory=None):
        self.store = store
        self.memory = memory if memory is not None else (DemoMemory() if demo else GameMemory())
        self.demo = demo
        self.events = queue.Queue()
        self.game_commands = queue.Queue(maxsize=32)
        self.disk_commands = queue.Queue(maxsize=32)
        self.stop = threading.Event()
        self.game_done = threading.Event()
        self.threads = []
        self.quick = None
        self.hotkeys = []
        self.last_hook = 0.0
        self.hook_lock = threading.Lock()

    def start(self):
        for target in (self.disk_loop, self.game_loop):
            thread = threading.Thread(target=target, daemon=True)
            self.threads.append(thread)
            thread.start()

    def submit(self, kind, *args, disk=False):
        if self.stop.is_set():
            return False
        try:
            (self.disk_commands if disk else self.game_commands).put_nowait((kind, args))
            return True
        except queue.Full:
            self.events.put(("notice", "Please wait for the pending actions to finish.", "warning"))
            return False

    def emit_locations(self):
        self.events.put(("locations", dict(self.store.locations)))

    def disk_loop(self):
        try:
            warning = self.store.load()
            try:
                recovery = self.store.recover_previous_records()
                warning = " ".join(part for part in (warning, recovery) if part)
            except (OSError, ValueError, UnicodeError):
                LOG.exception("Could not recover earlier AppData records")
                warning = "Earlier AppData records could not be imported automatically. The original is unchanged; you can try Import."
            self.emit_locations()
            if warning:
                self.events.put(("notice", warning, "warning"))
        except Exception:
            LOG.exception("Cannot load location storage")
            self.events.put(("notice", "Cannot read the data folder. Open Diagnostics for details; your files were not replaced.", "error"))
        self.events.put(("storage", self.store.ready))
        while not self.stop.is_set() or not self.game_done.is_set() or not self.disk_commands.empty():
            try:
                kind, args = self.disk_commands.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                if kind == "save_coordinates":
                    request_id, old, name, pos, expected = args
                    pos = position(pos)
                    name = self.store.add(name, pos) if old is None else self.store.update(old, name, pos, expected)
                    self.emit_locations()
                    self.events.put(("coordinate_saved", request_id, name, pos))
                    self.events.put(("notice", f"Location {'saved' if old is None else 'updated'}: {name}", "ok"))
                    continue
                elif kind == "add":
                    name = self.store.add(*args)
                    self.events.put(("saved", args[0], name))
                    message = f"Location saved: {name}"
                elif kind == "rename":
                    self.store.rename(*args)
                    message = "Location renamed."
                elif kind == "delete":
                    self.store.delete(*args)
                    message = "Location removed. Previous file kept as a backup."
                elif kind == "import":
                    count, skipped = self.store.import_file(*args)
                    message = f"Imported {count:,} locations. {skipped:,} invalid entries skipped."
                elif kind in ("export", "report"):
                    destination = os.path.normcase(os.path.abspath(args[0]))
                    protected = (self.store.path, self.store.directory / "locations.previous.json",
                                 self.store.directory / ".appdata-migration.json", self.store.directory / ".teleport.lock")
                    if destination in [os.path.normcase(os.path.abspath(p)) for p in protected]:
                        raise ValueError("Choose another export path to protect the active file and its backup.")
                    atomic_json(args[0], args[1] if kind == "report" else self.store.locations)
                    message = "Connection report saved locally. Nothing was sent." if kind == "report" else "Locations exported."
                else:
                    continue
                if kind not in ("export", "report"):
                    self.emit_locations()
                self.events.put(("notice", message, "ok"))
            except (ValueError, OSError) as exc:
                LOG.exception("Location operation failed: %s", kind)
                if kind == "save_coordinates":
                    self.events.put(("coordinate_error", args[0], str(exc)))
                self.events.put(("notice", str(exc), "error"))
            except Exception:
                LOG.exception("Unexpected location operation failure")
                if kind == "save_coordinates":
                    self.events.put(("coordinate_error", args[0], "Could not save the location. Your previous record was preserved. See the log for details."))
                self.events.put(("notice", "Location operation failed. See Diagnostics for the log.", "error"))

    def install_hooks(self):
        if self.demo:
            return
        try:
            import keyboard
            for key, action in (("f5", "save"), ("f9", "load")):
                hook = keyboard.add_hotkey(key, lambda a=action: self.on_hotkey(a), trigger_on_release=True)
                self.hotkeys.append(hook)
        except Exception:
            LOG.exception("Hotkey registration failed")
            self.remove_hooks()
            self.events.put(("notice", "Global hotkeys unavailable. The on-screen buttons still work.", "warning"))

    def remove_hooks(self):
        if not self.hotkeys:
            return
        import keyboard
        for hook in self.hotkeys:
            try:
                keyboard.remove_hotkey(hook)
            except Exception:
                LOG.exception("Could not remove hotkey")
        self.hotkeys.clear()

    def on_hotkey(self, action):
        if self.stop.is_set():
            return
        # Restrict global hooks to the game. Tk handles F5/F9 locally, allowing
        # text-entry dialogs to suppress hotkeys without cross-thread Tk calls.
        if self.memory.pid is None or foreground_pid() != self.memory.pid:
            return
        with self.hook_lock:
            now = time.monotonic()
            if now - self.last_hook < 0.25:
                return
            self.last_hook = now
        self.submit(action)

    def game_loop(self):
        state = None
        next_poll = 0.0
        self.install_hooks()
        try:
            while not self.stop.is_set() or not self.game_commands.empty():
                if time.monotonic() >= next_poll:
                    try:
                        if not self.memory.alive():
                            self.quick = None
                            self.events.put(("quick", None))
                            self.memory.attach()
                        self.memory.read_position()
                        current = ("ready", "Connected and ready" if not self.demo else "Preview mode — simulated character")
                        diagnostic = {"state": "ready", "reason": "preview" if self.demo else "ready",
                                      "message": current[1], "advice": "The connection is working. Use F5 to capture a checkpoint and F9 to return to it."}
                    except Exception as exc:
                        diagnostic = classify_failure(exc)
                        current = (diagnostic["state"], diagnostic["message"])
                        if diagnostic["reason"] in ("access_denied", "open_failed"):
                            self.memory.close()
                        if current != state:
                            LOG.info("Connection: %s (%s)", current[1], diagnostic["reason"], exc_info=current[0] == "error")
                    game = self.memory.diagnostics() if hasattr(self.memory, "diagnostics") else {"pid": self.memory.pid, "preview": self.demo}
                    self.events.put(("diagnostics", {"tool_version": VERSION,
                        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                        "connection": diagnostic, "game": game}))
                    if current != state:
                        self.events.put(("connection", *current))
                        state = current
                    next_poll = time.monotonic() + 1.0
                try:
                    kind, args = self.game_commands.get(timeout=0.05)
                except queue.Empty:
                    continue
                try:
                    if kind == "reconnect":
                        self.memory.close()
                        next_poll = 0.0
                        continue
                    if not self.memory.alive():
                        raise GameUnavailable("Open Sekiro and load your character. Connection is automatic.")
                    if kind == "read_coordinates":
                        self.events.put(("coordinate_read", args[0], self.memory.read_position()))
                        continue
                    elif kind == "teleport_coordinates":
                        target = position(args[1])
                        self.memory.teleport(target)
                        self.events.put(("coordinate_teleported", args[0], target))
                        message = "Teleported to the entered coordinates."
                    elif kind == "save":
                        self.quick = self.memory.read_position()
                        self.events.put(("quick", list(self.quick)))
                        message = "Quick checkpoint captured. F9 returns to this position."
                    elif kind == "load":
                        if self.quick is None:
                            raise GameUnavailable("Create a quick checkpoint with F5 first.")
                        self.memory.teleport(self.quick)
                        message = "Returned to the quick checkpoint."
                    elif kind == "capture":
                        pos = self.memory.read_position()
                        self.disk_commands.put(("add", (args[0], pos)), timeout=1)
                        continue
                    elif kind == "teleport":
                        self.memory.teleport(args[0])
                        message = "Teleported to the selected location."
                    else:
                        continue
                    self.events.put(("notice", message, "ok"))
                except Exception as exc:
                    LOG.info("Game action failed: %s", kind, exc_info=True)
                    message = str(exc) if isinstance(exc, (GameUnavailable, ValueError)) else "Memory access failed. Wait for the character to load or use Reconnect."
                    if kind in ("read_coordinates", "teleport_coordinates"):
                        self.events.put(("coordinate_error", args[0], message))
                    self.events.put(("notice", message, "error"))
                    next_poll = 0.0
        finally:
            try:
                self.remove_hooks()
                self.memory.close()
            finally:
                self.game_done.set()

    def shutdown(self):
        self.stop.set()

    def finished(self):
        return all(not t.is_alive() for t in self.threads)
