# 命令参数全表

在技能目录里跑：`python3 scripts/peichang.py <check|quick> 参数…`。只用 Python 3.9+ 标准库，不联网、不写文件。`--json` 输出结构化结果。

## check（体检：先问什么、时效、要不要停）

全部参数可选，有什么给什么：`--entry --leave --reason --wage/--wages12/--parts --city --avg-wage --contract --notice --flags --apply`。

```bash
python3 scripts/peichang.py check --leave 2025-08-31 --reason unknown --apply 2026-11-03
python3 scripts/peichang.py check --flags 派遣 --leave 2026-10-08
```

输出四块：要停下、不出金额的情形 / 要特别注意 / 仲裁时效（截止日、还剩或已超过几天）/ 要先问用户的（按顺序，带为什么）。

## quick（算钱）

| 参数 | 必填 | 写法 | 说明 |
|---|---|---|---|
| --entry | 是 | 2021-03-15 | 入职（实际开始上班）日 |
| --leave | 是 | 2026-09-30 | 离职（被解除、合同终止）日 |
| --reason | 是 | illegal_dismissal 或 违法解除 | 离职方式，见 references/codes.md；没问清写 unknown |
| --wage | 三选一 | 15000 | 离职前 12 个月平均每月税前应发（含奖金补贴） |
| --wages12 | 三选一 | 9000,9000,12000 | 逐月税前应发，最多 12 个 |
| --parts | 三选一 | 基本工资=8000,绩效=2000,年终奖=24000 | 工资构成；名字带「年」的除以 12 |
| --city | 建议 | 上海 | 劳动合同履行地，查社平工资做三倍封顶 |
| --avg-wage | 否 | 9500 | 表里没有的城市，给当地上年度职工月平均工资 |
| --min-wage | 否 | 2690 | 当地月最低工资，经济补偿基数不低于它 |
| --apply | 建议 | 2026-11-03 | 按哪天判时效；用户说了「今天是……」就照写，没说默认今天 |
| --contract | 否 | 签了 / 没签 / 补签 | 不给就不算二倍工资，并列进「还要问」 |
| --signed-date | 补签时必填 | 2025-06-01 | 补签书面合同那天 |
| --notice | 否 | 有 / 没有 / 未知 | 第四十条解除时单位有没有提前 30 天书面通知 |
| --last-wage | 否 | 16000 | 上一个月工资（代通知金用），默认用月平均 |
| --ot-in | 否 | 1500 | 月工资里平均含多少加班费，年假和二倍工资基数要剔除 |
| --renew-declined | 否 | （开关） | 合同到期单位维持或提高条件续签、员工不同意 |
| --al-years | 否 | 6 | 参加工作累计年数（含以前单位），给了才算未休年假 |
| --al-taken | 否 | 2 | 离职当年已休年假天数 |
| --al-prev | 否 | 2025=5 | 往年没休的年假 |
| --flags | 否 | 孕期 或 派遣,工伤 | 特殊情形，见 references/codes.md |
| --years | 没有入职日时 | 4 / 3.5 / 3多 | 只知道干了几年时代替 --entry；「3 年多」写 3多（按 3 年零 1 个月算，并在【回答开头照抄】里给 3.5 和 4 个月两种金额）；结果标为假设 |
| --rough | 否 | （开关） | 派遣、外包、境外等要停的情形，按普通劳动关系粗算 N 到 2N 区间，结论段写「粗算区间，不是结论」 |

输出最上面的【回答开头照抄】【还要问（逐条照抄）】两段（派遣、外包、境外、刑事、调岗降薪、受第四十二条保护的人被按第四十条或第四十一条解除、严重违纪或试用期不合格、「X 年多」时出现；check 和 quick 都有；--json 里是同名两个字段）：前者原样作回答第一段，后者每条单独问。

```bash
# 违法解除，上海
python3 scripts/peichang.py quick --entry 2021-03-15 --leave 2026-09-30 --wage 15000 --reason 违法解除 --city 上海 --contract 签了 --apply 2026-11-03
# 不能胜任被辞、没提前通知，北京
python3 scripts/peichang.py quick --entry 2022-07-01 --leave 2026-10-15 --wage 12000 --reason objective --notice 没有 --city 北京 --apply 2026-11-03
# 一直没签合同，主动辞职，问二倍工资
python3 scripts/peichang.py quick --entry 2025-03-01 --leave 2026-10-31 --wage 9000 --reason employee_resign --contract 没签 --apply 2026-11-03
# 工资里有年终奖，协商解除，顺带算年假
python3 scripts/peichang.py quick --entry 2023-01-01 --leave 2026-06-30 --parts 基本工资=6000,绩效=2000,年终奖=24000 --reason 协商-单位提出 --city 上海 --al-years 8 --al-taken 1 --apply 2026-11-03
```

输出依次是：按这些事实算的（回显）/ 结论（可主张合计，或「离职方式没问清不下结论」，或「已过时效」）/ 逐项（算式、年限折算、封顶判断、依据的法条全称和条款号、时效截止日、存疑）/ 各情形对比表 / 要特别注意 / 存疑与地方口径 / 假设 / 还要问。
