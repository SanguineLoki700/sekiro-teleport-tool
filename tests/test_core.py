import json
import math
from pathlib import Path
import struct
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from teleport_core import (GameMemory, GameUnavailable, LocationStore, POINTER_PATHS,
                           atomic_json, filtered_page, position, validate_locations)


@pytest.mark.parametrize("value", [None, [], [1, 2], [1, 2, 3, 4], [True, 2, 3],
                                   ["1", 2, 3], [float("nan"), 0, 0],
                                   [math.inf, 0, 0], [1e20, 0, 0], [10**1000, 0, 0]])
def test_rejects_invalid_coordinates(value):
    with pytest.raises(ValueError):
        position(value)


def test_origin_is_valid():
    assert position([0, 0, 0]) == [0.0, 0.0, 0.0]


def test_mixed_json_keeps_valid_entries():
    data, skipped = validate_locations({"Castle": [1, 2, 3], "bad": "text", "null": None,
                                        "wrong": [0, float("nan"), 0], "": [1, 2, 3]})
    assert data == {"Castle": [1, 2, 3]}
    assert skipped == 4


def test_large_legacy_file_migrates_without_modifying_original(tmp_path):
    legacy = tmp_path / "old" / "locations.json"
    original = {f"Location {i}": [float(i), 0, 0] for i in range(20_000)}
    atomic_json(legacy, original)
    before = legacy.read_bytes()
    store = LocationStore(tmp_path / "data", [legacy])
    assert "Migrated 20,000" in store.load()
    assert len(store.locations) == 20_000
    assert legacy.read_bytes() == before
    assert len(list((store.directory / "backups").glob("*.json"))) == 1
    page, count, current, pages = filtered_page(store.locations, page=399)
    assert len(page) == 50 and count == 20_000 and current == 399 and pages == 400
    assert page[-1] == "Location 19999"


def test_search_pagination_and_clamp():
    data = {f"Castle {i}": [0, 0, 0] for i in range(101)}
    page, count, current, pages = filtered_page(data, "CASTLE", page=999)
    assert page == ["Castle 100"] and (count, current, pages) == (101, 2, 3)
    assert filtered_page(data, "missing") == ([], 0, 0, 1)


def test_malformed_json_is_preserved(tmp_path):
    file = tmp_path / "locations.json"
    file.write_text('{"unfinished":', encoding="utf-8")
    store = LocationStore(tmp_path)
    assert "Invalid JSON preserved" in store.load()
    store.add("New", [0, 0, 0])
    assert next((tmp_path / "backups").glob("*.json")).read_text() == '{"unfinished":'
    assert json.loads(file.read_text()) == {"New": [0, 0, 0]}


def test_canonical_file_wins_over_legacy(tmp_path):
    atomic_json(tmp_path / "locations.json", {"New": [1, 2, 3]})
    atomic_json(tmp_path / "old.json", {"Old": [1, 2, 3]})
    store = LocationStore(tmp_path, [tmp_path / "old.json"])
    store.load()
    assert list(store.locations) == ["New"]


def test_rename_cannot_overwrite_existing_name(tmp_path):
    store = LocationStore(tmp_path)
    store.load()
    store.add("One", [1, 2, 3])
    store.add("Two", [4, 5, 6])
    with pytest.raises(ValueError, match="already exists"):
        store.rename("One", "Two")
    assert store.locations == {"One": [1, 2, 3], "Two": [4, 5, 6]}
    store.rename("One", "Renamed")
    assert list(store.locations) == ["Renamed", "Two"]


