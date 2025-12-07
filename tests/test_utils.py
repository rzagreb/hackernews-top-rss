import unittest

import context  # noqa: F401

from src.utils import parse_human_date


class TestParseHumanDate(unittest.TestCase):
    def test_parse_human_date_valid_strings(self):
        for value in [
            "2024-01-10 12:34",
            "10 Jan 2024",
            "3 hours ago",
            "yesterday 14:00",
        ]:
            dt = parse_human_date(value)
            assert dt is not None, f"Expected non None for {value!r}"

    def test_parse_human_date_invalid_strings(self):
        for value in ["", None, "not a date at all"]:
            dt = parse_human_date(value)  # type: ignore[arg-type]
            assert dt is None
