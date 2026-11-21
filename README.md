# 今日运势 · Daily Fortune CLI

在 Windows 或 macOS 终端每天抽一张中文娱乐短签，看看财运、桃花运、事业运，以及当天的符卡和点评。还可以展开详卦、领取一个小任务，或让程序替你在两个日常选项中随机择一。运行时完全离线，只用 Python 标准库。

**1.6.1 精炼太卜式原创文案，统一卦盘、行止与现实优先说明。** [Windows 安装](#windowspowershell) · [macOS 安装](#macos) · [下载 main 分支源码 ZIP](https://github.com/9178osage/daily-fortune/archive/refs/heads/main.zip)

```text
穷观阵推演已毕，本座取艮势 (｡･ω･｡)（仅供娱乐）
财运：43
桃花运：23
事业运：20
符卡：旧物符「旧藏可用」
点评：末吉。今势转慢，宜候反馈，不宜催成。
★★☆☆☆☆☆
```

这是一个娱乐项目。分数、兆象、签文和宜忌都由程序生成，不预测现实结果；太卜式语感取其演算、趋势和留退路的抽象特征，文案为原创，未复刻角色台词。[查看短签与详卦完整示例](docs/example.txt)

## 快速开始

需要 Python 3.9 或更高版本。在 [GitHub Releases](https://github.com/9178osage/daily-fortune/releases) 选择版本，下载该版本的 `daily-fortune-vX.Y.Z.zip` 和 `SHA256SUMS`，校验后解压。macOS 可在下载目录执行 `shasum -a 256 -c SHA256SUMS`。Windows 可用 `Get-FileHash -Algorithm SHA256` 计算 ZIP 的哈希，再与 `SHA256SUMS` 对照。

如果 GitHub 自动生成的源码 ZIP 下载中断，请重新下载完整文件再校验。也可以用 Git 获取当前源码。进入解压或克隆得到的目录后，执行对应平台的安装命令。

```sh
git clone https://github.com/9178osage/daily-fortune.git
cd daily-fortune
```

### Windows（PowerShell）

安装 Python 后，用 `py -3 --version` 或 `python --version` 确认版本。在解压或克隆得到的目录中打开 PowerShell。安装只写入当前用户的目录，无需管理员权限。 [下载 Windows 版 Python](https://www.python.org/downloads/windows/)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
& "$env:LOCALAPPDATA\daily-fortune\bin\daily-fortune.cmd" --version
```

`-ExecutionPolicy Bypass` 仅对运行安装脚本的这个 PowerShell 进程有效。安装后，在任何目录都可以用上面的完整路径启动，去掉 `--version` 即可抽签。若想在当前窗口直接输入 `daily-fortune`，先把启动器目录加入当前会话的 PATH。

```powershell
$env:Path = "$env:LOCALAPPDATA\daily-fortune\bin;$env:Path"
daily-fortune
```

也可以直接从源码预览指定日期的短签。如果系统提供的是 `python` 命令，将 `py -3` 换成 `python`。

```powershell
py -3 .\main.py --date 2026-11-08
```

Windows PowerShell 5.1 通过管道读取输出时，若中文显示异常，可先在当前窗口运行 `[Console]::OutputEncoding = [Text.Encoding]::UTF8`。

### macOS

安装 [macOS 版 Python](https://www.python.org/downloads/macos/) 后，在源码目录预览短签。

```sh
./今日运势 --date 2026-11-08
```

想在任意目录输入 `今日运势`，在源码目录运行以下命令。

```sh
./install.sh
export PATH="$HOME/.local/bin:$PATH"
今日运势
```

如果希望新终端也能找到命令，将上面的 `export` 行加入 `~/.zshrc`。程序副本安装在 `~/.local/share/daily-fortune/app/`，可独立于源码目录运行。

## 怎么玩

直接运行时，按系统本地日期每天可抽一张短签。当天再运行会看到一句提醒。交互终端里可按 `1` 展开详卦、`2` 领今日可行小事、`3` 随机择一，或按回车收阵。

| 参数 | 用途 |
| --- | --- |
| `--full` | 查看七项卦势、今日兆象、赛博黄历和太卜寄语 |
| `--date 2026-11-08` | 预览指定日期的短签 |
| `--full --date 2026-11-08` | 查看指定日期的详卦 |
| `--plain` | 用数字表示星级，关闭颜色、Emoji 和菜单 |
| `--help` | 查看参数说明 |
| `--version` | 查看版本 |

`--date` 和 `--full` 可随时使用，且不占当天的抽签次数。单独使用 `--plain` 会计入当天次数。

## 更新与卸载

在克隆下来的目录中执行 `git pull --ff-only` 获取新版。如果用的是 ZIP，则改在新版解压目录中执行更新。更新和卸载都会保留匿名标识和抽签记录。

如果更新或卸载进程在切换时被终止，用当前版本或更新版本的维护脚本重试。脚本会先恢复上次未完成的切换，再执行本次命令。

### Windows

在新版源码目录中执行更新。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\update.ps1
```

需要移除已安装的命令时，执行卸载。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\uninstall.ps1
```

默认状态目录是 `%LOCALAPPDATA%\daily-fortune\state`。升级前的程序副本会保存在安装目录的 `backups` 下。如果安装时用了 `-Prefix`，启动器位于该目录的 `bin\daily-fortune.cmd`，更新和卸载时也要传入同一个 `-Prefix`。

### macOS

在新版源码目录中执行更新。

```sh
./update.sh
```

需要移除已安装的命令时，执行卸载。

```sh
./uninstall.sh
```

默认状态目录是 `~/.local/share/daily-fortune/state/`。

<details>
<summary>macOS 自定义安装与维护</summary>

- 安装、更新和卸载均接受 `--prefix`。使用自定义目录时，三次操作需指向同一个目录。
- 可用 `PYTHON=/绝对路径/python3 ./install.sh` 选择解释器。启动器绑定 Python 的绝对路径。用 `PYTHON=/新路径/python3 ./update.sh` 可以更换绑定，即使原解释器已移除也可以更新。
- 安装时若遇到已存在的同名命令或安装文件，安装器会停止并提示冲突。卸载会核对清单和文件校验值，遇到改动或未知文件时会停止。
- 更新会校验已安装文件并验证新版本，再切换程序副本。旧程序和清单保存在更新完成时打印的备份目录。

</details>

## 每日签文如何生成

首次运行会在本地生成随机匿名标识。同一个标识在同一天、同一版本下会抽到相同的签。程序只在本机保存标识和抽签记录。赛博黄历借用宜忌的形式，提供原创的日常行动提示。

<details>
<summary>生成算法与内容轮换</summary>

算法版本是 `daily-fortune-v1`。基本序列为：

```text
SHA256(UTF8(JSON([算法版本, 匿名标识, ISO日期, 字段标签, 计数器])))
```

JSON 规定使用紧凑分隔符和原始 Unicode；摘要按大端整数读取，再用拒绝采样映射到整数范围。所有计算使用固定整数规则，不用内置 `hash()`，也不依赖 `random.choice()` 的跨版本实现。每个评分、颜色、意象和寄语字段都有独立标签；新增无关字段不会消耗现有字段的序列。

1. 先生成一个公共节奏值与专注、秩序、联结、活力四个偏移；六个领域分别加上对应偏移及独立的小扰动，限制为 1–5 星。这让相关领域略有联系，同时保留差异。这些权重是娱乐设计，不是对人的测量。
2. 综合星级是六项的算术平均，按整数“四舍五入”显示。签等级按未取整的六项总分确定：

| 总分 | 等级 | 本项目含义 |
| --- | --- | --- |
| 6–9 | 凶 | 缓行、核对，不预示灾祸 |
| 10–13 | 末吉 | 留白、整理 |
| 14–17 | 平 | 平常节奏 |
| 18–21 | 小吉 | 积累小进展 |
| 22–25 | 中吉 | 选准重点 |
| 26–30 | 大吉 | 舒展、小步尝试 |

这是本项目的原创顺序与映射，不声称是所有寺社通用的传统。相同的综合星级可能对应不同签级，因为显示星级经过取整。

3. 从最高分领域确定主题；最低分领域提供提醒，平分时用独立标签选择。最高分也可能只有一两星，因此主题使用中性意象。分数 1–2、3、4–5 分别选取收束、平稳、尝试类文案。宜覆盖三个不同领域并匹配各自星级；忌始终是明确的负面行为。寄语引用实际选中的行动和提醒，不另抽一份相冲突的结论。
4. 句段与幸运元素使用“日历洗牌”：对每个固定候选集合，按匿名标识、字段和日期块产生排序，每 N 天遍历 N 个候选；若块交界处首尾重复，只交换新块的前两项。结果不依赖查询顺序，不记录历史，也不通过反复运行刷新。幸运数字在 1–99 中轮换，颜色、关键词与物品来自当天主题。

内容库含 108 条领域建议、90 条宜、36 条忌、36 组双句意象、36 条等级解签，以及多组兆象元素、推演开场和理性收尾。多样性来自结构与语义约束下的组合。有限内容会再次出现，某项星级连续相同也完全正常；不承诺每天每一句都不同。固定候选池的轮换可避免该池连续日期直接重复，但主题或分数切换后的子池重新进入不作此保证。

复现保证以匿名标识、日期、算法和内容版本相同为前提。更换标识、改变参与评分的规则或编辑某个候选池可能改变对应结果；无关新字段不影响已有字段。保留 `user-id` 可在重装后延续相同版本的结果。源码直接运行可用绝对路径 `DAILY_FORTUNE_HOME` 指定隔离状态目录；已安装启动器固定使用其安装目录内的状态。

</details>

## 开发与测试

1.6.0 已在 GitHub Actions 上通过 Windows（Python 3.9、3.13）和 macOS（Python 3.13）测试。Windows 用例涵盖中文路径、并发抽签、安装、升级、卸载重装及记录保留。1.6.1 增加了跨平台路径边界、安装回滚、控制台状态和输出语气回归。[查看 1.6.0 测试结果](https://github.com/9178osage/daily-fortune/actions/runs/43582674509)

在 macOS 上运行全套测试。

```sh
python3 -B -m unittest discover -s tests -v
```

Windows 上运行运势、命令行和安装流程的测试。

```powershell
py -3 -B -m unittest -v tests.test_engine tests.test_cli tests.test_windows
```

- [设计调研与来源](docs/RESEARCH.md)
- [历史测试记录与环境](docs/TESTING.md)
- [Windows 与 macOS 自动化测试](https://github.com/9178osage/daily-fortune/actions/workflows/tests.yml)

### 类型检查与 Lint

在 macOS 上可将开发依赖装在虚拟环境中运行以下检查。Windows PowerShell 脚本和 GitHub Actions 工作流也由 CI 检查。

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m mypy --no-incremental --platform darwin --exclude 'daily_fortune/_windows\.py$'
python -m mypy --no-incremental --platform win32
python -m ruff check .
shellcheck --norc -s sh install.sh update.sh uninstall.sh 今日运势
```

### 发布

推送与 `daily_fortune/__init__.py` 版本号一致的 `vX.Y.Z` 标签会启动发布流程。Windows 和 macOS 测试及静态检查通过后，工作流打包该标签的源码，生成 SHA-256 校验文件，从 ZIP 试装，再将两份文件上传到 GitHub Releases。
