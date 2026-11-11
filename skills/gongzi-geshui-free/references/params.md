# geshui.py 参数全表和例子

只用 Python 3.8+ 标准库，在技能目录里跑。金额都按「每月」写、只写数字（可带小数、千分位逗号）。

## quick：单人逐月个税和到手

| 参数 | 含义 | 不写时 |
|---|---|---|
| `--income` | 每月应发（税前，含免税补贴） | 必填 |
| `--income-from 7=18000` | 从 7 月起应发改成 18000（涨薪），可写多个 | 不变 |
| `--income-set 6=30000` | 只有 6 月应发是 30000（当月发绩效、补发工资；补发工资并入发放当月计税），可写多个 | 不变 |
| `--si` | 三险个人合计（养老、医疗、失业） | 0，输出里写「按 0 算」 |
| `--hf` | 公积金个人 | 0 |
| `--si-from 7=2300` | 从 7 月起三险个人改成 2300（社保基数每年调整） | 不变 |
| `--base` | 缴费基数（不知道扣款金额时用，和下面两个比例配合） | — |
| `--si-rate` | 三险个人比例，百分数里的数字 | 10.5（养老 8 + 医疗 2 + 失业 0.5），输出写明是假设 |
| `--hf-rate` | 公积金个人比例 | 0；超过 12 时脚本自动算可扣部分和单位超缴并入 |
| `--special` | 专项附加扣除每月合计 | 0 |
| `--special-from 5=3000` | 从 5 月起专项附加改成 3000（如孩子满 3 岁、新增房贷） | 不变 |
| `--other` | 其他扣除：个人养老金（每月最多 1000）、商业健康险（每月最多 200）、企业年金个人缴费 | 0 |
| `--tax-free` | 每月免税收入（含在应发里） | 0 |
| `--start` / `--end` | 本单位计税从几月到几月（年中入职写 `--start`） | 1 / 12 |
| `--first-job` | 今年首次就业，减除费用从 1 月起算（国家税务总局公告 2020 年第 13 号） | 关 |
| `--sixty-k` | 上年 1~12 月都在本单位且全年工资 ≤ 6 万，1 月起按 6 万减除（2020 年第 19 号） | 关 |
| `--bonus` | 年终奖金额 | 0（不比对） |
| `--bonus-month` | 年终奖发放月 | 12 |
| `--bonus-mode` | 逐月表里年终奖按 `separate` 单独计税还是 `merge` 并入当月预扣 | separate；两种合计比对总会都算 |
| `--year` | 纳税年度，晚于 2027 年时提醒年终奖政策期限 | 2026 |

### 例子

```bash
# 月薪 2 万，基数 2 万，三险 10.5%，公积金 7%，子女教育 2000，年终奖 5 万
python3 scripts/geshui.py quick --income 20000 --base 20000 --si-rate 10.5 --hf-rate 7 --special 2000 --bonus 50000
# 1~6 月 1 万，7 月起 2 万
python3 scripts/geshui.py quick --income 10000 --income-from 7=20000 --si 1000
# 7 月调社保基数
python3 scripts/geshui.py quick --income 18000 --si 2000 --si-from 7=2300 --hf 1440
# 9 月入职的应届生，只看 9~12 月
python3 scripts/geshui.py quick --income 9000 --si 945 --start 9 --first-job
# 年终奖并入当月预扣时 12 月扣多少
python3 scripts/geshui.py quick --income 15000 --si 2250 --bonus 30000 --bonus-mode merge
```

## bonus：只给年终奖

```bash
python3 scripts/geshui.py bonus --bonus 37000 [--year 2026]
```

输出：单独计税算式、税后到手、是否落进「多发反而少拿」区间（落进就给降到下限、提到上限两个改法），离下一个临界点还有多少。要比两种计税方式，必须有工资情况，改用 quick。

## 输出结构（quick）

【输入与假设】→【逐月个税与到手】表 →【逐月算式】→【个税和到手为什么变了】→【年终奖：单独计税 vs 并入综合所得】→【临界点提醒】→【全年合计】→【依据与适用期限】。

## zones：全部「多发反而少拿」区间

```bash
python3 scripts/geshui.py zones
```

输出 6 段区间的表：区间、发到下限的税、下限多发 1 元的税、多发 1 元多交多少。用户问「年终奖怎么发最省」又没给金额时先跑它。

## 金额写法

`15000`、`15,000`、`1.5万`、`1.5w`、`15k`、`15000元` 都认，换算结果写在输出开头「金额写法换算」一行。`1.5万美元`、`abc` 这类报 E02。

## scope：超出范围的所得

```bash
python3 scripts/geshui.py scope labor --amount 8000          # 劳务报酬（讲课费、设计费、兼职费）每次收入
python3 scripts/geshui.py scope royalty --amount 8000        # 稿酬
python3 scripts/geshui.py scope business --profit 300000 [--getihu]   # 经营所得全年利润；个体工商户加 --getihu 算减半
python3 scripts/geshui.py scope foreign --income 50000       # 非居民个人当月工资
python3 scripts/geshui.py scope allowance                    # 外籍个人补贴免税
python3 scripts/geshui.py scope avoid                        # 避税要求：不做什么、风险、合法做法
```

输出只有【回答要点】：固定开头（这一类不归本技能计算，以单位和主管税务机关确认为准）、基本算式、会改变结果的因素。缺必填数报 E01。

## 每条命令输出的第一段

quick、bonus、scope 的输出都以【回答要点】开头：几句可以直接抄进回答正文的整话（结论数、换算、扣款、逐月个税和到手、为什么变了、依据和期限、要你确认的）。后面才是完整表格和算式。
