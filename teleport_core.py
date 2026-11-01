"""Persistence and memory access; deliberately independent of Tk and hotkey hooks."""
from __future__ import annotations

import ctypes
import json
import math
import os
import re
from pathlib import Path
import shutil
import struct
import sys
import tempfile
from datetime import datetime
from connection_diagnostics import ConnectionIssue, executable_version, open_game_process

VERSION = "2.3.0"
PAGE_SIZE = 50
MAX_COORD = 1_000_000
# Original project's two known layouts. No claim of universal version support.
POINTER_PATHS = ((0x03AFB218, (0x28, 0x80)),
                 (0x03D7A1E0, (0x48, 0x28, 0x80)))


def position(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("A location needs exactly three coordinates.")
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) for v in value):
        raise ValueError("Coordinates must be numbers.")
    try:
        result = [float(v) for v in value]
    except (OverflowError, ValueError) as exc:
        raise ValueError("Invalid coordinate.") from exc
    if any(not math.isfinite(v) or abs(v) > MAX_COORD for v in result):
        raise ValueError("Coordinates are outside the supported range.")
    return result


def parse_coordinates(values):
    """Parse three edit fields; accept a decimal point or comma, never grouping."""
    if len(values) != 3:
        raise ValueError("Enter X, Y and Z.")
    numbers = []
    for axis, value in zip("XYZ", values):
        text = value.strip().replace("−", "-")
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:[.,][0-9]*)?|[.,][0-9]+)(?:[eE][+-]?[0-9]+)?", text):
            raise ValueError(f"Enter a number for {axis}, such as 12.5 or 12,5, without thousands separators.")
        number = float(text.replace(",", "."))
        if not math.isfinite(number) or abs(number) > MAX_COORD:
            raise ValueError(f"{axis} must be a finite number between {-MAX_COORD:,} and {MAX_COORD:,}.")
        numbers.append(number)
    return position(numbers)


def validate_locations(data):
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object of location names and [X, Y, Z] values.")
    valid, skipped = {}, 0
    for name, value in data.items():
        try:
            if not isinstance(name, str) or not name.strip() or len(name) > 200:
                raise ValueError("Invalid location name.")
            if any(ord(c) < 32 for c in name):
                raise ValueError("Control characters in location name.")
            valid[name] = position(value)
        except ValueError:
            skipped += 1
    return valid, skipped


def unique_name(name, locations):
    name = name.strip() or f"Location {len(locations) + 1}"
    if len(name) > 180 or any(ord(c) < 32 for c in name):
        raise ValueError("Use a name of up to 180 characters without line breaks.")
    candidate, index = name, 1
    while candidate in locations:
        candidate = f"{name} ({index})"
        index += 1
    return candidate


def application_dir():
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def default_data_dir():
    return application_dir()


def previous_data_dir():
    return Path(os.environ.get("APPDATA", Path.home() / ".config")) / "SekiroTeleportTool"


class DataFolderLock:
    """Prevent concurrent app instances from overwriting the same location file."""
    def __init__(self, directory):
        self.path = Path(directory) / ".teleport.lock"
        self.file = None

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file = self.path.open("a+b")
        try:
            file.seek(0, os.SEEK_END)
            if file.tell() == 0:
                file.write(b"\0")
                file.flush()
            file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            file.close()
            raise OSError("Another copy is already using this data folder. Close it first or choose a different --data-dir.") from exc
        self.file = file
        return self

    def close(self):
        if self.file is None:
            return
        try:
            self.file.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None


