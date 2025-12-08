# sekiro-teleport-tool
This repository contains the raw Python source code for the **Sekiro Teleport Manager** tool, published on Nexus Mods by **SanguineLoki700**.

Why this repository exists
I created this standalone tool using **Python** and compiled it with **PyInstaller** for user convenience. However, because the tool manipulates game memory (RAM) to function, compiled `.exe` files often trigger **False Positive** alerts in antivirus software (heuristic detection).

To ensure full transparency and safety for the community, I am providing the open source code here. You can inspect the code to verify that it only contains logic for:
1.  **GUI:** Using `customtkinter`.
2.  **Memory Editing:** Using `pymem` to read/write player coordinates.
3.  **Hotkeys:** Using `keyboard` library.

## Features
- **F5 (Quick Save):** Instantly saves your current X, Y, Z coordinates.
- **F9 (Quick Load):** Teleports you back to the saved position.
- **Location Manager:** Save specific locations (e.g., "Isshin Boss Arena", "Castle Gate") to a list.
- **Persistent Saves:** Locations are saved to a `.json` file.
- **Hotkeys & GUI:** Works with both keyboard shortcuts and clickable buttons.

## How to run from source

1.  Install [Python](https://www.python.org/).
2.  Install dependencies:
    ```bash
    pip install customtkinter pymem keyboard
    ```
3.  Run the script:
    ```bash
    python sekiro_teleport.py
    ```

## Requirements
- **Game:** Sekiro: Shadows Die Twice (Tested on Steam Version 1.06).
- **OS:** Windows 10/11.

---
*Created by SanguineLoki700.*
