import json
import math
from unittest.mock import patch

import pytest

from teleport_core import LocationStore, parse_coordinates
from teleport_workers import DemoMemory, Workers


@pytest.mark.parametrize("values,expected", [
    (["12.5", "-4.25", "0"], [12.5, -4.25, 0]),
    (["12,5", "−4,25", " 0 "], [12.5, -4.25, 0]),
    ([".5", "-,25", "1e2"], [.5, -.25, 100]),
])
def test_manual_coordinate_formats(values, expected):
    assert parse_coordinates(values) == expected


@pytest.mark.parametrize("values", [
    ["", "1", "2"], ["NaN", "1", "2"], ["inf", "1", "2"],
    ["1e999", "1", "2"], ["1000001", "1", "2"], ["1,234.5", "1", "2"],
    ["1_000", "1", "2"], ["one", "1", "2"], ["1", "2"],
])
def test_invalid_manual_coordinates_are_rejected(values):
    with pytest.raises(ValueError):
        parse_coordinates(values)


def make_store(tmp_path):
    store = LocationStore(tmp_path)
    store.load()
    store.add("First", [1, 2, 3])
    store.add("Second", [4, 5, 6])
    return store


def test_update_replaces_only_selected_record_and_keeps_previous_file(tmp_path):
    store = make_store(tmp_path)
    store.update("First", "First", [0, -2, 3.5], expected=[1, 2, 3])
    assert list(store.locations) == ["First", "Second"]
    assert store.locations == {"First": [0, -2, 3.5], "Second": [4, 5, 6]}
    assert json.loads((tmp_path / "locations.previous.json").read_text())["First"] == [1, 2, 3]


def test_rename_and_position_update_commit_together(tmp_path):
    store = make_store(tmp_path)
    store.update("First", "Renamed", [7, 8, 9], expected=[1, 2, 3])
    assert list(store.locations) == ["Renamed", "Second"]
    assert store.locations["Renamed"] == [7, 8, 9]
    restored = LocationStore(tmp_path)
    restored.load()
    assert restored.locations == store.locations


@pytest.mark.parametrize("name,pos,expected", [
    ("Second", [7, 8, 9], [1, 2, 3]),
    ("", [7, 8, 9], [1, 2, 3]),
    ("First", [math.nan, 8, 9], [1, 2, 3]),
    ("First", [7, 8, 9], [9, 9, 9]),
])
def test_failed_edit_does_not_change_any_records_or_file(tmp_path, name, pos, expected):
    store = make_store(tmp_path)
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.update("First", name, pos, expected)
    assert store.path.read_bytes() == before
    assert store.locations["First"] == [1, 2, 3]
    assert store.locations["Second"] == [4, 5, 6]


def test_deleted_record_is_not_recreated_by_old_editor(tmp_path):
    store = make_store(tmp_path)
    store.delete("First")
    with pytest.raises(ValueError, match="no longer exists"):
        store.update("First", "First", [0, 0, 0], [1, 2, 3])
    assert "First" not in store.locations


def test_write_failure_preserves_original_name_and_coordinates(tmp_path):
    store = make_store(tmp_path)
    before = store.path.read_bytes()
    with patch("teleport_core.atomic_json", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            store.update("First", "Renamed", [7, 8, 9], [1, 2, 3])
    assert store.path.read_bytes() == before
    assert store.locations == {"First": [1, 2, 3], "Second": [4, 5, 6]}


def next_event(workers, kind, request=None):
    for _ in range(100):
        event = workers.events.get(timeout=4)
        if event[0] == kind and (request is None or event[1] == request):
            return event
    raise AssertionError(f"Missing {kind} for {request}")


def shutdown(workers):
    workers.shutdown()
    for thread in workers.threads:
        thread.join(timeout=4)
    assert workers.finished()


def test_manual_save_read_update_and_teleport_through_workers(tmp_path):
    store = LocationStore(tmp_path)
    memory = DemoMemory()
    workers = Workers(store, demo=True, memory=memory)
    workers.start()
    try:
        needed = {"storage", "connection"}
        while needed:
            needed.discard(workers.events.get(timeout=4)[0])
        assert workers.submit("save_coordinates", "save-1", None, "Manual", [1, 2, 3], None, disk=True)
        assert next_event(workers, "coordinate_saved", "save-1")[2:] == ("Manual", [1, 2, 3])
        workers.submit("read_coordinates", "read-1")
        current = next_event(workers, "coordinate_read", "read-1")[2]
        assert current == [155.4, -42.8, 18.2]
        workers.submit("save_coordinates", "save-2", "Manual", "Manual", current, [1, 2, 3], disk=True)
        next_event(workers, "coordinate_saved", "save-2")
        before = store.path.read_bytes()
        workers.submit("teleport_coordinates", "teleport-1", [0, 0, 0])
        assert next_event(workers, "coordinate_teleported", "teleport-1")[2] == [0, 0, 0]
        assert memory.pos == [0, 0, 0]
        assert store.path.read_bytes() == before  # A manual teleport never saves implicitly.
        assert len(store.locations) == 1
        assert store.locations["Manual"] == current
        workers.submit("save_coordinates", "stale", "Manual", "Manual", [9, 9, 9], [1, 2, 3], disk=True)
        assert "changed" in next_event(workers, "coordinate_error", "stale")[2]
    finally:
        shutdown(workers)


def test_invalid_manual_teleport_never_reaches_memory(tmp_path):
    class CheckedMemory(DemoMemory):
        def teleport(self, pos):
            raise AssertionError("Invalid coordinates reached memory")
    workers = Workers(LocationStore(tmp_path), demo=True, memory=CheckedMemory())
    workers.start()
    try:
        next_event(workers, "connection")
        workers.submit("teleport_coordinates", "bad", [math.inf, 0, 0])
        event = next_event(workers, "coordinate_error", "bad")
        assert "supported range" in event[2]
    finally:
        shutdown(workers)


def test_queue_rejection_can_be_detected_by_editor(tmp_path):
    workers = Workers(LocationStore(tmp_path), demo=True)
    for _ in range(32):
        assert workers.submit("read_coordinates", "pending")
    assert workers.submit("read_coordinates", "overflow") is False
    workers.shutdown()
    assert workers.submit("read_coordinates", "closed") is False
