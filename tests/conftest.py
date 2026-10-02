import socket

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Tests never touch the network. Any socket connection attempt fails the test."""
    def guard(*args, **kwargs):
        raise RuntimeError("network access attempted in a test")
    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