def test_failed_atomic_write_preserves_disk_and_memory(tmp_path):
    store = LocationStore(tmp_path)
    store.load()
    store.add("One", [1, 2, 3])
    before = store.path.read_bytes()
    with patch("teleport_core.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            store.add("Two", [4, 5, 6])
    assert store.path.read_bytes() == before
    assert list(store.locations) == ["One"]


def test_final_replace_failure_preserves_original(tmp_path):
    file = tmp_path / "locations.json"
    atomic_json(file, {"one": [0, 0, 0]})
    before = file.read_bytes()
    with patch("teleport_core.os.replace", side_effect=OSError("denied")):
        with pytest.raises(OSError):
            atomic_json(file, {"two": [1, 1, 1]})
    assert file.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_import_merges_duplicates_and_unicode(tmp_path):
    store = LocationStore(tmp_path / "data")
    store.load()
    store.add("葦名", [1, 2, 3])
    source = tmp_path / "import.json"
    atomic_json(source, {"葦名": [4, 5, 6], "invalid": None})
    assert store.import_file(source) == (1, 1)
    assert store.locations["葦名"] == [1, 2, 3]
    assert store.locations["葦名 (1)"] == [4, 5, 6]
    assert json.loads((store.directory / "locations.previous.json").read_text(encoding="utf-8")) == {"葦名": [1, 2, 3]}


def test_unreadable_file_does_not_enable_writing(tmp_path):
    atomic_json(tmp_path / "locations.json", {"one": [0, 0, 0]})
    store = LocationStore(tmp_path)
    with patch.object(Path, "read_text", side_effect=PermissionError("locked")):
        with pytest.raises(PermissionError):
            store.load()
    with pytest.raises(OSError):
        store.add("new", [0, 0, 0])


class FakeProcess:
    def __init__(self, chain=0):
        self.process_handle = 1
        self.process_id = 55
        self.base = 0x140000000
        self.ptrs = {}
        self.vectors = {}
        self.writes = []
        self.closed = False
        self.set_chain(chain, 0x50000)

    def set_chain(self, index, player, pos=(12.0, 8.0, 4.0)):
        base, offsets = POINTER_PATHS[index]
        self.ptrs[self.base + base] = player
        for i, off in enumerate(offsets[:-1]):
            self.ptrs[player + off] = player + 0x10000
            player += 0x10000
        self.address = player + offsets[-1]
        self.vectors[self.address] = struct.pack("<fff", pos[0], pos[2], pos[1])

    def read_longlong(self, address):
        return self.ptrs.get(address, 0)

    def read_bytes(self, address, length):
        return self.vectors[address]

    def write_bytes(self, address, data, length):
        self.writes.append((address, data, length))
        self.vectors[address] = data

    def close_process(self):
        self.closed = True


def memory_for(fake):
    memory = GameMemory(lambda: fake, lambda *_: SimpleNamespace(lpBaseOfDll=fake.base))
    memory.attach()
    return memory


@pytest.mark.parametrize("chain", [0, 1])
def test_both_original_pointer_layouts(chain):
    fake = FakeProcess(chain)
    memory = memory_for(fake)
    assert memory.read_position() == [12, 8, 4]
    memory.teleport([0, -2, 3])
    assert fake.writes == [(fake.address, struct.pack("<fff", 0, 3, -2), 12)]


def test_respawn_resolves_new_address_and_accepts_x_zero():
    fake = FakeProcess()
    memory = memory_for(fake)
    memory.read_position()
    old = fake.address
    fake.set_chain(0, 0x90000, (0, 2, 3))
    assert memory.read_position() == [0, 2, 3]
    memory.teleport([1, 2, 3])
    assert fake.writes[0][0] != old


def test_null_or_invalid_player_never_writes():
    fake = FakeProcess()
    memory = memory_for(fake)
    fake.ptrs.clear()
    with pytest.raises(GameUnavailable):
        memory.teleport([1, 2, 3])
    assert not fake.writes


def test_nonfinite_player_never_writes():
    fake = FakeProcess()
    fake.vectors[fake.address] = struct.pack("<fff", math.nan, 0, 0)
    memory = memory_for(fake)
    with pytest.raises(GameUnavailable):
        memory.teleport([1, 2, 3])
    assert not fake.writes


def test_character_change_during_write_check_is_rejected():
    fake = FakeProcess()
    memory = memory_for(fake)
    original = memory.resolve
    calls = 0
    def unstable(path):
        nonlocal calls
        calls += 1
        return original(path) + (16 if calls >= 3 else 0)
    memory.resolve = unstable
    with pytest.raises(GameUnavailable, match="changed"):
        memory.teleport([1, 2, 3])
    assert not fake.writes
