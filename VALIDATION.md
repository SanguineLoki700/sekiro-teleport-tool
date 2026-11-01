# Validation — version 2.3.0

Validated on Windows x64 with Python 3.13.11 on 2026-11-01.

## Automated checks

**80 regression tests passed.** Coverage includes:

- Migration and pagination with 20,000 saved locations.
- Corrupt JSON, invalid records, import collisions and write failures without losing the original file.
- Portable storage, AppData recovery, duplicate-name handling and concurrent data-folder locking.
- Both original pointer layouts, legitimate zero coordinates, null pointers, invalid vectors, respawn address changes and checks before writing.
- Connection retries, required process rights and distinct connection failure states.
- Worker isolation, queue rejection and shutdown persistence.
- Button hover, keyboard focus, focus loss and preservation of the original brush artwork with transparent borders.
- Manual coordinate parsing, updates, combined rename/coordinate changes, backups, deleted/stale records and teleporting without saving.

Run the suite with `python -m pytest -q` after installing `requirements-dev.txt`.

## Live game checks

The memory backend was checked against the owner's running Steam 1.06 game (executable version 1.6.0.0, 64-bit):

- Both pointer layouts resolved to the same player position.
- A 0.2-unit horizontal displacement was written and verified by readback, then the original position was restored. Height was unchanged.
- With 20,000 synthetic saved records, storage was ready in 0.060 seconds and the live connection in 0.197 seconds in one test run. These are measurements on that machine, not performance guarantees.
- The worker captured and returned to a quick checkpoint while that large file was loaded.
- The required-rights opener (`0x100438`, without all-access/debug privileges) read the player, detected the executable version and successfully wrote the same stationary position without displacement.
- The standalone executable connected and its local F5/F9 actions worked with the live game.

## Interface and manual coordinates

The compact interface and original red-kanji icon were visually checked. In the standalone preview:

- Button feedback returned to neutral after the pointer left. Destination selection remained separate from action feedback.
- Entered `12,5`, `-3.25` and `0` manually and saved a new location.
- Filled the fields from the simulated player and saved changes to the same location; the list count stayed at one.
- The editor's fields, status and action buttons fit inside its window.

Arbitrary manual coordinates were tested with simulated memory, not written to the owner's live character. The game memory backend is unchanged by the 2.3 editor.

## Limits of this validation

- Other executable versions and mods were not tested.
- Live death/respawn or closing/reopening the owner's game were not forced; pointer relocation and reconnect scenarios use regression tests.
- Records do not contain map IDs. Cross-map travel is not supported or validated.
- The cause of a connection failure on another user's computer cannot be confirmed without evidence from that machine. The local connection report captures the detected version and failing connection stage for troubleshooting.
- The artwork is reconstructed from supplied references, not extracted game assets or a pixel-identical reproduction.
