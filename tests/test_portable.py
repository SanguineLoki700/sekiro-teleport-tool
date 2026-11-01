from unittest.mock import patch
from teleport_core import LocationStore, atomic_json, default_data_dir


def test_default_directory_is_beside_executable_not_launch_directory(tmp_path):
    with patch("teleport_core.application_dir", return_value=tmp_path):
        assert default_data_dir() == tmp_path


def test_existing_portable_and_appdata_records_are_merged_once(tmp_path):
    portable = tmp_path / "mod"
    old = tmp_path / "AppData" / "locations.json"
    atomic_json(portable / "locations.json", {"One": [1, 2, 3], "Same": [0, 0, 0]})
    atomic_json(old, {"One": [4, 5, 6], "Same": [0, 0, 0], "New": [7, 8, 9]})
    original = old.read_bytes()
    store = LocationStore(portable, recovery_source=old)
    store.load()
    assert "Recovered 2" in store.recover_previous_records()
    assert store.locations["One"] == [1, 2, 3]
    assert store.locations["One (AppData)"] == [4, 5, 6]
    assert store.locations["New"] == [7, 8, 9]
    assert len(store.locations) == 4
    assert old.read_bytes() == original
    assert (portable / ".appdata-migration.json").exists()
    assert store.recover_previous_records() == ""
    restarted = LocationStore(portable, recovery_source=old)
    restarted.load()
    assert restarted.recover_previous_records() == ""
    assert len(restarted.locations) == 4


def test_appdata_only_is_copied_to_portable_and_original_remains(tmp_path):
    old = tmp_path / "AppData" / "locations.json"
    atomic_json(old, {"Checkpoint": [1, 2, 3]})
    store = LocationStore(tmp_path / "mod", [old], recovery_source=old)
    store.load()
    store.recover_previous_records()
    assert store.path.exists()
    assert old.exists()
    assert list(store.locations) == ["Checkpoint"]


def test_marker_write_failure_cannot_duplicate_conflicting_records(tmp_path):
    old = tmp_path / "AppData" / "locations.json"
    atomic_json(old, {"Same name": [2, 2, 2]})
    store = LocationStore(tmp_path / "mod", recovery_source=old)
    store.load()
    store.add("Same name", [1, 1, 1])
    original = __import__("teleport_core").atomic_json
    def fail_marker(path, data):
        if path.name == ".appdata-migration.json":
            raise OSError("disk full")
        return original(path, data)
    with patch("teleport_core.atomic_json", side_effect=fail_marker):
        try:
            store.recover_previous_records()
        except OSError:
            pass
    store.recover_previous_records()
    assert len(store.locations) == 2
