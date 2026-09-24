#!/usr/bin/env python3
"""Convert frozen r4 history_state.json to the Android compact binary format.

The source is the already-opened r4 history state artifact. This converter does
not fetch or read September/Q4 races, odds, payouts, or outcomes beyond what is
already represented in the frozen state. Double statistics are preserved exactly;
recent cumulative counts are losslessly represented as day deltas + 3 finish bits.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

MAGIC = b"BAH1"
VERSION = 1


def uvarint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative unsigned varint")
    out = bytearray()
    while value & ~0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return uvarint(len(raw)) + raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_bytes = args.input.read_bytes()
    state = json.loads(source_bytes)
    if set(state) != {"stats", "recent", "lastDay", "updateRaces"}:
        raise ValueError("Unexpected PlayerHistory state schema")

    out = bytearray()
    out += MAGIC
    out += struct.pack(">i", VERSION)
    out += struct.pack(">i", int(state["lastDay"]))
    out += struct.pack(">i", int(state["updateRaces"]))

    stats = state["stats"]
    out += struct.pack(">i", len(stats))
    for key in sorted(stats):
        values = stats[key]
        if len(values) != 8:
            raise ValueError(f"stats[{key}] width != 8")
        out += string(key)
        for value in values:
            out += struct.pack(">d", float(value))

    recent = state["recent"]
    out += struct.pack(">i", len(recent))
    appearances = 0
    for player in sorted(recent):
        record = recent[player]
        days = record["days"]
        cumulative = record["cumulative"]
        if len(cumulative) != len(days) + 1:
            raise ValueError(f"recent[{player}] cumulative length mismatch")
        if cumulative[0] != [0, 0, 0]:
            raise ValueError(f"recent[{player}] non-zero cumulative origin")
        appearances += len(days)
        out += string(player)
        out += uvarint(len(days))
        previous_day = 0
        previous = [0, 0, 0]
        for index, day in enumerate(days):
            day = int(day)
            if day < previous_day:
                raise ValueError(f"recent[{player}] days not sorted")
            out += uvarint(day - previous_day)
            previous_day = day
            current = [int(x) for x in cumulative[index + 1]]
            delta = [current[i] - previous[i] for i in range(3)]
            if not all(x in (0, 1) for x in delta) or not (delta[0] <= delta[1] <= delta[2]):
                raise ValueError(f"recent[{player}] invalid finish delta {delta}")
            out.append(delta[0] | (delta[1] << 1) | (delta[2] << 2))
            previous = current

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(out)
    summary = {
        "format": "BAH1",
        "version": VERSION,
        "sourceBytes": len(source_bytes),
        "binaryBytes": len(out),
        "compressionRatio": len(out) / len(source_bytes),
        "sha256": hashlib.sha256(out).hexdigest(),
        "lastDay": int(state["lastDay"]),
        "updateRaces": int(state["updateRaces"]),
        "stats": len(stats),
        "players": len(recent),
        "appearances": appearances,
        "septemberRead": False,
        "q4Read": False,
    }
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
