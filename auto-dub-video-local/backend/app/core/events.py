from collections.abc import Callable
from threading import RLock

LogListener = Callable[[str, str], None]

_log_listeners: list[LogListener] = []
_lock = RLock()


def subscribe_log(listener: LogListener) -> None:
    with _lock:
        if listener not in _log_listeners:
            _log_listeners.append(listener)


def unsubscribe_log(listener: LogListener) -> None:
    with _lock:
        if listener in _log_listeners:
            _log_listeners.remove(listener)


def emit_log(job_id: str, message: str) -> None:
    with _lock:
        listeners = list(_log_listeners)

    for listener in listeners:
        try:
            listener(job_id, message)
        except Exception:
            pass
