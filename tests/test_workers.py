import queue
import threading
import time

from teleport_core import LocationStore
from teleport_workers import DemoMemory, Workers


def wait_event(workers, kind, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        event = workers.events.get(timeout=timeout)
        if event[0] == kind:
            return event
    raise AssertionError(f"No {kind} event")


def stop(workers):
    workers.shutdown()
    for thread in workers.threads:
        thread.join(timeout=3)
    assert workers.finished()


def test_connection_does_not_wait_for_large_or_slow_storage(tmp_path):
    release = threading.Event()
    class SlowStore(LocationStore):
        def load(self):
            release.wait(timeout=3)
            return super().load()
    workers = Workers(SlowStore(tmp_path), demo=True)
    workers.start()
    try:
        assert wait_event(workers, "connection")[1] == "ready"
    finally:
        release.set()
        stop(workers)


def test_actions_run_in_one_worker_and_shutdown_flushes_pending_saves(tmp_path):
    class CheckedMemory(DemoMemory):
        def __init__(self):
            super().__init__()
            self.thread_ids = set()
        def read_position(self):
            self.thread_ids.add(threading.get_ident())
            return super().read_position()
        def teleport(self, pos):
            self.thread_ids.add(threading.get_ident())
            return super().teleport(pos)
    memory = CheckedMemory()
    store = LocationStore(tmp_path)
    workers = Workers(store, demo=True, memory=memory)
    workers.start()
    pending = {"storage", "connection"}
    while pending:
        pending.discard(workers.events.get(timeout=3)[0])
    workers.submit("save")
    assert wait_event(workers, "quick")[1] == [155.4, -42.8, 18.2]
    workers.submit("load")
    while "Returned" not in wait_event(workers, "notice")[1]:
        pass
    for i in range(10):
        workers.submit("add", f"Record {i}", [i, 0, 0], disk=True)
    stop(workers)
    assert len(store.locations) == 10
    assert len(memory.thread_ids) == 1
    assert threading.get_ident() not in memory.thread_ids


def test_auto_reconnect_after_game_start_and_restart(tmp_path):
    class ProcessNotFound(Exception):
        pass
    class DelayedMemory(DemoMemory):
        def __init__(self):
            super().__init__()
            self.available = False
        def attach(self):
            if not self.available:
                raise ProcessNotFound()
            super().attach()
    memory = DelayedMemory()
    workers = Workers(LocationStore(tmp_path), demo=True, memory=memory)
    workers.start()
    try:
        assert wait_event(workers, "connection")[1] == "waiting"
        memory.available = True
        assert wait_event(workers, "connection")[1] == "ready"
        workers.submit("save")
        wait_event(workers, "quick")
        memory.available = False
        memory.pm = None
        assert wait_event(workers, "connection")[1] == "waiting"
        assert workers.quick is None
        memory.available = True
        assert wait_event(workers, "connection")[1] == "ready"
    finally:
        stop(workers)


def test_close_immediately_after_capture_finishes_the_save(tmp_path):
    store = LocationStore(tmp_path)
    workers = Workers(store, demo=True)
    workers.start()
    wait_event(workers, "connection")
    workers.submit("capture", "Last click")
    stop(workers)
    assert store.locations["Last click"] == [155.4, -42.8, 18.2]
