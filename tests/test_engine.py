from dataclasses import asdict
from datetime import date, timedelta
import hashlib
import json
import unittest

from daily_fortune import ALGORITHM_VERSION
from daily_fortune.content import DOMAINS, DOMAIN_TEXT, ACTIONS, CAUTIONS, THEMES
from daily_fortune.engine import Stream, band, digest, generate, grade_for, rotation


USER = "0123456789abcdef0123456789abcdef"
DAY = date(2026, 11, 8)


class EngineTests(unittest.TestCase):
    def test_digest_serialization_is_specified(self):
        payload = '["daily-fortune-v1","用户","2026-11-08","score.study",0]'
        self.assertEqual(digest("用户", "2026-11-08", "score.study", 0),
                         hashlib.sha256(payload.encode("utf-8")).digest())
        self.assertEqual(ALGORITHM_VERSION, "daily-fortune-v1")

    def test_version_one_golden_vectors(self):
        self.assertEqual(digest("用户", "2026-11-08", "score.study", 0).hex(),
                         "a18aa21a71de4f2748d0d461b6b5af945871dbee386037ed8b87a6a424cb329c")
        stream = Stream(USER, DAY.isoformat(), "score.study")
        self.assertEqual([stream.below(1000000) for _ in range(5)],
                         [347597, 777290, 456602, 715908, 989760])
        report = generate(DAY, USER)
        self.assertEqual([s.stars for s in report.scores], [2, 2, 1, 3, 2, 2, 2])
        self.assertEqual((report.grade, report.number, report.color, report.direction,
                          report.keyword, report.object, report.image),
                         ("末吉", 15, "砂岩色", "西", "节制", "玻璃罐", "细绳"))

    def test_reproducible_and_module_independent(self):
        before = generate(DAY, USER)
        for _ in range(100):
            Stream(USER, DAY.isoformat(), "future.module").below(100)
        self.assertEqual(before, generate(DAY, USER))
        first = Stream(USER, DAY.isoformat(), "score.study")
        other = Stream(USER, DAY.isoformat(), "score.career")
        self.assertNotEqual([first.below(10000) for _ in range(8)],
                            [other.below(10000) for _ in range(8)])

    def test_calendar_deck_has_no_adjacent_repeat_and_complete_blocks(self):
        for size in (1, 2, 3, 4, 8, 12, 99):
            pool = tuple(range(size))
            output = [rotation(USER, date.fromordinal(i + 1), "test", pool) for i in range(size * 5)]
            if size > 1:
                self.assertTrue(all(a != b for a, b in zip(output, output[1:])))
            for start in range(0, size * 5, size):
                self.assertEqual(set(output[start:start + size]), set(pool))
        # Querying dates backwards cannot alter a deck.
        days = [DAY + timedelta(days=i) for i in range(20)]
        forward = [rotation(USER, day, "test", tuple(range(8))) for day in days]
        reverse = [rotation(USER, day, "test", tuple(range(8))) for day in reversed(days)]
        self.assertEqual(forward, list(reversed(reverse)))

    def test_years_of_range_consistency_and_diversity(self):
        grades, reports, scores = set(), set(), []
        for i in range(1096):
            report = generate(DAY + timedelta(days=i), USER)
            values = {s.key: s.stars for s in report.scores}
            self.assertEqual(len(values), 7)
            self.assertTrue(all(1 <= n <= 5 for n in values.values()))
            total = sum(values[k] for k in DOMAINS)
            self.assertEqual(report.grade, grade_for(total))
            self.assertEqual(values["overall"], (total + 3) // 6)
            self.assertEqual(values[report.strongest], max(values[k] for k in DOMAINS))
            self.assertEqual(values[report.weakest], min(values[k] for k in DOMAINS))
            self.assertEqual(len(report.suitable), 3)
            self.assertEqual(len(report.avoid), 3)
            self.assertEqual(len({a.domain for a in report.suitable}), 3)
            self.assertEqual(len({a.name for a in report.suitable + report.avoid}), 6)
            for action in report.suitable:
                self.assertEqual(action.band, band(values[action.domain]))
                self.assertIn((action.name, action.reason), ACTIONS[action.domain][action.band])
            for action in report.avoid:
                self.assertIn((action.name, action.reason), CAUTIONS[action.domain])
            theme = THEMES[report.strongest]
            self.assertIn(report.color, theme["colors"])
            self.assertIn(report.keyword, theme["keywords"])
            self.assertIn(report.object, theme["objects"])
            self.assertIn((report.image, report.poem), theme["images"])
            self.assertIn(report.suitable[0].reason, report.message)
            self.assertIn(report.avoid[1].reason, report.message)
            grades.add(report.grade)
            reports.add(json.dumps(asdict(report), default=str, ensure_ascii=False, sort_keys=True))
            scores.append(values["overall"])
        self.assertEqual(grades, {"大吉", "中吉", "小吉", "平", "末吉", "凶"})
        self.assertEqual(len(reports), 1096)
        # Some repeated scalar ratings are normal; full reports still differ.
        self.assertTrue(any(a == b for a, b in zip(scores, scores[1:])))

    def test_anonymous_users_differ(self):
        self.assertNotEqual(generate(DAY, USER), generate(DAY, "f" * 32))

    def test_dates_at_supported_extremes(self):
        self.assertEqual(generate(date.min, USER).day, date.min)
        self.assertEqual(generate(date.max, USER).day, date.max)

    def test_content_coverage_and_original_structure(self):
        for key in DOMAINS:
            for level in ("low", "mid", "high"):
                self.assertGreaterEqual(len(DOMAIN_TEXT[key][level]), 4)
                self.assertGreaterEqual(len(ACTIONS[key][level]), 4)
            self.assertGreaterEqual(len(CAUTIONS[key]), 4)
            for key2 in ("keywords", "colors", "objects", "images"):
                self.assertGreaterEqual(len(THEMES[key][key2]), 4)


if __name__ == "__main__":
    unittest.main()
