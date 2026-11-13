"""Versioned, domain-separated deterministic generation. No network or hash()."""

from dataclasses import dataclass
from datetime import date
import hashlib
import json

from . import ALGORITHM_VERSION
from .content import (DOMAINS, LABELS, DOMAIN_TEXT, THEMES, ACTIONS, CAUTIONS,
                      GRADE_INFO, OPENINGS, CLOSINGS, WEEKDAY_NOTES)

DIGEST_RANGE = 1 << 256
AXIS_FOR = {
    "study": "focus", "career": "focus", "wealth": "order",
    "social": "connection", "love": "connection", "vitality": "energy",
}


def digest(*parts):
    payload = json.dumps([ALGORITHM_VERSION, *parts], ensure_ascii=False,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).digest()


class Stream:
    """SHA-256 counter stream with unbiased bounded integer sampling."""

    def __init__(self, user_id, stamp, field):
        self.parts = (user_id, stamp, field)
        self.counter = 0

    def below(self, bound):
        if not 0 < bound <= DIGEST_RANGE:
            raise ValueError("bound must be in 1..2**256")
        limit = DIGEST_RANGE - DIGEST_RANGE % bound
        while True:
            value = int.from_bytes(digest(*self.parts, self.counter), "big")
            self.counter += 1
            if value < limit:
                return value % bound

    def choose(self, items):
        return items[self.below(len(items))]


def rotation(user_id, day, field, items):
    """A shuffled calendar deck. Query order is irrelevant; no history is stored.

    For n >= 3 every n-day block is a permutation. Swapping only the first two
    entries on a boundary collision leaves each block's last entry unchanged,
    so checking the preceding *raw* permutation is sufficient.
    """
    size = len(items)
    if not size:
        raise ValueError("empty content pool")
    ordinal = day.toordinal() - 1
    if size < 3:
        offset = int.from_bytes(digest(user_id, "deck", field), "big") % size
        return items[(ordinal + offset) % size]
    cycle, position = divmod(ordinal, size)

    def rank(block, index):
        return digest(user_id, "deck", field, block, index), index

    order = sorted(range(size), key=lambda i: rank(cycle, i))
    # Only these positions can change across a block boundary.
    if position < 2:
        previous_last = max(range(size), key=lambda i: rank(cycle - 1, i))
        if order[0] == previous_last:
            position = 1 - position
    return items[order[position]]


def band(stars):
    return "low" if stars <= 2 else "mid" if stars == 3 else "high"


def grade_for(total):
    for ceiling, grade in ((9, "凶"), (13, "末吉"), (17, "平"),
                           (21, "小吉"), (25, "中吉"), (30, "大吉")):
        if total <= ceiling:
            return grade
    raise ValueError("invalid score total")


@dataclass(frozen=True)
class Score:
    key: str
    stars: int
    note: str


@dataclass(frozen=True)
class Activity:
    domain: str
    name: str
    reason: str
    band: str


@dataclass(frozen=True)
class Report:
    day: date
    scores: tuple[Score, ...]
    strongest: str
    weakest: str
    theme: str
    number: int
    color: str
    direction: str
    keyword: str
    object: str
    suitable: tuple[Activity, ...]
    avoid: tuple[Activity, ...]
    grade: str
    meaning: str
    image: str
    poem: str
    interpretation: str
    message: str
    weekday_note: str


def daily_ratings(day, user_id):
    """Return the same six domain ratings for both the short and full reports."""
    stamp = day.isoformat()

    def rng(field):
        return Stream(user_id, stamp, field)

    # Shared story rhythm creates gentle correlations; each axis and domain
    # retains its own stream. These are invented entertainment weights.
    base = rng("context.base").choose((1,) + (2,) * 4 + (3,) * 8 + (4,) * 6 + (5,))
    axes = {key: rng("context." + key).choose((-1, 0, 0, 1))
            for key in ("focus", "order", "connection", "energy")}
    values = {}
    for key in DOMAINS:
        noise = rng("score." + key).choose((-1, 0, 0, 0, 1))
        values[key] = max(1, min(5, base + axes[AXIS_FOR[key]] + noise))
    return values


def generate(day, user_id):
    stamp = day.isoformat()

    def rng(field):
        return Stream(user_id, stamp, field)

    def text(field, items):
        return rotation(user_id, day, field, items)

    values = daily_ratings(day, user_id)
    total = sum(values[key] for key in DOMAINS)
    overall = (total + 3) // 6  # half-up, entirely integer arithmetic
    highest = max(values.values())
    strongest = rng("focus.strong").choose(tuple(k for k in DOMAINS if values[k] == highest))
    rest = tuple(k for k in DOMAINS if k != strongest)
    lowest = min(values[k] for k in rest)
    weakest = rng("focus.weak").choose(tuple(k for k in rest if values[k] == lowest))
    third = rng("almanac.third").choose(tuple(k for k in rest if k != weakest))
    theme = THEMES[strongest]
    scores = [Score("overall", overall, text("overview." + band(overall), OPENINGS[band(overall)]))]
    for key in DOMAINS:
        level = band(values[key])
        scores.append(Score(key, values[key], text("note." + key + "." + level, DOMAIN_TEXT[key][level])))
    suitable, avoid = [], []
    for key in (strongest, weakest, third):
        level = band(values[key])
        action, reason = text("do." + key + "." + level, ACTIONS[key][level])
        suitable.append(Activity(key, action, reason, level))
        action, reason = text("avoid." + key, CAUTIONS[key])
        avoid.append(Activity(key, action, reason, level))
    grade = grade_for(total)
    image, poem = text("image." + strongest, theme["images"])
    # Use a distinct opening from the overview, while keeping a stable pool.
    opening_pool = OPENINGS[band(overall)]
    opening = text("message.open." + band(overall), opening_pool)
    if opening == scores[0].note:
        opening = opening_pool[(opening_pool.index(opening) + 1) % len(opening_pool)]
    strong_action, weak_caution = suitable[0], avoid[1]
    focus_word = "各项接近，今天不必分出输赢" if len(set(values.values())) == 1 else "把%s当作今天的着力点" % LABELS[strongest]
    message = "%s%s，可以%s：%s。留意%s，忌%s：%s。%s" % (
        opening, focus_word, strong_action.name, strong_action.reason,
        LABELS[weakest], weak_caution.name, weak_caution.reason,
        text("message.close", CLOSINGS))
    return Report(
        day, tuple(scores), strongest, weakest, theme["name"],
        text("lucky.number", range(1, 100)),
        text("lucky.color." + strongest, theme["colors"]),
        text("lucky.direction", ("东", "东南", "南", "西南", "西", "西北", "北", "东北")),
        text("lucky.keyword." + strongest, theme["keywords"]),
        text("lucky.object." + strongest, theme["objects"]),
        tuple(suitable), tuple(avoid), grade, GRADE_INFO[grade]["meaning"], image, poem,
        text("slip.interpretation." + grade, GRADE_INFO[grade]["messages"]),
        message, WEEKDAY_NOTES[day.weekday()],
    )
