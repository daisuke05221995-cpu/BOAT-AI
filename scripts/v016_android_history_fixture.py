#!/usr/bin/env python3
"""Generate deterministic Python PlayerHistory fixtures for Android parity.

The fixture is entirely synthetic. It reads no race archive, odds, results,
September data or Q4 data. Every day's snapshots are emitted before that day's
synthetic outcomes are committed, matching the production leak fence.
"""
import argparse
from pathlib import Path

from v016_r4_player_history import PlayerHistory


def f(value):
    return format(float(value), ".17g")


def snapshot_line(day, lane, player, course, cls, ex, st, changed, h, r, flags):
    fields = [
        "S", str(day), str(lane), str(player), str(course), str(cls), f(ex), f(st),
        "1" if changed else "0",
        ",".join(f(x) for x in h),
        ",".join(f(x) for x in r),
        "1" if flags[0] else "0", "1" if flags[1] else "0", "1" if flags[2] else "0",
    ]
    return "|".join(fields)


def commit_line(day, updates):
    encoded = []
    for player, course, cls, ex, st, y, flags in updates:
        encoded.append(",".join([
            str(player), str(course), str(cls), f(ex), f(st),
            str(int(y[0])), str(int(y[1])), str(int(y[2])),
            "1" if flags[0] else "0", "1" if flags[1] else "0", "1" if flags[2] else "0",
        ]))
    return "C|" + str(day) + "|" + ";".join(encoded)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    history = PlayerHistory()
    lines = []
    # Deliberately cross 30/60/90/180-day rolling-window boundaries and reuse
    # players in changing courses/classes to exercise every history key family.
    days = [1, 15, 31, 32, 65, 91, 181, 182]
    for day_index, day in enumerate(days):
        pending = []
        for lane in range(6):
            player = 7001 + lane
            course = ((lane + day_index) % 6) + 1
            cls = 1 + ((lane + 2 * day_index) % 4)
            ex = 6.64 + 0.018 * lane + 0.0025 * day_index
            st = 0.105 + 0.014 * lane + 0.0015 * day_index
            changed = ((lane + day_index) % 4 == 0)
            h, r, flags = history.snapshot(player, course, cls, ex, st, changed, day)
            lines.append(snapshot_line(day, lane, player, course, cls, ex, st, changed, h, r, flags))

            # Rotating synthetic finish order. y is cumulative top1/top2/top3.
            rank = (lane - day_index) % 6
            y = [int(rank == 0), int(rank < 2), int(rank < 3)]
            pending.append((player, course, cls, ex, st, y, flags))
        # The commit follows all six snapshots for the day.
        history.commit_day(day, pending)
        lines.append(commit_line(day, pending))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print({
        "days": len(days),
        "snapshots": len(days) * 6,
        "commits": len(days),
        "lastDay": history.state["lastDay"],
        "updateRaces": history.state["updateRaces"],
        "registeredPlayers": len(history.state["recent"]),
        "realDataRead": False,
        "septemberRead": False,
        "q4Read": False,
    })


if __name__ == "__main__":
    main()
