#!/usr/bin/env python3
"""Synthetic Python r4 player-history snapshots; no race or holdout files."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from v016_r4_player_history import PlayerHistory  # noqa: E402


def main():
    history = PlayerHistory()
    events = []

    def take(day, player, course, racer_class, exhibition, start, changed):
        args = {
            "day": day,
            "player": player,
            "course": course,
            "racerClass": racer_class,
            "exhibitionTime": exhibition,
            "previewStartTiming": start,
            "courseChanged": changed,
        }
        h, reaction, flags = history.snapshot(player, course, racer_class, exhibition, start, changed, day)
        expected = {
            "history": [float(v) for v in h],
            "reaction": [float(v) for v in reaction],
            "flags": {
                "fastExhibition": flags[0],
                "goodPreviewStart": flags[1],
                "courseChanged": flags[2],
            },
        }
        events.append({"type": "snapshot", "args": args, "expected": expected})
        return flags

    def day_updates(day, race_index, races):
        updates = []
        for race in range(races):
            for lane in range(6):
                player = 1000 + ((lane + race * 4 + race_index * 2) % 15)
                course = (lane + race_index + race) % 6 + 1
                racer_class = (lane + race_index) % 5
                exhibition = round(6.58 + (lane + race_index) * 0.023 + race * 0.016, 3)
                start = round(-0.03 + lane * 0.025 + race_index * 0.003, 3)
                changed = course != lane + 1
                flags = take(day, player, course, racer_class, exhibition, start, changed)
                updates.append({
                    "player": player,
                    "course": course,
                    "racerClass": racer_class,
                    "exhibitionTime": exhibition,
                    "previewStartTiming": start,
                    "win": lane == 0,
                    "top2": lane < 2,
                    "top3": lane < 3,
                    "flags": {
                        "fastExhibition": flags[0],
                        "goodPreviewStart": flags[1],
                        "courseChanged": flags[2],
                    },
                })
        python_updates = [(u["player"], u["course"], u["racerClass"],
                           u["exhibitionTime"], u["previewStartTiming"],
                           [int(u["win"]), int(u["top2"]), int(u["top3"])],
                           (u["flags"]["fastExhibition"],
                            u["flags"]["goodPreviewStart"],
                            u["flags"]["courseChanged"])) for u in updates]
        history.commit_day(day, python_updates)
        events.append({"type": "commit", "day": day, "updates": updates})

    for index, (day, race_count) in enumerate([(10000, 1), (10010, 2), (10031, 1), (10061, 1), (10191, 1)]):
        day_updates(day, index, race_count)

    take(10192, 1000, 1, 1, 6.7, 0.16, False)
    take(10192, 11111, 6, 0, 6.8, 0.17, True)  # unseen player / sparse prior

    payload = {
        "schema_version": 1,
        "source": "scripts/v016_r4_player_history.py (synthetic and holdout-free)",
        "events": events,
        "expected_state": {
            "lastDay": history.state["lastDay"],
            "updateRaces": history.state["updateRaces"],
            "registeredPlayers": len(history.state["recent"]),
        },
    }
    path = ROOT / "cloud" / "forecast-worker" / "test" / "fixtures" / "python-model-a-history.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(events)} events to {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
