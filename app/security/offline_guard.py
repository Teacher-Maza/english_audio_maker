from __future__ import annotations

import os
import socket
import threading


class OfflineNetworkError(OSError):
    pass


_LOCK = threading.Lock()
_INSTALLED = False


def _blocked(*_args, **_kwargs):
    raise OfflineNetworkError("Network access is disabled for English Audio Maker V2 – Humanization A")


def install_offline_guard() -> None:
    global _INSTALLED
    with _LOCK:
        if _INSTALLED:
            return
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        socket.create_connection = _blocked
        socket.getaddrinfo = _blocked
        socket.socket.connect = _blocked
        socket.socket.connect_ex = _blocked
        _INSTALLED = True


def is_offline_guard_installed() -> bool:
    return _INSTALLED
