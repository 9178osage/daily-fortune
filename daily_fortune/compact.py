"""A short fortune card based on the same daily domain ratings."""

from bisect import bisect_right
from dataclasses import dataclass

from .engine import Stream, daily_ratings, rotation

OPENING_FACES = ("(~▽~)", "(≧▽≦)", "(*´▽｀*)", "(｡･ω･｡)", "(ﾉ◕ヮ◕)ﾉ", "(^・ω・^)")
REMINDER_FACES = ("(｀△´)", "(¬_¬)", "(눈_눈)", "(￣^￣)", "(｀へ´)", "(；￣Д￣)")

DOMAINS = (("wealth", "财运"), ("love", "桃花运"), ("career", "事业运"))
CARDS = {
    "wealth": (
        "账本符「收支有度」", "找零符「锱铢亦有数」",
        "铜铃符「欲取先思」", "旧物符「旧藏可用」",
        "信封符「用度宜留余」", "纽扣符「守细方得长久」",
    ),
    "love": (
        "纸鹤符「一言便可寄意」", "猫爪符「相近亦留分寸」",
        "月窗符「心事且随月明」", "便签符「言简而意真」",
        "糖纸符「甜意且留三分」", "回声符「听罢方可答」",
    ),
    "career": (
        "存档符「留迹方可回溯」", "铅笔符「先谋其形」",
        "纸桥符「步稳自可渡」", "剪刀符「纷务且分而理之」",
        "路标符「先辨所往」", "钟摆符「进退皆有时」",
    ),
}
TIERS = ("凶", "末吉", "平", "小吉", "中吉", "大吉", "大吉")
# Symbolic labels for the seven compact rating levels.
TRIGRAMS = ("坎", "艮", "坤", "巽", "兑", "离", "乾")
ADVICE = {
    "凶": (
        "今势受阻，宜减项核对，不宜硬推。",
        "宜守住必要一项，不宜与满日程硬碰。",
        "宜查前因，不宜把趋势误作定数。",
    ),
    "末吉": (
        "今势转慢，宜候反馈，不宜催成。",
        "宜先理清手边诸元，不宜盲推下一步。",
        "宜留出缓冲，不宜再加重变量。",
    ),
    "平": (
        "诸元平稳，宜循序，不宜虚耗。",
        "今日宜做好一件可验收的小事，不宜无序追加。",
        "宜守住既定节奏，不宜虚造新的主线。",
    ),
    "小吉": (
        "卦势有隙，宜小试，不宜铺开。",
        "宜小幅试行，不宜一口气加码。",
        "宜积累微功，不宜追求全胜。",
    ),
    "中吉": (
        "今势偏顺，宜择要推进，不宜旁骛。",
        "宜先定主线，不宜让副项同时上阵。",
        "宜行一步并复核，不宜省掉退路。",
    ),
    "大吉": (
        "阵势舒展，宜择一事成章，不宜分心。",
        "宜顺势试行且每步可查可改，不宜一次铺开。",
        "宜收束范围，不宜贪多。",
    ),
}


@dataclass(frozen=True)
class CompactReport:
    scores: tuple[tuple[str, int], ...]
    card: str
    comment: str
    stars: int
    opening: str


def summarize(day, identity):
    """Keep each number within its corresponding twenty-point rating band."""
    ratings = daily_ratings(day, identity)
    values = {}
    for domain, _ in DOMAINS:
        roll = Stream(identity, day.isoformat(), "compact.score." + domain)
        values[domain] = (ratings[domain] - 1) * 20 + 1 + roll.below(20)

    # Compare the sum to three times each average-score boundary.
    thresholds = (75, 105, 135, 180, 225, 270)
    stars = bisect_right(thresholds, sum(values.values())) + 1
    tier = TIERS[stars - 1]
    strongest = max(values, key=values.__getitem__)
    card = rotation(identity, day, "compact.card." + strongest, CARDS[strongest])
    advice = rotation(identity, day, "compact.comment." + tier, ADVICE[tier])
    scores = tuple((label, values[domain]) for domain, label in DOMAINS)
    face = rotation(identity, day, "compact.opening-face", OPENING_FACES)
    opening = f"穷观阵推演已毕，本座取{TRIGRAMS[stars - 1]}势 {face}（仅供娱乐）"
    return CompactReport(scores, card, f"{tier}。{advice}", stars, opening)


def already_drawn(day, identity):
    face = rotation(identity, day, "compact.reminder-face", REMINDER_FACES)
    return f"同日诸元未变，前卦仍可用 {face}（不重复抽签）"
