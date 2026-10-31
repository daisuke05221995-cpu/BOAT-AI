"""Contract tests for the public CSV snapshot research adapter."""

from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch
import json
import unittest
from zoneinfo import ZoneInfo

from exhibition_vision.public_feed import FeedError, feed_url, main, parse_source, process_day, write_records


DAY = date(2026, 10, 29)
BEFORE = datetime(2026, 10, 29, 15, 20, tzinfo=ZoneInfo("Asia/Tokyo"))
AFTER = datetime(2026, 10, 29, 15, 40, tzinfo=ZoneInfo("Asia/Tokyo"))
COMMON = "レースコード,レース日,レース場,レース回,締切時刻,取得日時"
PREFIX = "202610292309,2026-10-29,23,09R,15:30,2026-10-29T15:17:20+09:00"


def original_csv(*, labels=("一周", "まわり足", "直線"), missing_lane=None):
    head = COMMON + ",計測数,計測項目1,計測項目2,計測項目3"
    head += "".join(f",艇{lane}_選手名,艇{lane}_値1,艇{lane}_値2,艇{lane}_値3" for lane in range(1, 7))
    row = PREFIX + f",{len(labels)},{','.join((*labels, *([''] * (3 - len(labels)))))}"
    for lane in range(1, 7):
        values = [str(36.0 + lane / 5), str(5.0 + lane / 5), str(6.8 + lane / 5)]
        if missing_lane == lane:
            values[1] = ""
        row += f",選手{lane}," + ",".join(values)
    return head + "\n" + row + "\n"


def tkz_csv():
    head = COMMON + ",状態" + "".join(
        f",艇{lane}_展示タイム,艇{lane}_チルト" for lane in range(1, 7))
    row = PREFIX + ",1" + "".join(f",6.{lane},-0.5" for lane in range(1, 7))
    return head + "\n" + row + "\n"


def stt_csv():
    head = COMMON + "".join(f",艇{lane}_コース,艇{lane}_スタート展示" for lane in range(1, 7))
    row = PREFIX + ",1,0.04,2,-0.01,3,0.11,6,0.20,4,0.05,5,0.09"
    return head + "\n" + row + "\n"


def sui_csv():
    head = COMMON + ",風速(m),波の高さ(cm)"
    return head + "\n" + PREFIX + ",2,3\n"


