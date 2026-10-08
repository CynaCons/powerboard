import time

import pytest

from powerboard import store
from powerboard.store import Board, BoardError


def texts(messages):
    return [m.text for m in messages]


def test_post_and_read_between_two_agents(board):
    board.read_new("ui-review", "release")  # ui-review starts listening
    board.post("auth-refactor", "release", "login flow done")
    msgs, more = board.read_new("ui-review", "release")
    assert texts(msgs) == ["login flow done"] and msgs[0].author == "auth-refactor"
    assert not more
    assert board.read_new("ui-review", "release")[0] == []  # marked seen


def test_own_messages_are_skipped(board):
    board.read_new("a", "c")
    board.post("a", "c", "mine")
    board.post("b", "c", "theirs")
    assert texts(board.read_new("a", "c")[0]) == ["theirs"]


def test_first_read_shows_recent_history_without_own_posts(board):
    for i in range(25):
        board.post("b", "c", f"m{i}")
    board.post("a", "c", "mine")
    msgs, _ = board.read_new("a", "c")
    assert texts(msgs) == [f"m{i}" for i in range(5, 25)]  # last 20 from others
    assert board.read_new("a", "c")[0] == []


def test_read_positions_are_per_name_and_channel(board):
    board.read_new("x", "c1")
    board.read_new("y", "c1")
    board.read_new("x", "c2")
    board.post("z", "c1", "hello c1")
    board.post("z", "c2", "hello c2")
    assert texts(board.read_new("x", "c1")[0]) == ["hello c1"]
    assert texts(board.read_new("y", "c1")[0]) == ["hello c1"]
    assert texts(board.read_new("x", "c2")[0]) == ["hello c2"]


def test_names_are_normalised_and_validated(board):
    board.read_new("ui-review", "release")
    board.post("Auth-Refactor ", " Release", "x")
    msgs, _ = board.read_new("UI-Review", "release")
    assert msgs[0].author == "auth-refactor" and msgs[0].channel == "release"
    for bad in ["", "has space", "a/b", "x" * 65, "-leading"]:
        with pytest.raises(BoardError):
            board.post(bad, "c", "x")
    with pytest.raises(BoardError):
        board.post("a", "c", "   ")


def test_large_backlog_is_paged(board, monkeypatch):
    monkeypatch.setattr(store, "READ_BATCH", 3)
    board.read_new("a", "c")
    for i in range(5):
        board.post("b", "c", f"m{i}")
    msgs, more = board.read_new("a", "c")
    assert texts(msgs) == ["m0", "m1", "m2"] and more
    msgs, more = board.read_new("a", "c")
    assert texts(msgs) == ["m3", "m4"] and not more


def test_old_messages_are_deleted_on_post(board, monkeypatch):
    board.post("a", "c", "old")
    real_time = time.time
    monkeypatch.setattr(store.time, "time", lambda: real_time() + store.RETENTION_SECONDS + 60)
    board.post("a", "c", "new")
    assert texts(board.recent("c")) == ["new"]


def test_channels_overview(board):
    board.read_new("watcher", "release")
    board.post("auth-refactor", "release", "done")
    board.post("pc3-deploy", "lab", "taking pc-3")
    rows = {c["channel"]: c for c in board.channels()}
    assert rows["release"]["messages"] == 1
    assert rows["release"]["active"] == ["auth-refactor", "watcher"]
    assert rows["lab"]["last"].text == "taking pc-3"


def test_two_connections_share_the_file(db_path):
    a, b = Board(db_path), Board(db_path)
    try:
        b.read_new("b", "c")
        a.post("a", "c", "via another connection")
        assert texts(b.read_new("b", "c")[0]) == ["via another connection"]
    finally:
        a.close()
        b.close()
