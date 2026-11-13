"""Small optional activities after a fortune in an interactive terminal."""

import secrets

from .engine import generate, rotation
from .render import render, wrap

TASKS = (
    "找一件两分钟内能收好的东西，把它放回原位。",
    "写下明天最想先做的一件事，再写下它的第一步。",
    "挑一首喜欢的歌，把手里的事放下，听完一遍。",
    "从待办里划掉一件其实可以不做的事。",
    "把一个反复打开的页面加到容易找到的书签里。",
    "把注意力从屏幕移开，找出周围三种颜色。",
    "用一句话记下今天值得留下的一个细节。",
    "挑一条躺了很久的笔记，留一句现在的想法。",
    "给桌上最碍事的物品找个合适的位置。",
    "从明日的计划中腾出五分钟，留给临时起意。",
    "选一件今天做得还不错的事，想想下次怎么复用。",
    "给正在做的事写个收尾句，方便下次接着做。",
)


def _read_option(prompt, width):
    text = input("\n".join(wrap(prompt, width)))
    return "".join(char for char in text if char.isprintable()).strip()


def show_followups(day, identity, width, *, color=False, emoji=False):
    """Offer follow-ups after the draw has been committed and its lock released."""
    width = min(78, width)
    options = "1 详卦  ·  2 今日小任务  ·  3 二选一  ·  回车离开"
    prompt = "\n" + "\n".join(wrap(options, width)) + "\n> "
    detailed_output = None

    def show(line):
        print("\n".join(wrap(line, width)))

    try:
        while True:
            selection = input(prompt).strip()
            if not selection:
                return
            if selection == "1":
                if detailed_output is None:
                    detailed_output = render(generate(day, identity), width, color=color, emoji=emoji)
                print(detailed_output, end="")
            elif selection == "2":
                task = rotation(identity, day, "followup.task", TASKS)
                show(f"今日小任务：{task}")
            elif selection == "3":
                first = _read_option("第一项（回车返回）：", width)
                if not first:
                    continue
                second = _read_option("第二项（回车返回）：", width)
                if second:
                    chosen = secrets.choice((first, second))
                    show(f"本座抽得：{chosen}（仅供娱乐）")
            else:
                show("请输入 1、2 或 3，或按回车离开。")
    except (EOFError, KeyboardInterrupt):
        print()
