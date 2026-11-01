"""Windows attachment with required rights only, and actionable connection states."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import struct

# Query modules, read/write coordinates, and observe process exit. No termination,
# thread creation, debug privilege, suspend/resume or full-access request.
PROCESS_RIGHTS = 0x0400 | 0x0010 | 0x0020 | 0x0008 | 0x00100000


class ConnectionIssue(RuntimeError):
    def __init__(self, reason, message, **details):
        super().__init__(message)
        self.reason = reason
        self.details = details


def open_process_handle(pid):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    handle = kernel.OpenProcess(PROCESS_RIGHTS, False, pid)
    if not handle:
        error = ctypes.get_last_error()
        raise ConnectionIssue("access_denied" if error == 5 else "open_failed",
                              f"Windows could not open the game (error {error}).",
                              pid=pid, winerror=error, stage="open_process")
    return handle


def open_game_process():
    if struct.calcsize("P") != 8:
        raise ConnectionIssue("tool_architecture", "The tool needs 64-bit Python.", stage="architecture")
    import pymem
    class CoordinateProcess(pymem.Pymem):
        def __init__(self, *args, **kwargs):
            try:
                super().__init__(*args, **kwargs)
            except Exception:
                if getattr(self, "process_handle", None):
                    self.close_process()
                raise
        def open_process_from_id(self, process_id):
            self.process_id = process_id
            self.process_handle = open_process_handle(process_id)
    # The superclass finds the exact executable and invokes our narrower opener.
    return CoordinateProcess("sekiro.exe", exact_match=True)


def executable_version(path):
    """Read the executable's Windows version resource; do not execute the file."""
    if not path:
        return None
    class FixedInfo(ctypes.Structure):
        _fields_ = [(name, wintypes.DWORD) for name in (
            "signature", "structure", "file_ms", "file_ls", "product_ms", "product_ls",
            "flags_mask", "flags", "os", "type", "subtype", "date_ms", "date_ls")]
    try:
        version = ctypes.WinDLL("version", use_last_error=True)
        version.GetFileVersionInfoSizeW.argtypes = (wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD))
        version.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        version.GetFileVersionInfoW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p)
        version.GetFileVersionInfoW.restype = wintypes.BOOL
        version.VerQueryValueW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT))
        version.VerQueryValueW.restype = wintypes.BOOL
        unused = wintypes.DWORD()
        size = version.GetFileVersionInfoSizeW(str(path), ctypes.byref(unused))
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
            return None
        ptr, length = ctypes.c_void_p(), wintypes.UINT()
        if not version.VerQueryValueW(buffer, "\\", ctypes.byref(ptr), ctypes.byref(length)) or length.value < ctypes.sizeof(FixedInfo):
            return None
        info = ctypes.cast(ptr, ctypes.POINTER(FixedInfo)).contents
        if info.signature != 0xFEEF04BD:
            return None
        return ".".join(map(str, (info.file_ms >> 16, info.file_ms & 65535, info.file_ls >> 16, info.file_ls & 65535)))
    except (OSError, AttributeError):
        return None


def classify_failure(exc):
    name = type(exc).__name__
    reason = getattr(exc, "reason", None)
    details = getattr(exc, "details", {})
    if name == "ProcessNotFound":
        reason = "game_not_found"
    elif name in ("CouldNotOpenProcess", "WinAPIError") or isinstance(exc, PermissionError):
        reason = reason or "access_denied"
    elif isinstance(exc, ImportError):
        reason = "missing_dependency"
    reason = reason or "unexpected_error"
    messages = {
        "game_not_found": ("waiting", "Waiting for Sekiro to open.",
            "Open Sekiro. Connection will retry automatically. If the game is already open, include the report so its process can be checked."),
        "access_denied": ("error", "Sekiro found; Windows could not grant access.",
            "Keep the game and tool at the same permission level. If Sekiro was started as administrator, start this tool the same way. Save a report if access still fails."),
        "open_failed": ("error", "Sekiro found; the process could not be opened.",
            "The game may have closed or restarted during connection. Wait for the automatic retry; save a report if this continues."),
        "player_unavailable": ("waiting", "Sekiro opened; waiting for the character.",
            "Load a character and wait until you can move. If you are already playing, save a report: it records the detected version and both address-layout checks."),
        "module_pending": ("waiting", "Sekiro is still starting.",
            "Wait until the game has finished starting. The tool will retry automatically."),
        "tool_architecture": ("error", "This tool needs 64-bit Python.",
            "Use the Windows x64 executable, or run the source with 64-bit Python."),
        "missing_dependency": ("error", "A required component is missing.",
            "Use the packaged executable, or install requirements.txt when running the source."),
        "unexpected_error": ("error", "Connection needs investigation.",
            "Save a connection report and include what happens when you open the game. The tool will keep retrying."),
    }
    state, message, advice = messages.get(reason, messages["unexpected_error"])
    return {"state": state, "reason": reason, "message": message, "advice": advice,
            "error_type": name, "error_detail": str(exc), **details}


def diagnostic_text(report, directory, storage_mode):
    connection = report.get("connection", {})
    game = report.get("game", {})
    status = connection.get("message", "Checking the connection…")
    advice = connection.get("advice", "Please wait a moment while the game is checked.")
    version = game.get("version") or "Not available yet"
    pid = game.get("pid") or connection.get("pid") or "Not found yet"
    mode = "Beside the tool (portable)" if storage_mode == "portable" else "Selected test/custom folder"
    return (f"Connection\n{status}\n\nNext step\n{advice}\n\n"
            f"Detected game\nVersion: {version}    Process ID: {pid}\n\n"
            f"Your locations\n{mode}\n{directory}\n"
            "locations.json — named locations\nlocations.previous.json — previous copy\nteleport.log — connection and error log\n\n"
            "Your Sekiro save can stay in its usual folder. There is no need to move it.\n"
            "Save report creates a local file for troubleshooting; nothing is sent automatically.")
