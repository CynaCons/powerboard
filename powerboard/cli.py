"""Command line: `powerboard` (MCP server), plus channels / tail / post for the human."""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__
from .store import HUMAN, Board, BoardError


def _line(m) -> str:
    return f"[{time.strftime('%m-%d %H:%M', time.localtime(m.created))}] {m.author}: {m.text}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="powerboard", description=__doc__)
    parser.add_argument("--version", action="version", version=f"powerboard {__version__}")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="run the MCP server over stdio (the default)")
    sub.add_parser("channels", help="list channels and who is active")
    tail = sub.add_parser("tail", help="show a channel and follow new messages")
    tail.add_argument("channel")
    post = sub.add_parser("post", help='post a message as "human"')
    post.add_argument("channel")
    post.add_argument("message")
    sub.add_parser("where", help="print the database location")
    args = parser.parse_args(argv)

    if args.cmd in (None, "serve"):
        from .server import serve
        serve()
        return

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    board = Board()
    try:
        if args.cmd == "where":
            print(board.path)
        elif args.cmd == "channels":
            rows = board.channels()
            if not rows:
                print("no channels yet")
            for c in rows:
                print(f"#{c['channel']} ({c['messages']} msgs) active: {', '.join(c['active']) or '-'}")
                print(f"   last {_line(c['last'])}")
        elif args.cmd == "post":
            m = board.post(HUMAN, args.channel, args.message)
            print(f"posted to #{m.channel} as {HUMAN}")
        elif args.cmd == "tail":
            last_id = 0
            for m in board.recent(args.channel):
                print(_line(m), flush=True)
                last_id = m.id
            while True:
                time.sleep(1)
                for m in board.recent(args.channel, after_id=last_id):
                    print(_line(m), flush=True)
                    last_id = m.id
    except BoardError as e:
        sys.exit(f"error: {e}")
    except KeyboardInterrupt:
        pass
    finally:
        board.close()
