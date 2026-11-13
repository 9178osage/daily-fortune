"""A small column-aware renderer for our controlled Chinese content.

This is intentionally not a complete UAX #29 grapheme segmenter. It handles
combining marks, variation selectors, common emoji modifiers/ZWJ and flags;
no complex emoji are used in aligned report fields.
"""

import re
import unicodedata

from .content import LABELS

ANSI = re.compile(r"\x1b\[[0-9;]*m")
CLOSING_PUNCTUATION = frozenset("，。！？：；、）》】」』…,.!?;:%")
OPENING_PUNCTUATION = frozenset("（《【「『(")


# Brief readings for low, steady, and high ratings, in that order.
DOMAIN_READINGS = {
    "overall": ("变数尚多，守势为上。", "卦势未偏，循序即可。", "阵势开明，择要可进。"),
    "study": ("温旧足矣，勿贪多。", "析其一疑，而后读新。", "可攻一难，仍须求证。"),
    "career": ("先辨所求，勿轻许诺。", "理其先后，各归其位。", "宜进一事，成后复核。"),
    "wealth": ("先清旧账，支用有度。", "细核所需，再作取舍。", "盘点有余，仍须量入。"),
    "social": ("先听其意，言不必多。", "问候有度，留三分余地。", "可开一席话，勿替人作答。"),
    "love": ("心事且缓，勿凭空臆测。", "所思直言，分寸自守。", "诚言可近，莫强求回应。"),
    "vitality": ("气力宜养，勿勉强。", "劳逸各有时，行止有度。", "可择轻事活动，知止即可。"),
}

GRADE_READINGS = {
    "大吉": "法眼所照，诸路渐通。择一事而成，便是上策。",
    "中吉": "阵势稳顺，可进一程。得其势，亦须审其变。",
    "小吉": "卦中有路，徐图可进。小成亦足称吉。",
    "平": "吉凶未偏，守常自安。",
    "末吉": "阻滞未消。先整其序，再待其时。",
    "凶": "啧，卦中变数颇多。收势为上。",
}


def _extension(char):
    code = ord(char)
    return (unicodedata.category(char) in ("Mn", "Me") or
            0xFE00 <= code <= 0xFE0F or 0x1F3FB <= code <= 0x1F3FF)


def clusters(text):
    """Yield the display clusters needed by this program, never split a ZWJ."""
    current = ""
    for char in ANSI.sub("", text):
        regional = 0x1F1E6 <= ord(char) <= 0x1F1FF
        paired_flag = (regional and len(current) == 1 and
                       0x1F1E6 <= ord(current) <= 0x1F1FF)
        if current and (_extension(char) or char == "\u200d" or current.endswith("\u200d") or paired_flag):
            current += char
        else:
            if current:
                yield current
            current = char
    if current:
        yield current


def cluster_width(cluster):
    if "\ufe0f" in cluster or "\u20e3" in cluster or any(0x1F000 <= ord(c) <= 0x1FAFF for c in cluster):
        return 2
    return max((0 if _extension(c) or unicodedata.category(c) in ("Cc", "Cf")
                else 2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
                for c in cluster), default=0)


def display_width(text):
    return sum(cluster_width(c) for c in clusters(text))


def wrap(text, width, indent=""):
    """Wrap by terminal cells. Used before SGR decoration is applied."""
    width = max(2, width)
    indent_width = display_width(indent)
    if indent_width >= width - 1:
        indent, indent_width = "", 0
    lines = []
    capacity = width - indent_width
    for paragraph in text.split("\n"):
        pending = list(clusters(paragraph))
        start = 0
        while start < len(pending):
            if pending[start] == " ":
                start += 1
                continue
            end, used = start, 0
            while end < len(pending):
                columns = cluster_width(pending[end])
                if used + columns > capacity:
                    break
                used += columns
                end += 1
            end = max(start + 1, end)
            # Basic Chinese line-breaking: avoid a closing mark at line start
            # or an opening mark at line end when there is room to move text.
            while end > start + 1 and (
                (end < len(pending) and pending[end] in CLOSING_PUNCTUATION)
                or pending[end - 1] in OPENING_PUNCTUATION
            ):
                end -= 1
            lines.append((indent + "".join(pending[start:end])).rstrip())
            start = end
        if not pending:
            lines.append("")
    return lines or [""]


def render_compact(report, width=76, color=False, plain=False):
    width = min(78, width)
    rows = [report.opening]
    rows.extend(f"{label}：{value}" for label, value in report.scores)
    rows.append(f"符卡：{report.card}")
    lines = [line for row in rows for line in wrap(row, width)]
    for line in wrap(f"点评：{report.comment}", width):
        lines.append(f"\x1b[1m{line}\x1b[0m" if color and not plain else line)
    stars = f"{report.stars}/7" if plain else "★" * report.stars + "☆" * (7 - report.stars)
    lines.extend(wrap(stars, width))
    return "\n".join(lines) + "\n"


def render(report, width=76, color=False, plain=False, emoji=False):
    width = max(2, min(78, width))
    color = color and not plain
    output = []

    def add(text="", style=None, indent=""):
        for line in wrap(text, width, indent):
            output.append(("\x1b[%sm%s\x1b[0m" % (style, line)) if color and style and line else line)

    def section(title):
        add()
        add("[%s]" % title if plain else "【%s】" % title, "1;36")

    title = "穷观阵已启 · 本座断今日之卦"
    if not plain:
        title = f"🔮 {title}" if emoji else f"✦ {title} ✦"
    add(title, "1;35")
    add("-" * width if plain else "─" * width, "2")
    weekday = "一二三四五六日"[report.day.weekday()]
    add("日期：%s  星期%s" % (report.day.isoformat(), weekday))
    add(f"阵中所见：{report.theme} · {report.keyword}", "33")

    section("今日总览")
    label_width = max(display_width(LABELS[s.key]) for s in report.scores)
    for score in report.scores:
        label = LABELS[score.key]
        stars = "%d/5" % score.stars if plain else "★" * score.stars + "☆" * (5 - score.stars)
        if width >= 32:
            line = label + " " * (label_width - display_width(label) + 2) + stars
            add(line, "32" if score.stars >= 4 else "33" if score.stars <= 2 else None)
        else:
            add(label + "：" + stars)
        level = 0 if score.stars <= 2 else 1 if score.stars == 3 else 2
        add(DOMAIN_READINGS[score.key][level], indent="  ")

    section("幸运元素")
    for label, value in (("幸运数字", report.number), ("幸运颜色", report.color),
                         ("幸运方位", report.direction), ("幸运关键词", report.keyword),
                         ("幸运物品", report.object)):
        add("%s：%s" % (label, value))

    section("赛博黄历")
    add("宜", "1;32")
    for activity in report.suitable:
        add(f"- {activity.name}")
    add("不宜", "1;33")
    for activity in report.avoid:
        add(f"- {activity.name}")

    section("今日签文")
    add(f"卦断：{report.grade}", "1;35")
    add("意象：%s" % report.image)
    add(report.poem, indent="  ")
    add(f"解签：{GRADE_READINGS[report.grade]}")

    section("今日寄语")
    add(f"本座以为，宜先{report.suitable[0].name}，不宜{report.avoid[1].name}。")
    add("一饮一啄，莫非前定。然最优解仍在人为。")
    add()
    add("仅供娱乐。评分为生成值，不预测未来。", "2")
    add("赛博黄历与签文均为原创生活提示。", "2")
    return "\n".join(output) + "\n"
