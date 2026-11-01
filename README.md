# Sekiro Teleport 2.3

Coordinate checkpoints for **Sekiro: Shadows Die Twice**, by **SanguineLoki700**.
The application reads and writes the running player's coordinates. It does **not** restore a game save, load maps, reset enemies, or recover quest progress.

## Run

On Windows 10/11 x64, open `SekiroTeleport.exe`, then open Sekiro and load into the world. The order does not matter: the tool retries automatically. Buttons become available when the player is readable.

- **F5:** capture a temporary checkpoint.
- **F9:** return to that checkpoint.
- **Save position:** save a named location (or use an automatic name).
- Search, scroll or use the arrows to browse records. Select one, then **Travel**.
- **Manual coordinates…** opens X/Y/Z fields without needing a saved record. Enter decimal values (point or comma), then **Save location** to store them or **Teleport** to travel without saving.
- **Edit** opens the selected record's name and exact coordinates. **Use current player position** fills X/Y/Z from the game; **Save changes** replaces that record, preserving its name unless you edit it.
- **Remove**, **Import**, **Export** manage named records.
- **Reconnect** refreshes the process handle. **Diagnostics** explains storage, logs and connection failures.

Global F5/F9 operate only while Sekiro is in the foreground. Local F5/F9 also work in the tool, except while typing in text boxes or dialogs. Buttons remain usable if hotkey registration fails. The menu supports Tab/Enter for actions, Up/Down for record selection, and Page Up/Page Down for pages. Press Escape in an input to return to the menu; Escape in the menu clears the destination selection.

**Travel within the same loaded area.** These records contain coordinates, not map IDs. Avoid restoring a location from another map, character or playthrough. A quick checkpoint is cleared when the process disconnects or is reattached. Named records persist.

Manual records can be prepared while the game is closed. Reading the player or teleporting requires a ready connection. Saving and teleporting are separate actions: teleporting never changes a record implicitly. All X/Y/Z fields are required; NaN, infinity and values outside the supported range are rejected. Numerical validity cannot guarantee the target is on safe ground.

The editor remains open after saving. Further saves update the same record instead of creating duplicates. Renaming and updating coordinates commit together, with the previous JSON kept as a backup. If the record was deleted or its coordinates changed after the editor opened, the save is rejected so newer data is not silently replaced. Close the editor and select the record again in that case.

## Existing locations

By default, records, logs and backups are stored **beside the executable** (beside the script when running source). The current working directory does not change this portable default. The main file is `locations.json`; `--data-dir` still allows a custom folder. Keep the tool in a writable folder. No AppData storage is required.

The first portable launch recovers records previously stored by versions 2.0/2.1 in `%APPDATA%\SekiroTeleportTool\locations.json`. That original file stays untouched and is backed up. If a portable file already exists, equal records are deduplicated; different positions with the same name are retained under an ` (AppData)` suffix. `.appdata-migration.json` marks the completed recovery so it does not repeat. Other copies can be merged with Import. Close older versions before opening this version.

The old file is left untouched and copied into `backups/` before migration. A JSON with invalid entries keeps its valid records and preserves the original. A malformed JSON is preserved for recovery. Write/read failures are reported rather than silently discarding data.

Saves use a temporary file and replacement in the same folder; `locations.previous.json` retains the previous complete file. Data in memory changes only after saving succeeds. Imports merge names without overwriting collisions. Renaming to an existing name is rejected. Removing a record asks for confirmation.

Your Sekiro save can remain in its usual folder. This utility uses the running character's position, so it does not require the save to be moved or selected. The game's `.sl2` files are not modified by the tool.

## Connection and compatibility

The two pointer layouts from the original project are retained, with fresh pointer resolution for each operation. Both were read successfully in the owner's running **Steam 1.06 / executable 1.6.0.0**, and a 0.2-unit horizontal teleport and return were verified by memory readback. This is not a guarantee for other builds or mods.

If the player is unavailable, load into the world and wait. After death/loading the tool tries the layouts again. If access is denied, run the tool and game at the same permission level. It does not request administrator privileges automatically. Persistent failures include instructions and a rotating `teleport.log` in the data folder.

Diagnostics now provides a specific next step for each connection stage: game not found, Windows access denied, process restart/open failure, game still starting, player-layout unreadable, missing dependency or unexpected error. **Save report** writes a local JSON report with the detected executable version, process ID, Windows error when available and address-layout checks. It includes no save-file contents or memory dump, and is not sent anywhere automatically.

