import pytest
from teleport_core import DataFolderLock


def test_second_instance_is_blocked_until_first_releases(tmp_path):
    first = DataFolderLock(tmp_path).acquire()
    second = DataFolderLock(tmp_path)
    try:
        with pytest.raises(OSError, match="Another copy"):
            second.acquire()
        assert second.file is None
    finally:
        first.close()
    second.acquire()
    second.close()
    second.close()  # Cleanup is idempotent.


def test_separate_data_folders_can_be_used_simultaneously(tmp_path):
    first = DataFolderLock(tmp_path / "one").acquire()
    second = DataFolderLock(tmp_path / "two").acquire()
    first.close()
    second.close()
