"""Export only normalized, anonymous song scores from a read-only Navidrome DB."""

import json
import math
import os
from pathlib import Path
import sqlite3
import sys
import time


def aggregate(connection):
    # Normalize every listener separately before combining; never export user IDs.
    totals = {}
    users = {}
    for uid, sid, count in connection.execute(
        "SELECT user_id,item_id,play_count FROM annotation WHERE item_type='media_file' AND play_count>0"
    ):
        users.setdefault(uid, []).append((sid, math.log1p(count)))
    for songs in users.values():
        maximum = max(value for _, value in songs)
        for sid, value in songs:
            totals[sid] = totals.get(sid, 0) + value / maximum / len(users)
    return totals


def export_scores(database, output):
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=10)
    try:
        connection.execute("BEGIN")
        scores = aggregate(connection)
        listeners = connection.execute(
            "SELECT COUNT(DISTINCT user_id) FROM annotation WHERE item_type='media_file' AND play_count>0"
        ).fetchone()[0]
    finally:
        connection.close()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"created": time.time(), "scores": scores, "listeners": listeners})
    )
    os.chmod(temporary, 0o600)
    os.replace(temporary, output)


if __name__ == "__main__":
    while True:
        try:
            export_scores(
                os.getenv("NAV_DB_PATH", "/nav/navidrome.db"),
                os.getenv("COLLECTIVE_OUTPUT", "/output/collective.json"),
            )
        except Exception:
            print("Collective statistics unavailable; retrying later.", flush=True)
        if "--once" in sys.argv:
            break
        time.sleep(300)