The game is opened with query, memory-read, memory-write, VM-operation and synchronization rights only. The tool no longer requests `PROCESS_ALL_ACCESS` or enables `SeDebugPrivilege`. This follows [Microsoft's recommendation to request required rights](https://learn.microsoft.com/en-us/windows/win32/procthread/process-security-and-access-rights). It can reduce unnecessary access failures; it cannot override Windows access restrictions or establish the cause of an unobserved user's connection failure.

The tool checks null pointers, validates all three coordinates, allows legitimate zero coordinates, rejects non-finite/out-of-range values and writes the X/Z/Y memory vector in one 12-byte operation. This reduces stale/invalid writes; it cannot make an external memory write atomic with the game's loading thread.

## Changes in 2.3

- Manual X/Y/Z entry, with decimal point/comma support, named save and teleport without saving.
- Edit a saved record's name and coordinates in one operation, or fill them from the current player position and save over that record.
- A compact Manual coordinates action and Edit in place of Rename; main window size/artwork retained.
- Correlated worker results report save/read/teleport errors inside the editor; no memory or file I/O is done in its UI callbacks.
- Pending edits disable repeated submissions. Queue rejection returns control to the editor, closed dialogs ignore late responses, and stale-coordinate edits cannot silently replace newer records.

## Changes retained from 2.2

- Restored the same button artwork from 2.1. Only its transparency extraction changed: the paper is estimated per column to avoid visible crop rectangles while retaining the source RGB and geometry. No replacement brush is used.
- Portable storage beside the executable, plus non-destructive one-time recovery of AppData records.
- Connection opens the game with required rights rather than full access/debug privilege; verified reading and a same-position write on the owner's running game.
- Friendly live connection help and a local report export, with distinct connection-failure stages.
- Added regression tests for original-art alpha borders, portable migration/collisions, required process rights and connection-stage classification.

## Changes retained from 2.1

- Compact, resizable 600×700 single-column layout (minimum 520×600). The game's screenshot supplies the visual style rather than the original inventory layout.
- Action buttons are neutral at rest. Orange feedback follows the pointer or explicit keyboard navigation and clears when the pointer leaves or focus is lost. Mouse clicks no longer leave a latched keyboard highlight.
- A selected destination uses a separate dark row with a small arrow. Clicking empty menu space or pressing Escape clears it.
- An OS file lock prevents two instances from saving to the same data folder at once. A second instance is refused before reading/writing location records. The OS releases the lock if the process exits unexpectedly; the lock file may remain and does not require manual deletion.
- Added regression tests for hover/leave/click/focus transitions and data-folder locking.

## Changes retained from 2.0

- Connection and storage run in independent workers; neither calls Tk widgets.
- Live connection monitoring, automatic retry and process-handle cleanup.
- Search and pages of 50 records, with only the visible rows rendered. No widget per saved location.
- Atomic persistence, backups, validated JSON, safe import/export and collision handling.
- Serialized memory actions; keyboard hooks enqueue commands and are removed on exit.
- Shutdown drains pending capture and disk operations.
- Weathered paper, ornamental frame and ink brushes, reconstructed from the owner's supplied screenshot. SEKIRO / TELEPORT logo and the repository's original red-kanji icon. See [ASSETS.md](ASSETS.md).

## Source setup

Use **64-bit Python 3.11+** with Tk installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python sekiro_teleport.py
```

Preview without attaching to Sekiro or reading real records:

```powershell
python sekiro_teleport.py --demo
```

Override the data folder for testing or a portable setup:

```powershell
python sekiro_teleport.py --data-dir "D:\My Sekiro Records"
```

The app blocks a second copy using the same data folder. Separate data folders can be opened simultaneously. `--demo` defaults to an isolated temporary folder; `--demo --data-dir ...` uses the explicitly selected folder.

## Test and build

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
.\build.ps1
```

Build output: `dist/SekiroTeleport.exe`. PyInstaller bundles Python and the required dependencies; users do not need Python installed. The original `sekiro.ico` is used for both the executable and window.

Tests cover 20,000-record migration, search/page boundaries, corrupt/invalid JSON, preservation on write failures, import/name collisions, both pointer layouts, zero coordinates, null/invalid pointers, respawn, character changes during write checks, automatic reconnect, worker isolation, shutdown persistence, transient button states and data-folder locking. Live evidence is documented in `VALIDATION.md`. Compatibility with future game updates or every mod is not guaranteed.