class PublicFeedTest(unittest.TestCase):
    def test_fixed_documented_endpoint(self):
        self.assertEqual("https://boatracecsv.github.io/data/previews/tkz/2026/10/29.csv", feed_url("tkz", DAY))
        with self.assertRaises(FeedError):
            feed_url("../../secrets", DAY)

    def test_four_source_join_without_fabricating_video_qualities(self):
        sources = {"original_exhibition": original_csv(), "tkz": tkz_csv(), "stt": stt_csv(), "sui": sui_csv()}
        result = process_day(sources, DAY, BEFORE)
        self.assertEqual(1, len(result))
        race = result[0]
        self.assertEqual("PRE_CLOSE_OBSERVED", race["status"])
        self.assertEqual([1, 2, 3, 4, 5, 6], [b["original_ranks"]["straight_time_s"] for b in race["boats"]])
        self.assertEqual(6, race["boats"][3]["course"])
        self.assertEqual(-0.01, race["boats"][1]["exhibition_st"])
        self.assertEqual(2.0, race["weather"]["wind_speed_mps"])
        self.assertEqual({"deashi": None, "yukiashi": None, "nobiashi": None,
                          "mawariashi": None, "turn_performance": None}, race["boats"][0]["traits"])
        self.assertFalse(race["forecast_input_allowed"])
        self.assertEqual("published_numeric_exhibition_not_video_ai", race["data_kind"])

    def test_reading_a_historical_snapshot_does_not_claim_live_forecast(self):
        result = process_day({"original_exhibition": original_csv()}, DAY, AFTER)
        self.assertEqual("ARCHIVE_ONLY", result[0]["status"])
        with TemporaryDirectory() as directory:
            report = write_records(result, Path(directory), live_only=True)
            self.assertEqual(0, report["saved"])

    def test_missing_original_is_explicit_not_zero(self):
        result = process_day({"tkz": tkz_csv()}, DAY, BEFORE)[0]
        self.assertIsNone(result["boats"][0]["original_ranks"]["turn_time_s"])
        self.assertIn("original_exhibition", result["sources_missing_or_late"])

    def test_two_field_original_and_missing_boat(self):
        data = original_csv(labels=("一周", "まわり足"))
        race = process_day({"original_exhibition": data}, DAY, BEFORE)[0]
        self.assertIsNone(race["boats"][0]["original_ranks"]["straight_time_s"])
        self.assertIsNotNone(race["boats"][0]["original_ranks"]["lap_time_s"])
        incomplete = process_day({"original_exhibition": original_csv(missing_lane=4)}, DAY, BEFORE)[0]
        self.assertIsNone(incomplete["boats"][0]["original_ranks"]["turn_time_s"])

    def test_half_lap_measured_as_half_lap_not_full_lap(self):
        data = original_csv(labels=("半周ラップ", "まわり足", "直線"))
        race = process_day({"original_exhibition": data}, DAY, BEFORE)[0]
        self.assertEqual(1, race["boats"][0]["original_ranks"]["half_lap_time_s"])
        self.assertIsNone(race["boats"][0]["original_ranks"]["lap_time_s"])

    def test_post_deadline_source_capture_not_usable(self):
        late = original_csv().replace("15:17:20+09:00", "15:31:20+09:00")
        race = process_day({"original_exhibition": late}, DAY, AFTER)[0]
        self.assertIn("original_exhibition", race["sources_missing_or_late"])
        self.assertEqual({}, race["boats"][0]["original"])

    def test_inconsistent_keys_rejected(self):
        wrong = original_csv().replace("202610292309", "202610292308")
        with self.assertRaises(FeedError):
            parse_source("original_exhibition", DAY, wrong)

    def test_future_snapshot_cannot_be_used(self):
        future = original_csv().replace("15:17:20+09:00", "15:24:20+09:00")
        race = process_day({"original_exhibition": future}, DAY, BEFORE)[0]
        self.assertIn("original_exhibition", race["sources_missing_or_late"])

    def test_one_changed_deadline_skips_only_affected_race(self):
        original = original_csv().strip().split("\n")
        other_race = original[1].replace("202610292309", "202610292310").replace(",09R,", ",10R,")
        combined = "\n".join([*original, other_race, ""])
        # A delayed cutoff in one source must not kill the whole job/day.
        outdated_tkz = tkz_csv().replace(",15:30,", ",15:25,")
        with redirect_stderr(StringIO()) as stderr:
            races = process_day({"original_exhibition": combined, "tkz": outdated_tkz}, DAY, BEFORE)
        self.assertEqual(["202610292310"], [race["race"]["code"] for race in races])
        self.assertIn("skipped race 202610292309", stderr.getvalue())

    def test_main_uses_end_of_fetch_time_not_start_for_live_claim(self):
        with TemporaryDirectory() as directory:
            args = ["public_feed", "--date", "2026-10-29", "--output-dir", directory, "--live-only"]
            with (patch("sys.argv", args),
                  patch("exhibition_vision.public_feed.datetime", wraps=datetime) as clock,
                  patch("exhibition_vision.public_feed.fetch_source") as fetch,
                  redirect_stdout(StringIO()) as stdout):
                clock.now.side_effect = [BEFORE, AFTER]
                fetch.side_effect = lambda source, day: original_csv() if source == "original_exhibition" else ""
                main()
            report = json.loads(stdout.getvalue())
            self.assertEqual(0, report["saved"])
            self.assertEqual(1, report["archive_only"])
            self.assertEqual([], list(Path(directory).glob("*.json")))


if __name__ == "__main__":
    unittest.main()