def atomic_json(path, data):
    """Write in the destination filesystem; an interrupted write leaves the original intact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as f:
            temp = Path(f.name)
            json.dump(data, f, ensure_ascii=False, allow_nan=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


class LocationStore:
    def __init__(self, directory, legacy_paths=(), recovery_source=None):
        self.directory = Path(directory)
        self.path = self.directory / "locations.json"
        self.legacy_paths = tuple(Path(p) for p in legacy_paths)
        self.locations = {}
        self.ready = False
        self.recovery_source = Path(recovery_source) if recovery_source else None
        self.loaded_source = None

    def preserve(self, source, label):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        destination = self.directory / "backups" / f"locations-{label}-{stamp}.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        return destination

    def load(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        source = self.path if self.path.exists() else next(
            (p for p in self.legacy_paths if p.is_file() and p.resolve() != self.path.resolve()), None)
        if source is None:
            self.ready = True
            return ""
        self.loaded_source = source
        try:
            raw = json.loads(source.read_text(encoding="utf-8-sig"))
            locations, skipped = validate_locations(raw)
        except (ValueError, UnicodeError):
            backup = self.preserve(source, "invalid")
            self.ready = True
            return f"Invalid JSON preserved in {backup}. Import a valid copy to recover locations."
        # Never overwrite the original legacy file, even if it contains invalid records.
        if source != self.path or skipped:
            self.preserve(source, "original")
        self.locations = locations
        if source != self.path:
            atomic_json(self.path, locations)
        self.ready = True
        if skipped:
            return f"Loaded {len(locations):,} locations; skipped {skipped:,} invalid entries. Original backed up."
        return f"Migrated {len(locations):,} locations from {source}." if source != self.path else ""

    def recover_previous_records(self):
        """One-time portable recovery from 2.0/2.1 AppData, without removing either file."""
        source = self.recovery_source
        marker = self.directory / ".appdata-migration.json"
        if source is None or marker.exists() or not source.is_file() or source.resolve() == self.path.resolve():
            return ""
        data, skipped = validate_locations(json.loads(source.read_text(encoding="utf-8-sig")))
        merged = dict(self.locations)
        added = 0
        for name, pos in data.items():
            candidate = name
            if candidate in merged and merged[candidate] != pos:
                base = name[:160] + " (AppData)"
                candidate, index = base, 1
                while candidate in merged and merged[candidate] != pos:
                    candidate = f"{base} ({index})"
                    index += 1
            if candidate not in merged:
                merged[candidate] = pos
                added += 1
        if self.loaded_source != source:
            self.preserve(source, "appdata-original")
        if added:
            self.commit(merged)
        atomic_json(marker, {"source": str(source), "added": added, "skipped": skipped})
        return f"Recovered {added} AppData locations. Both original files are preserved." if added else ""

    def commit(self, new_locations):
        if not self.ready:
            raise OSError("Location storage is unavailable. Check the data folder permissions and restart.")
        if self.path.exists():
            # Keep the previous complete file, without creating unbounded backups on every save.
            previous = self.directory / "locations.previous.json"
            temp_backup = self.directory / "locations.previous.tmp"
            shutil.copy2(self.path, temp_backup)
            os.replace(temp_backup, previous)
        atomic_json(self.path, new_locations)
        self.locations = new_locations

    def add(self, name, pos):
        name = unique_name(name, self.locations)
        self.commit({**self.locations, name: position(pos)})
        return name

    def rename(self, old, new):
        if old not in self.locations:
            raise ValueError("That location no longer exists.")
        new = new.strip()
        if new == old:
            return
        if not new:
            raise ValueError("Enter a location name.")
        unique_name(new, {})  # Validate before writing.
        if new in self.locations:
            raise ValueError("That name already exists. Choose a different name.")
        self.commit({(new if k == old else k): v for k, v in self.locations.items()})

    def update(self, old, new, pos, expected=None):
        if old not in self.locations:
            raise ValueError("That location no longer exists. Close the editor and select it again.")
        if expected is not None and self.locations[old] != position(expected):
            raise ValueError("This location changed since the editor opened. Reopen it to avoid replacing newer coordinates.")
        new = new.strip()
        if not new:
            raise ValueError("Enter a location name.")
        if new != old:
            unique_name(new, {})
            if new in self.locations:
                raise ValueError("That name already exists. Choose a different name.")
        pos = position(pos)
        updated = {(new if name == old else name): (pos if name == old else value)
                   for name, value in self.locations.items()}
        self.commit(updated)
        return new

    def delete(self, name):
        if name not in self.locations:
            raise ValueError("That location no longer exists.")
        self.commit({k: v for k, v in self.locations.items() if k != name})

    def import_file(self, path):
        data, skipped = validate_locations(json.loads(Path(path).read_text(encoding="utf-8-sig")))
        if not data:
            raise ValueError("This file has no valid locations. Nothing was changed.")
        merged = dict(self.locations)
        for name, pos in data.items():
            merged[unique_name(name, merged)] = pos
        self.commit(merged)
        return len(data), skipped


class GameUnavailable(RuntimeError):
    reason = "player_unavailable"


class GameMemory:
    """Used only by the connection worker, including all reads and writes."""
    def __init__(self, factory=None, module_lookup=None):
        self.factory = factory
        self.module_lookup = module_lookup
        self.pm = None
        self.base = None
        self.pointer_path = None
        self.pid = None
        self.metadata = {}
        self.pointer_attempts = []

    def attach(self):
        if self.factory is None:
            import pymem
            import pymem.process
            self.factory = open_game_process
            self.module_lookup = pymem.process.module_from_name
        self.close()
        self.metadata = {}
        self.pointer_attempts = []
        try:
            self.pm = self.factory()
            self.metadata["pid"] = self.pm.process_id
            module = self.module_lookup(self.pm.process_handle, "sekiro.exe")
            if module is None:
                raise ConnectionIssue("module_pending", "Sekiro's executable module is not available yet.", stage="find_module")
            self.base = module.lpBaseOfDll
            self.pid = self.pm.process_id
            path = getattr(module, "filename", None)
            self.metadata.update(executable=path, version=executable_version(path),
                                 architecture="32-bit" if getattr(self.pm, "is_WoW64", False) else "64-bit")
        except Exception as exc:
            self.close()
            self.metadata.update(getattr(exc, "details", {}))
            raise

    def alive(self):
        if self.pm is None:
            return False
        # WAIT_TIMEOUT means this process handle is still alive. Unlike a cached PID,
        # a process handle cannot accidentally attach to a reused process ID.
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.WaitForSingleObject.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
        kernel.WaitForSingleObject.restype = ctypes.c_ulong
        return kernel.WaitForSingleObject(self.pm.process_handle, 0) == 258

    @staticmethod
    def valid_pointer(addr):
        return isinstance(addr, int) and 0x10000 <= addr < 0x0000800000000000 and addr % 8 == 0

    def resolve(self, path):
        if self.pm is None or self.base is None:
            raise GameUnavailable("Open Sekiro and load your character.")
        base_offset, offsets = path
        addr = self.pm.read_longlong(self.base + base_offset)
        for off in offsets[:-1]:
            if not self.valid_pointer(addr):
                raise GameUnavailable("Character is loading or unavailable.")
            addr = self.pm.read_longlong(addr + off)
        if not self.valid_pointer(addr):
            raise GameUnavailable("Character is loading or unavailable.")
        return addr + offsets[-1]

    def read_at(self, addr):
        x, z, y = struct.unpack("<fff", self.pm.read_bytes(addr, 12))
        return position([x, y, z])

    def read_position(self):
        self.pointer_attempts = []
        paths = ([self.pointer_path] if self.pointer_path else []) + [
            p for p in POINTER_PATHS if p != self.pointer_path]
        for path in paths:
            try:
                result = self.read_at(self.resolve(path))
                self.pointer_path = path
                self.pointer_attempts.append({"layout": hex(path[0]), "result": "valid coordinate vector"})
                return result
            except (OSError, RuntimeError, ValueError, struct.error) as exc:
                self.pointer_attempts.append({"layout": hex(path[0]), "result": type(exc).__name__, "detail": str(exc)})
                continue
            except Exception as exc:
                # Pymem exposes its own exception hierarchy.
                if exc.__class__.__module__.startswith("pymem"):
                    self.pointer_attempts.append({"layout": hex(path[0]), "result": type(exc).__name__, "detail": str(exc)})
                    continue
                raise
        self.pointer_path = None
        raise GameUnavailable("Game opened, but neither known player layout is readable yet.")

    def diagnostics(self):
        return {**self.metadata, "process_open": self.pm is not None,
                "selected_layout": hex(self.pointer_path[0]) if self.pointer_path else None,
                "layout_checks": list(self.pointer_attempts)}

    def teleport(self, pos):
        pos = position(pos)
        self.read_position()  # Check a fresh, complete vector before any write.
        addr = self.resolve(self.pointer_path)
        self.read_at(addr)
        if self.resolve(self.pointer_path) != addr:
            raise GameUnavailable("Character changed during loading. Try again when in the world.")
        # Preserve the original game's X, Z, Y memory order with one 12-byte write.
        data = struct.pack("<fff", pos[0], pos[2], pos[1])
        self.pm.write_bytes(addr, data, len(data))

    def close(self):
        if self.pm is not None:
            try:
                self.pm.close_process()
            except Exception:
                pass
        self.pm = self.base = self.pointer_path = self.pid = None


def filtered_page(locations, query="", page=0):
    query = query.strip().casefold()
    names = [name for name in locations if query in name.casefold()]
    pages = max(1, (len(names) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    return names[page * PAGE_SIZE:(page + 1) * PAGE_SIZE], len(names), page, pages
