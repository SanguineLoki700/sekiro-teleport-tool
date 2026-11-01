# Sekiro Teleport

Save positions and return to them without a loading screen. For **Sekiro: Shadows Die Twice**, by **SanguineLoki700**.

## Download

[Download the latest Windows version](https://github.com/SanguineLoki700/sekiro-teleport-tool/releases/latest)

Extract the ZIP into a writable folder, run `SekiroTeleport.exe` and load your character. No Python installation needed.

**Windows 10/11 x64. Tested on Steam 1.06.**

## Controls

- **F5** captures a quick checkpoint. **F9** returns to it.
- **Save position** adds your current position to the list.
- Select a location and click **Travel** to return to it.
- **Manual coordinates** lets you enter X/Y/Z, save a location or teleport without saving.
- **Edit** changes a saved name or position. To replace it with your current position, click **Use current player position**, then **Save changes**.
- Search, import and export are available for saved locations.

Use locations within the **same loaded area**. The tool stores coordinates; it does not load maps or restore health, enemies or progress.

## Saved locations

`locations.json`, backups and logs stay beside the executable. Keep your old `locations.json` in that folder when updating. Records from earlier AppData versions are recovered automatically without deleting the original.

Close the old version before opening a new one. Your normal Sekiro save does not need to be moved.

If the tool cannot connect, load into the game and check **Diagnostics**. You can save a connection report there when reporting a problem.

## Run from source

Use 64-bit Python 3.11+ with Tk installed:

```powershell
python -m pip install -r requirements.txt
python sekiro_teleport.py
```

`--demo` opens a preview without connecting to Sekiro. `--data-dir "path"` chooses a different folder for records.

To run the tests or build the executable:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
.\build.ps1
```

The test suite contains 80 tests. Build output is `dist/SekiroTeleport.exe`.

Unofficial fan tool. See [ASSETS.md](ASSETS.md) for artwork notes.
