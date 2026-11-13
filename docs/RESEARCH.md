# 「今日运势」调研记录

检查日期：2026-11-08。先完成资料阅读与设计归纳，再进入实现。下列网页、文档和仓库由本项目调研实际打开；源码、README 和运营方自述的证据范围分别标明。未运行外部项目，也未审计运势网站后台。

## 研究结论

适合借鉴的核心是“分领域报告、当天主题、简短签文、具体行动提示”。星座网站擅长分类，黄历提供宜忌的文化形式，御神签提供等级与解释的仪式感，单卡玩法提供每天一个思考主题。它们没有统一的生成规则，不能直接拼接成一套声称真实有效的预测方法。

本项目采用原创娱乐规则：先生成评分、强弱项和主题，再选择相符的原创句段；幸运元素保持主题一致；用独立的确定性序列与跨日轮换降低重复感。程序不计算星盘、不复刻传统择日、不要求生日，也不使用在线模型。分数和等级只决定报告的叙事节奏。

## 十项调研与取舍

### 1. 每日运势网站和应用的常见功能

[Astrology.com 每日页](https://www.astrology.com/horoscope/daily/aries.html)提供日期、昨日／今日／明日、工作和情感等入口，并连接每日塔罗和幸运数字玩法。[Horoscope.com 每日页](https://www.horoscope.com/us/horoscopes/general/horoscope-general-daily-today.aspx?sign=1)区分多个生活领域、星级及每日牌卡。

借鉴固定栏目、简短概览和指定日期查看，舍弃账户、付费服务和联网依赖。上述是可观察的产品结构；页面预测的实际效力不在这些观察中得到验证。

### 2. 星座每日运势的分类和内容结构

上述页面及 [Horoscope Daily 方法页](https://horoscope-daily.net/methodology/)展示了综合、情感、事业、财富、活力、情绪、行动提示等结构。后者自述先准备结构化信息，再组织文案并检查格式、禁用表述和重复；这是运营方公开说明，不能等同于后台代码审计结果。

本项目固定显示综合、学习、事业、财富、社交、情感、健康与活力七项。每项不仅有星级，还配一条与分数区间相符的原创建议；寄语引用实际强弱项，避免各栏目独立抽句。

### 3. 中国传统黄历中的宜忌

[国史馆台湾文献馆《通书》词条](https://dict.th.gov.tw/detailPage.aspx?Ca=40&ID=2650)介绍了通书作为历书与民间行事参考的文化背景，以及干支、宜忌、方位、时刻等内容。[Chinese Almanac 实页](https://chinesealmanac.com/)展示了现代网站如何呈现按日的宜忌活动和方位。[香港天文台公历与农历对照表](https://www.hko.gov.hk/en/gts/time/conversion.htm)则是可核对的历法资料。

历法转换与择日信念应分开理解：农历日期可以按历法核查，但历表本身不能证明“某天适合某种行为”的预测效力。本项目只借用“宜／忌”的表达形式，创作学习、编程、散步、音乐等现代内容，并明确称为“赛博黄历”，不冒充传统黄历计算结果。

### 4. 塔罗每日单卡的娱乐玩法

[Labyrinthos 单卡页](https://labyrinthos.co/pages/one-card-tarot)把每日单卡描述为关注当下的短暂活动，并提供牌面选择、解释及日记等延伸入口。此处借鉴每天一个主题和解释的形式，不把运营方的心理或占卜表述当作经验证据。

本项目采用原创“今日意象”，使主题、颜色、关键词与签文共享语境。不复制塔罗牌图、牌义文字，也不为一个轻量 CLI 引入完整牌库或用户记录系统。

### 5. 日本御神签的等级、签文与形式

[JNTO 御神签介绍](https://faq.japan-travel.jnto.go.jp/en/japan-magazine/2007_omikuji/)展示了纸签、编号抽取、总体等级、健康／工作／学习等细项，以及吉凶之外的解释和建议。[日本观光厅的明治神宫资料](https://www.mlit.go.jp/tagengo-db/en/H30-00533.html)说明，该处“大御心”使用附解释的和歌，与普通吉凶签不同。这一差异说明不能把所有神社寺院简化成同一张等级表。

本项目自定“大吉、中吉、小吉、平、末吉、凶”六档，按生成评分解释为不同的行动节奏。这是原创娱乐分级，不宣称是日本传统的统一顺序或比例。“凶”仅表示放慢、核对、留余地，不暗示灾祸；签文全部原创。

### 6. 幸运数字与幸运颜色的生成

[Astrology.com numerology 教学](https://www.astrology.com/numerology)介绍了按出生日期数字归约等玩法。[Horoscope Daily 方法页](https://horoscope-daily.net/methodology/)则自述幸运数来自星座与日期，颜色来自元素色组。两种方案体现了不同的娱乐约定，没有统一规范，也不能由此推断数字或颜色会改变现实结果。

本项目不索取生日，使用随机安装标识、日期和独立字段标签派生幸运数字。颜色、关键词与物品从主题适配的原创集合中选择，使其在报告中有一致的意象。

### 7. GitHub Fortune / Daily Fortune / CLI 项目

| 一手资料 | 实际阅读范围与观察 | 本项目借鉴 |
| --- | --- | --- |
| [shlomif/fortune-mod](https://github.com/shlomif/fortune-mod) | README：Unix fortune 实现，从本地引文库输出内容 | 内容与执行逻辑分离、完全离线；本项目增加结构化生成 |
| [HubTou/fortune](https://github.com/HubTou/fortune) | 项目说明：Python BSD fortune 重实现，具有分类和长度过滤等 CLI 参数 | 常规参数、清晰退出行为、轻量结构 |
| [bmc/fortune-go 源码](https://github.com/bmc/fortune-go/blob/master/fortune.go) | 源码：本地文本以分隔符切分，按当前纳秒时间播种抽取 | 简单本地数据；其时间播种方式不满足本项目同日固定要求 |
| [ZichenYuan/terminal-fortune-cookie README](https://github.com/ZichenYuan/terminal-fortune-cookie/blob/main/README.md) | README：开发者分类、ASCII art、颜色库、shell 启动集成；未测量作者声称的性能 | 轻巧的仪式感；无需其依赖和自动启动执行 |
| [jimmy668765/daily-fortune README](https://github.com/jimmy668765/daily-fortune/blob/main/README.md) | README：输入信息后生成分类特征、主题和文案，并涉及 iCal | “结构特征→条件文案”；不采用生辰采集、预测效力说法和日历功能 |

未复制这些项目的代码或引文库；仅归纳架构与交互思路。README 阅读不能证明实现正确或适用于本机。

### 8. 终端 ASCII、ANSI、Unicode 与排版

[Xterm 控制序列文档](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html)提供 SGR 颜色与复位机制；[NO_COLOR 约定](https://no-color.org/)要求非空环境变量关闭默认颜色。[Unicode UAX #11](https://www.unicode.org/reports/tr11/)说明东亚宽度属性及其在现代终端中的限制；[UTS #51](https://www.unicode.org/reports/tr51/)说明 Emoji 可包含变体选择符、肤色与 ZWJ 序列。[iTerm2 文本设置](https://iterm2.com/documentation-preferences-profiles-text.html)允许调整 Unicode 宽度与模糊宽度字符，实际显示因此也取决于用户设置。

本项目使用纵向栏目、短分隔线和少量装饰，避免依赖复杂 Emoji 对齐的封闭表格。按终端显示列换行，提供 `--plain`；非 TTY、`TERM=dumb` 与 `NO_COLOR` 情形关闭默认颜色。标准库宽度估算应明确其边界，不声称覆盖所有字体和完整 Unicode 字素分段。

### 9. 每日稳定的确定性伪随机

[Python 数据模型](https://docs.python.org/3/reference/datamodel.html#object.__hash__)明确说明字符串与字节的哈希默认带进程随机盐，不能用内置 `hash()` 作为跨进程稳定种子。[hashlib](https://docs.python.org/3/library/hashlib.html)提供 SHA-256；[random 的可复现说明](https://docs.python.org/3/library/random.html#notes-on-reproducibility)指出跨版本保证的范围，不能假定所有随机辅助算法永远不变。[date.today()](https://docs.python.org/3/library/datetime.html#datetime.date.today)读取本地日期。

本项目工程方案是明确序列化版本、匿名标识、日期、字段域和计数器，使用 SHA-256 与整数运算派生结果。字段域独立，使新增模块不消耗其他模块的序列。匿名标识只保存在本地，不读取硬件序列号、MAC 地址或出生信息。该机制保证娱乐内容可复现，并不增加预测能力。

### 10. 丰富度、一致性与减少机械重复

fortune 项目说明本地内容库可以快速运行；Horoscope Daily 的公开方法说明“先结构后文案”和重复检查是一种实际产品思路，但无需照搬其在线模型流程。

本项目将多样性分成多个层次：分数差异、最强／最弱领域、当天主题、对应等级、意象、行动和句段组合。先限定语义适配集合，再做确定性跨日轮换；查询顺序不应改变结果，也无需保存查询历史。宜使用正面小行动，忌使用明确的不良行为，以减少互相否定。某个评分或句段隔日再次出现是有限集合的正常现象，不等于随机机制失败；不承诺无限不重复。

## macOS 安装的补充依据

[Python 官方 macOS 文档](https://docs.python.org/3/using/mac.html)介绍了支持 Apple Silicon 与 Intel 的 universal2 发行方式，并提醒不要修改 Apple 控制的 Python。项目因此优先使用已有 Python 3，只安装到用户目录，不用 sudo、不改系统解释器。缺少 Python 时提供官方安装入口并退出，不擅自下载。安装与卸载的冲突、权限和清单校验属于本项目的工程设计，需由本地测试验证。

## 2026-11-12 流程完善调研

以 Python 3.9 版文档核对最低兼容版本的标准库接口，并查阅 Apple Terminal 和 iTerm2 的设置说明。以下为本轮设计与验证的依据。

- **本地日期与参数。** `date.today()` 按本地时间取日历日期，可作为每日抽签记录的日期键。显式日期通过 `argparse` 校验，帮助、版本、非法参数和指定日期查看应分别验证，避免查看路径误记为当天抽签。 [Python `date.today()`](https://docs.python.org/3.9/library/datetime.html#datetime.date.today) · [Python `argparse`](https://docs.python.org/3.9/library/argparse.html#argparse.ArgumentParser)
- **匿名标识。** `secrets.token_hex(16)` 将系统随机源的 16 字节编码成 32 个十六进制字符，可在首次启动时生成本地安装标识。`mkstemp()` 支持在指定目录独占创建用户私有的临时文件，适合先完成写入，再发布标识。并发首次启动应验证各进程读到同一个完整值。 [Python `secrets.token_hex`](https://docs.python.org/3.9/library/secrets.html#secrets.token_hex) · [Python `tempfile.mkstemp`](https://docs.python.org/3.9/library/tempfile.html#tempfile.mkstemp)
- **每日记录与并发。** `flock` 是基于已打开文件的协作锁，可串行化遵循同一锁约定的抽签进程。验证应覆盖同时启动、输出管道提前关闭和重新打开终端。缓冲文件先 `flush()` 再 `fsync()`，分别处理 Python 缓冲和系统文件同步。终端输出与状态写入分属两个操作，故障测试需分别观察这两个结果。 [Python `fcntl.flock`](https://docs.python.org/3.9/library/fcntl.html#fcntl.flock) · [Apple `flock(2)`](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/flock.2.html) · [Python `os.fsync`](https://docs.python.org/3.9/library/os.html#os.fsync)
- **交互与重定向。** `pty.openpty()` 提供可自动化验证的伪终端，可用来检查交互入口、输入选择与终端颜色，再用管道或重定向核对非交互输出。非空 `NO_COLOR` 用于关闭默认 ANSI 颜色。窗口列数可从 `COLUMNS` 或终端取得，查询失败时采用预设值。 [Python `pty.openpty`](https://docs.python.org/3.9/library/pty.html#pty.openpty) · [Python `shutil.get_terminal_size`](https://docs.python.org/3.9/library/shutil.html#shutil.get_terminal_size) · [NO_COLOR 约定](https://no-color.org/)
- **中文与字符宽度。** Apple Terminal 的配置可分别调整 ANSI 颜色、文本编码和东亚模糊宽度字符，iTerm2 也有宽度设置。`unicodedata.east_asian_width()` 可作为换行估算的输入。字体、Emoji 和模糊宽度设置仍影响最终显示，验证时应覆盖窄屏与纯文本模式。 [Apple Terminal 文本设置](https://support.apple.com/en-mk/guide/terminal/trmltxt/mac) · [Apple Terminal 高级设置](https://support.apple.com/en-az/guide/terminal/trmladvn/mac) · [iTerm2 文本设置](https://iterm2.com/documentation-preferences-profiles-text.html) · [Python `unicodedata`](https://docs.python.org/3.9/library/unicodedata.html#unicodedata.east_asian_width)
- **安装、升级与备份。** 同一文件系统内成功的 `os.rename()` 或 `os.replace()` 对单次重命名提供原子性。采用替换前应核验清单和同名目标，在切换程序前保留可恢复的旧版本，并将匿名标识和抽签记录纳入本地状态保留范围。程序目录、启动器和清单的多步切换需要各自的失败检查与回退验证。 [Python `os.rename`](https://docs.python.org/3.9/library/os.html#os.rename) · [Python `os.replace`](https://docs.python.org/3.9/library/os.html#os.replace)


- **验证环境与版本。** Python 的隔离模式忽略 PYTHON 环境变量。真实启动器继续使用隔离模式，哈希种子和输出编码回归则直接启动非隔离的 Python 进程。Python 3.9 与 3.10 已结束维护，本项目保留 3.9 运行兼容，新装可从仍受维护的版本中选择。 [Python 隔离模式](https://docs.python.org/3.9/using/cmdline.html#cmdoption-I) · [Python 版本状态](https://devguide.python.org/versions/)
- **未设置窗口尺寸的伪终端。** Python 3.11 起在系统返回零列时使用预设尺寸，本项目为 Python 3.9 补上同样的回退。中文标点避头尾参考 Unicode 换行规则。 [Python 窗口尺寸](https://docs.python.org/3/library/shutil.html#shutil.get_terminal_size) · [Unicode UAX #14](https://www.unicode.org/reports/tr14/)

Apple Terminal 的指南首页和窗口设置页本次直接打开返回 429。上面列出的文本与高级设置页已实际打开，并用于核对相关行为。

## 无法访问与证据边界

以下资料实际访问失败，没有据其搜索摘要编造内容：

- [神社本厅御神签页](https://www.jinjahoncho.or.jp/omairi/omikuji/)：返回 503。
- [Co–Star 官网](https://www.co-starastrology.com/)：工具无法访问，未研究 App 内功能。
- [Biddy Tarot 搜索命中的单卡 PDF](https://biddytarot.com/wp-content/uploads/2023/03/BT-Deck-30-Tarot-Spreads-PDF.pdf)：返回 404。
- [Outilix 每日运势页](https://outilix.eu/en/daily-horoscope/)：返回 Cache miss。
- [Japan Travel 的 guide/omikuji 入口](https://www.japan.travel/en/guide/omikuji/)：工具无法访问；改用上面可读的 JNTO 专题与观光厅资料。

网页结构与可用性可能变化。这里记录的是检查时实际读到的资料与相应设计推论，不构成对任何运势方法有效性的认可。所有程序运势文案均为原创娱乐内容，不用于现实决策。
