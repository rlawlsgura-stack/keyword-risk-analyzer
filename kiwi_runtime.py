"""Share the memory-heavy Kiwi model across API analysis helpers."""
from functools import lru_cache
from threading import Lock


_initialization_lock = Lock()
tokenization_lock = Lock()


@lru_cache(maxsize=1)
def _create_kiwi():
    from kiwipiepy import Kiwi

    return Kiwi(num_workers=1)


def get_kiwi():
    with _initialization_lock:
        return _create_kiwi()
