"""离职方式代码、特殊情形、输入校验、体检（check）。代码表也写在 references/codes.md。"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import date

from . import dates
from .errors import fail

# 代码 → (说明, 结果)
REASONS = {
    "employer_negotiated": ("单位提出、双方协商一致解除", "N"),
    "employee_negotiated": ("员工提出、双方协商一致解除", "0"),
    "objective": ("单位依第四十条解除（医疗期满不能工作、不能胜任、客观情况重大变化）", "N，没提前30天书面通知再加1个月（N+1）"),
    "layoff": ("经济性裁员（第四十一条）", "N"),
    "contract_expired": ("固定期限合同到期，单位不续签", "N（单位维持或提高条件续签、员工不同意的为0）"),
    "employee_forced": ("单位欠薪、不缴社保等，员工依第三十八条解除（被迫离职）", "N"),
    "employee_resign": ("员工主动辞职", "0"),
    "illegal_dismissal": ("单位违法解除或违法终止（员工已确认没有法定理由，或单位理由明显不成立）", "2N"),
    "misconduct": ("单位以严重违纪等第三十九条理由解除，员工不认", "理由成立为0，不成立为2N"),
    "probation_fail": ("单位以试用期不符合录用条件解除，员工不认", "理由成立为0，不成立为2N"),
    "closure": ("单位破产、被吊销、责令关闭、撤销或提前解散", "N"),
    "unknown": ("离职方式还没问清", "不下结论，只列各情形对比"),
}

REASON_ALIAS = {
    "协商-单位提出": "employer_negotiated", "单位协商": "employer_negotiated", "公司协商": "employer_negotiated",
    "协商-员工提出": "employee_negotiated", "员工协商": "employee_negotiated",
    "第四十条": "objective", "不能胜任": "objective", "医疗期满": "objective", "客观情况变化": "objective",
    "裁员": "layoff", "经济性裁员": "layoff",
    "到期不续": "contract_expired", "合同到期": "contract_expired",
    "被迫离职": "employee_forced", "被迫解除": "employee_forced",
    "主动辞职": "employee_resign", "辞职": "employee_resign",
    "违法解除": "illegal_dismissal", "违法辞退": "illegal_dismissal",
    "违纪辞退": "misconduct", "严重违纪": "misconduct",
    "试用期不合格": "probation_fail",
    "公司关闭": "closure", "破产": "closure",
    "未确认": "unknown", "不清楚": "unknown",
}

# 这些情形不出金额：说清不同在哪、先走什么程序、找谁
STOP_FLAGS = {
    "work_injury": "涉及工伤（认定、伤残等级、一次性伤残补助金和就业补助金）：先做工伤认定和劳动能力鉴定，金额按《工伤保险条例》和当地规定算，请找律师、当地工伤保险经办机构或拨 12348 法律援助",
    "dispatch": "劳务派遣：劳动合同在派遣单位，用工单位退回和派遣单位解除各有条件，用工单位造成损害的两家承担连带责任（《中华人民共和国劳动合同法》第九十二条），要看派遣协议，请找律师或当地劳动人事争议仲裁委员会窗口",
    "outsourcing": "外包、驻场、挂靠：先要分清和谁签的劳动合同、谁发工资、谁交社保，才知道向谁主张；名为外包实为派遣的还要另判，请找律师或当地劳动人事争议仲裁委员会窗口",
    "overseas": "境外用工（在境外工作、境外公司雇佣、外派出国）：先判适用哪国法律、合同和用人单位是谁，本技能只按中国大陆劳动法算，请找熟悉涉外劳动的律师",
    "foreign": "外籍、港澳台人员：有没有依法办理工作许可影响是否按劳动关系处理，请找律师",
    "retired": "已达退休年龄或已领养老金：一般按劳务关系处理，不适用经济补偿和二倍工资（法释〔2020〕26号第三十二条），请找律师",
    "civil_servant": "公务员、参公或事业编制：走人事争议或人事申诉，规则不同，请找律师或单位人事部门",
    "group": "十人以上集体争议、群体欠薪：可能走集体程序、推代表，请找当地劳动监察、劳动人事争议仲裁委员会或律师",
    "non_compete": "竞业限制、培训服务期违约金、股权期权：按协议和专门规则算，超出本技能范围，请找律师",
    "part_time": "非全日制用工：双方可以随时终止、不付经济补偿；要先核实是不是真的非全日制（每天不超过4小时、每周不超过24小时），请找律师",
    "criminal": "涉及刑事（被指职务侵占、泄密，单位报警，或想告老板拒不支付劳动报酬罪）：刑事部分要找刑辩律师或向公安、劳动监察反映，本技能只算民事上的劳动赔偿",
}

CAUTION_FLAGS = {
    "pregnant": "女职工在孕期、产期、哺乳期：单位不得依第四十条、第四十一条解除（《中华人民共和国劳动合同法》第四十二条），合同到期也要顺延到情形消失（第四十五条）；单位这样解除或到期终止的，一般按违法解除主张 2N",
    "medical_period": "患病或非因工负伤、还在医疗期内：单位不得依第四十条、第四十一条解除（《中华人民共和国劳动合同法》第四十二条）",
    "near_retire_15y": "在本单位连续工作满十五年、离法定退休年龄不足五年：单位不得依第四十条、第四十一条解除（《中华人民共和国劳动合同法》第四十二条）",
}

# 不停、照算，但回答开头和要问的问题由脚本给（ldlib/lead.py）
TOPIC_FLAGS = {
    "transfer": "被调岗、降薪、穿小鞋，还没走、想知道走了能拿多少",
}

FLAG_ALIAS = {
    "调岗": "transfer", "降薪": "transfer", "调岗降薪": "transfer", "穿小鞋": "transfer", "排挤": "transfer",
    "工伤": "work_injury", "派遣": "dispatch", "劳务派遣": "dispatch", "外包": "outsourcing", "驻场": "outsourcing",
    "境外": "overseas", "外派": "overseas", "外籍": "foreign", "港澳台": "foreign", "退休": "retired", "返聘": "retired",
    "编制": "civil_servant", "公务员": "civil_servant", "集体": "group", "竞业": "non_compete", "股权": "non_compete",
    "非全日制": "part_time", "兼职": "part_time", "刑事": "criminal", "报警": "criminal",
    "孕期": "pregnant", "怀孕": "pregnant", "产期": "pregnant", "哺乳期": "pregnant", "医疗期": "medical_period",
    "老员工": "near_retire_15y",
}

WAGE_MAX = Decimal("10000000")   # 月工资超过一千万，多半是多打了零


def reason_code(raw: str | None) -> str | None:
    s = str(raw or "").strip()
    if not s:
        return None
    code = REASON_ALIAS.get(s, s)
    if code not in REASONS:
        raise fail("E06", f"离职方式「{s}」认不出",
                   "从 references/codes.md 的离职方式表里选一个代码（如 illegal_dismissal）或中文别名（如 违法解除）；"
                   "还没问清就写 unknown", 4)
    return code


def flag_set(raw: str | None) -> set[str]:
    out: set[str] = set()
    for part in str(raw or "").replace("，", ",").replace("、", ",").split(","):
        p = part.strip()
        if not p:
            continue
        k = FLAG_ALIAS.get(p, p)
        if k not in STOP_FLAGS and k not in CAUTION_FLAGS and k not in TOPIC_FLAGS:
            raise fail("E06", f"特殊情形「{p}」认不出", "从 references/codes.md 的特殊情形表里选（如 dispatch 或 派遣）", 4)
        out.add(k)
    return out


def num(v: object, field: str, allow_zero: bool = False) -> Decimal:
    s = str(v if v is not None else "").replace(",", "").replace("，", "").strip()
    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        raise fail("E04", f"「{field}」不是数字：{v}", "只写阿拉伯数字，比如 12000，不带「元」「k」「万」", 4) from None
    if not d.is_finite():
        raise fail("E04", f"「{field}」不是有效数字：{v}", "只写阿拉伯数字，比如 12000", 4)
    if d < 0:
        raise fail("E04", f"「{field}」是负数：{v}", "金额、天数都写正数", 4)
    if d == 0 and not allow_zero:
        raise fail("E04", f"「{field}」是 0", "写离职前 12 个月平均每月税前应发多少；真的一分没发过的属于欠薪，先问清约定的工资", 4)
    if d > WAGE_MAX:
        raise fail("E04", f"「{field}」{v} 超出合理范围", "核对是不是多打了零、是不是把年薪当月薪", 4)
    return d


def wage_from(wage: str | None, wages12: str | None, parts: str | None) -> tuple[Decimal | None, str, list[str]]:
    """月平均应得工资。返回（数值，来源说明，存疑）。三种给法：单个数、逐月数、工资构成。"""
    doubts: list[str] = []
    if wages12:
        vals = [num(v, f"--wages12 第 {i + 1} 个", allow_zero=True)
                for i, v in enumerate(x for x in wages12.replace("，", ",").split(",") if x.strip())]
        if not vals or len(vals) > 12:
            raise fail("E05", f"--wages12 给了 {len(vals)} 个月", "只填解除前最近 1~12 个月每月税前应发，用逗号隔开", 4)
        avg = sum(vals, Decimal(0)) / len(vals)
        if avg == 0:
            raise fail("E04", "--wages12 每个月都是 0", "填税前应发工资；一直没发属于欠薪，先问清约定工资", 4)
        return avg, f"离职前 {len(vals)} 个月税前应发工资平均（{' + '.join(str(v) for v in vals)}）÷ {len(vals)}", doubts
    if parts:
        total, desc = Decimal(0), []
        for seg in parts.replace("，", ",").split(","):
            if not seg.strip():
                continue
            name, sep, val = seg.partition("=")
            if not sep:
                raise fail("E04", f"--parts 这一段认不出：{seg}", "写成 基本工资=8000,绩效=2000,年终奖=24000", 4)
            d = num(val, f"--parts {name.strip()}", allow_zero=True)
            if "年" in name:          # 年终奖、年度奖金按 12 个月摊
                total += d / 12
                desc.append(f"{name.strip()} {d} ÷ 12")
                doubts.append(f"{name.strip()}按 12 个月摊进月工资：多数地方的仲裁委认可年终奖属于工资，但跨年度发放、发放年度和计算年度对不上的，各地处理不一，以当地劳动人事争议仲裁委员会的口径为准")
            else:
                total += d
                desc.append(f"{name.strip()} {d}")
            if "加班" in name:
                doubts.append("加班费算不算进经济补偿的月工资，各地口径不一（多数算进去），以当地劳动人事争议仲裁委员会为准")
        if total == 0:
            raise fail("E04", "--parts 合计是 0", "填税前应发的各项工资", 4)
        return total, "税前应发的工资构成相加：" + " + ".join(desc), doubts
    if wage not in (None, ""):
        return num(wage, "--wage"), "买家报的数，当作离职前 12 个月平均税前应发工资（扣社保个税之前，含奖金津贴补贴）", doubts
    return None, "", doubts


def check(entry: str | None, leave: str | None, reason: str | None, has_wage: bool, city: str | None,
          avg_wage: str | None, contract: str | None, flags: set[str], apply: date,
          notice: str | None = None) -> dict:
    """体检：不算钱，只列要先问的、要停下转律师的、要特别注意的、时效。"""
    questions: list[dict] = []

    def ask(q: str, why: str) -> None:
        questions.append({"问": q, "为什么": why})

    stops = [STOP_FLAGS[k] for k in STOP_FLAGS if k in flags]
    cautions = [CAUTION_FLAGS[k] for k in CAUTION_FLAGS if k in flags]
    if not entry:
        ask("入职（实际开始上班）是哪天", "工作年限从用工之日算，决定 N 是几个月、二倍工资从哪天起")
    if not leave:
        ask("离职（被解除、合同终止）是哪天", "工作年限算到这天，一年仲裁时效也从这天起算")
    code = reason_code(reason)
    if code in (None, "unknown"):
        ask("是谁提出解除的、单位给的理由是什么（解除通知、离职证明或聊天记录上怎么写的）；你签过协商解除协议或辞职信没有",
            "离职方式决定是 0、N、N+1 还是 2N，差别最大；没问清之前只能列对比，不能下结论")
    if not has_wage:
        ask("离职前 12 个月每月税前应发多少（工资条或银行流水上的数）；含不含绩效、提成、年终奖、补贴",
            "经济补偿的月工资是应得工资，奖金津贴补贴都要算进去，只报基本工资会少算")
    if not city and avg_wage in (None, ""):
        ask("在哪个城市上班（劳动合同履行地）",
            "月工资超过当地上年度职工月平均工资 3 倍时要封顶、年限最多算 12 年；仲裁也找这个地方的仲裁委")
    if contract in (None, ""):
        ask("签没签书面劳动合同；签了的话是入职一个月内签的，还是后来补签的（哪天）",
            "入职超过一个月没签，可以要二倍工资差额，最多 11 个月")
    if code in ("misconduct", "probation_fail"):
        ask("单位说你违反了哪条规章制度（或不符合哪条录用条件），那份制度或录用条件你签收过没有，单位有没有证据",
            "单位举不出证据或制度没公示，就是违法解除，按 2N 算；理由成立的话一分不赔")
    if code == "objective" and notice in (None, "", "未知"):
        ask("单位有没有提前 30 天书面通知你", "没提前通知要多付一个月工资（代通知金，就是 N+1 的 1）")
    out: dict = {"要先问的": questions, "要停下转律师的": stops, "要特别注意的": cautions}
    if leave:
        lv = dates.parse(leave, "离职日")
        deadline = dates.plus_years(lv, 1)
        left = (deadline - apply).days
        out["仲裁时效"] = {
            "离职日": lv.isoformat(), "一般截止日": deadline.isoformat(), "按哪天判": apply.isoformat(),
            "状态": "已过" if left < 0 else ("临近（30天内）" if left <= 30 else "未过"),
            "剩余天数": left,
            "依据": "《中华人民共和国劳动争议调解仲裁法》第二十七条：时效一年，从知道或应当知道权利被侵害之日起算；向单位主张、向有关部门求助、单位同意履行的，时效中断，重新算一年",
        }
        if left < 0:
            questions.insert(0, {"问": "离职后这一年里有没有书面找单位要过钱、投诉到劳动监察或 12345、或单位答应过付钱（有记录的）",
                                 "为什么": "这些会让时效中断、从那天重新算一年；都没有的话超过一年的请求基本会被驳回（存疑：是否中断以当地劳动人事争议仲裁委员会认定为准）"})
    return out
