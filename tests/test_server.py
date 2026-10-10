import asyncio
import json
import os
import subprocess
import sys
import time

from powerboard import server

POSTER = (
    "import time; from powerboard.store import Board; time.sleep(1.5); "
    "Board().post('other-agent', 'c', 'from another process')"
)


def call(name, **args):
    result = asyncio.run(server.mcp.call_tool(name, args))
    content = result[0] if isinstance(result, tuple) else result
    return content[0].text


def test_post_read_channels(db_path):
    assert "no new messages" in call("read", me="b", channel="c")
    assert call("post", me="a", channel="c", message="hi") == "posted to #c as a"
    out = call("read", me="b", channel="c")
    assert out.startswith("you are b on #c: 1 new") and "a: hi" in out
    assert "#c (1 msgs) active: a, b" in call("channels")


def test_first_read_returns_history(db_path):
    call("post", me="a", channel="c", message="earlier")
    out = call("read", me="newcomer", channel="c", wait_seconds=30)
    assert "recent history" in out and "a: earlier" in out


def test_human_name_is_reserved_and_errors_are_readable(db_path):
    assert call("post", me="human", channel="c", message="x").startswith("error:")
    assert call("post", me="bad name", channel="c", message="x").startswith("error: invalid name")


def test_read_waits_for_a_post_from_another_process(db_path):
    call("read", me="waiter", channel="c")  # start listening
    poster = subprocess.Popen([sys.executable, "-c", POSTER],
                              env={**os.environ, "POWERBOARD_DB": str(db_path)})
    start = time.monotonic()
    out = call("read", me="waiter", channel="c", wait_seconds=20)
    elapsed = time.monotonic() - start
    poster.wait(timeout=10)
    assert "other-agent: from another process" in out
    assert 1.0 < elapsed < 8


def test_wait_times_out_quietly(db_path, monkeypatch):
    monkeypatch.setattr(server, "MAX_WAIT", 1)
    call("read", me="w", channel="quiet")
    out = call("read", me="w", channel="quiet", wait_seconds=60)
    assert out == "you are w on #quiet: no new messages after waiting 1s."


def test_stdio_round_trip(db_path):
    """Start `python -m powerboard` the way an MCP client does and use it."""
    p = subprocess.Popen([sys.executable, "-m", "powerboard"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         encoding="utf-8", env={**os.environ, "POWERBOARD_DB": str(db_path)})

    def send(msg):
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()

    def recv(i):
        while True:
            msg = json.loads(p.stdout.readline())
            if msg.get("id") == i:
                return msg

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"}}})
        init = recv(1)["result"]
        assert init["serverInfo"]["name"] == "powerboard"
        assert "pick a short name" in init["instructions"].lower()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert sorted(t["name"] for t in recv(2)["result"]["tools"]) == ["channels", "post", "read"]
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "post", "arguments": {"me": "a", "channel": "c", "message": "héllo ✓"}}})
        assert recv(3)["result"]["content"][0]["text"] == "posted to #c as a"
        send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {
            "name": "read", "arguments": {"me": "b", "channel": "c"}}})
        assert "a: héllo ✓" in recv(4)["result"]["content"][0]["text"]
    finally:
        p.stdin.close()
        p.wait(timeout=10)


def test_wait_limits(monkeypatch):
    class Ctx:
        def __init__(self, name):
            self.session = type("S", (), {"client_params": type("P", (), {
                "clientInfo": type("I", (), {"name": name})()})()})()

    monkeypatch.delenv("POWERBOARD_MAX_WAIT", raising=False)
    import importlib
    fresh = importlib.reload(server)
    try:
        assert fresh.MAX_WAIT == 12 * 3600
        assert fresh._wait_limit(Ctx("claude-code")) == 12 * 3600
        assert fresh._wait_limit(Ctx("codex-mcp-client")) == 12 * 3600
        assert fresh._wait_limit(Ctx("Cursor")) == 50  # Cursor CLI cancels at 60 s
        assert fresh._wait_limit(None) == 12 * 3600
    finally:
        importlib.reload(server)
