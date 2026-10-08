import os
import subprocess
import sys


def run(db_path, *args):
    return subprocess.run([sys.executable, "-m", "powerboard", *args], capture_output=True,
                          text=True, encoding="utf-8", timeout=30,
                          env={**os.environ, "POWERBOARD_DB": str(db_path)})


def test_human_post_and_channels(db_path):
    assert run(db_path, "post", "release", "ship it").stdout.strip() == "posted to #release as human"
    out = run(db_path, "channels").stdout
    assert "#release (1 msgs) active: human" in out and "human: ship it" in out
    assert run(db_path, "where").stdout.strip() == str(db_path)
    bad = run(db_path, "post", "bad channel", "x")
    assert bad.returncode != 0 and "invalid channel" in bad.stderr
