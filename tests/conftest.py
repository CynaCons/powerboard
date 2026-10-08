import pytest

from powerboard import server
from powerboard.store import Board


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "board.db"
    monkeypatch.setenv("POWERBOARD_DB", str(path))
    monkeypatch.setattr(server, "_board", None)
    yield path
    if server._board is not None:
        server._board.close()
        server._board = None


@pytest.fixture
def board(db_path):
    b = Board(db_path)
    yield b
    b.close()
