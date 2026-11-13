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
    "凶": ("宜敛锋，不宜强行。", "啧，宜缓行，不宜争先。", "宜审局，不宜涉险。"),
    "末吉": ("宜候时，不宜催逼。", "宜省察，不宜躁进。", "宜整备，不宜冒进。"),
    "平": ("宜循序，不宜求速。", "宜守常，不宜多虑。", "宜循旧章，不宜横生枝节。"),
    "小吉": ("宜试行，不宜贪多。", "宜小进，不宜妄动。", "宜拾微功，不宜求全。"),
    "中吉": ("宜择要而行，不宜旁骛。", "宜先验其策，不宜省去复核。", "宜拓一途，不宜诸事并举。"),
    "大吉": ("宜乘势而进，不宜失慎。", "宜落一子，不宜满盘皆动。", "宜展所长，不宜轻视变数。"),
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
    opening = f"穷观阵已启，本座观得{TRIGRAMS[stars - 1]}象 {face}（仅供娱乐）"
    return CompactReport(scores, card, f"{tier}。{advice}", stars, opening)


def already_drawn(day, identity):
    face = rotation(identity, day, "compact.reminder-face", REMINDER_FACES)
    return f"此卦本座已断。哼，同日无须再问 {face}"
