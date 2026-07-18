"""Per-user single-instance coordination for the desktop application."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


ACTIVATE_MESSAGE = b"ACTIVATE\n"


def default_server_name() -> str:
    user_scope = hashlib.sha256(str(Path.home().resolve()).lower().encode("utf-8")).hexdigest()[:16]
    return f"HaizFlow-{user_scope}"


class SingleInstanceCoordinator(QObject):
    activationRequested = Signal()

    def __init__(self, server_name: str | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.server_name = server_name or default_server_name()
        self._server: QLocalServer | None = None
        self._connections: set[QLocalSocket] = set()

    def acquire(self) -> bool:
        if self._notify_existing_instance():
            return False

        server = QLocalServer(self)
        server.setSocketOptions(QLocalServer.UserAccessOption)
        if not server.listen(self.server_name):
            if self._notify_existing_instance():
                return False
            QLocalServer.removeServer(self.server_name)
            if not server.listen(self.server_name):
                raise RuntimeError(f"Unable to create the application instance lock: {server.errorString()}")
        server.newConnection.connect(self._accept_connections)
        self._server = server
        return True

    def close(self) -> None:
        for socket in tuple(self._connections):
            socket.abort()
        self._connections.clear()
        if self._server is not None:
            self._server.close()
            self._server = None
            QLocalServer.removeServer(self.server_name)

    def _notify_existing_instance(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        if not socket.waitForConnected(250):
            socket.abort()
            return False
        socket.write(ACTIVATE_MESSAGE)
        socket.flush()
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        return True

    def _accept_connections(self) -> None:
        if self._server is None:
            return
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            self._connections.add(socket)
            socket.disconnected.connect(lambda active_socket=socket: self._release_socket(active_socket))
            socket.readAll()
            self.activationRequested.emit()
            socket.disconnectFromServer()

    def _release_socket(self, socket: QLocalSocket) -> None:
        self._connections.discard(socket)
        socket.deleteLater()
