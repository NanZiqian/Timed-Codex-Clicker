import unittest
from datetime import datetime

from timeparse import format_remaining, parse_clock, parse_countdown, resolve_target

NOW = datetime(2026, 10, 20, 14, 30, 0)


class CountdownTests(unittest.TestCase):
    def test_hours_and_minutes(self):
        for text in ("2h 14m", "2h14m", "2 hours 14 minutes", "2 hrs, 14 mins", "2H 14M", "2 hours and 14 minutes"):
            self.assertEqual(parse_countdown(text), 2 * 3600 + 14 * 60, text)

    def test_single_unit(self):
        self.assertEqual(parse_countdown("45m"), 45 * 60)
        self.assertEqual(parse_countdown("3h"), 3 * 3600)
        self.assertEqual(parse_countdown("30s"), 30)

    def test_colon_forms(self):
        self.assertEqual(parse_countdown("1:05"), 3600 + 5 * 60)
        self.assertEqual(parse_countdown("0:45:30"), 45 * 60 + 30)

    def test_bare_number_is_minutes(self):
        self.assertEqual(parse_countdown("90"), 90 * 60)

    def test_rejects_garbage(self):
        for text in ("", "   ", "soon", "2 days", "h", "2h x"):
            with self.assertRaises(ValueError, msg=text):
                parse_countdown(text)


class ClockTests(unittest.TestCase):
    def test_later_today(self):
        self.assertEqual(parse_clock("18:45", NOW), datetime(2026, 10, 20, 18, 45))
        self.assertEqual(parse_clock("6:45 PM", NOW), datetime(2026, 10, 20, 18, 45))
        self.assertEqual(parse_clock("6:45pm", NOW), datetime(2026, 10, 20, 18, 45))
        self.assertEqual(parse_clock("6pm", NOW), datetime(2026, 10, 20, 18, 0))

    def test_passed_time_rolls_to_tomorrow(self):
        self.assertEqual(parse_clock("09:15", NOW), datetime(2026, 10, 21, 9, 15))
        self.assertEqual(parse_clock("14:30", NOW), datetime(2026, 10, 21, 14, 30))

    def test_seconds(self):
        self.assertEqual(parse_clock("18:45:30", NOW), datetime(2026, 10, 20, 18, 45, 30))

    def test_full_date(self):
        self.assertEqual(parse_clock("2026-10-22 03:15", NOW), datetime(2026, 10, 22, 3, 15))
        self.assertEqual(parse_clock("2026-10-22 3:15 AM", NOW), datetime(2026, 10, 22, 3, 15))

    def test_past_date_rejected(self):
        with self.assertRaises(ValueError):
            parse_clock("2026-10-19 03:15", NOW)

    def test_month_name(self):
        self.assertEqual(parse_clock("Oct 22, 3:15 AM", NOW), datetime(2026, 10, 22, 3, 15))
        self.assertEqual(parse_clock("resets Oct 22 at 3:15 AM", NOW), datetime(2026, 10, 22, 3, 15))
        self.assertEqual(parse_clock("22 Oct 15:15", NOW), datetime(2026, 10, 22, 15, 15))

    def test_month_name_rolls_to_next_year(self):
        self.assertEqual(parse_clock("Jan 2 08:00", NOW), datetime(2027, 1, 2, 8, 0))

    def test_rejects_garbage(self):
        for text in ("", "noon-ish", "25:99", "13:00 PM"):
            with self.assertRaises(ValueError, msg=text):
                parse_clock(text, NOW)


class ResolveTests(unittest.TestCase):
    def test_countdown_adds_buffer(self):
        self.assertEqual(resolve_target("countdown", "1h", NOW, 60), datetime(2026, 10, 20, 15, 31))

    def test_clock_adds_buffer(self):
        self.assertEqual(resolve_target("clock", "18:45", NOW, 90), datetime(2026, 10, 20, 18, 46, 30))

    def test_zero_countdown_rejected(self):
        with self.assertRaises(ValueError):
            resolve_target("countdown", "0m", NOW)


class FormatTests(unittest.TestCase):
    def test_format(self):
        self.assertEqual(format_remaining(2 * 3600 + 14 * 60 + 5), "2h 14m 05s")
        self.assertEqual(format_remaining(125), "2m 05s")
        self.assertEqual(format_remaining(9), "9s")
        self.assertEqual(format_remaining(-3), "0s")


if __name__ == "__main__":
    unittest.main()
