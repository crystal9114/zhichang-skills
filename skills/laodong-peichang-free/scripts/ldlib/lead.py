"""【回答开头照抄】和【还要问（逐条照抄）】两段：派遣、外包、境外、调岗降薪、年限零头说不准这几种情形，
回答第一段该说什么、要单独问哪几个问题，都由脚本打成整句，答题时原样贴，不改写成金额结论。"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .model import fmt

NEXT = ("首要下一步：带上劳动合同、工资流水和解除或退回的通知，先找律师或当地劳动人事争议仲裁委员会窗口核定"
        "（也可以拨 12348 法律援助热线），劳动仲裁不收费。")


@dataclass
class Lead:
    lines: list[str] = field(default_factory=list)      # 回答开头照抄
    asks: list[str] = field(default_factory=list)       # 还要问（逐条照抄），每条只问一件事

    def add_ask(self, q: str) -> None:
        if q not in self.asks:
            self.asks.append(q)

    def __bool__(self) -> bool:
        return bool(self.lines or self.asks)


def _range(n_amt: Decimal | None, dn_amt: Decimal | None) -> str:
    if n_amt is None or dn_amt is None:
        return ("能赔多少现在只能给算法、不出金额：经济补偿 N = 月工资 × 年限折算的月数，"
                "单位违法解除的 2N 是它的两倍；给了月工资和年限，也只能按普通劳动关系粗算一个区间，不是结论。")
    return (f"按普通劳动关系粗算只能给一个区间：经济补偿 N 约 {fmt(n_amt)} 元到违法解除赔偿金 2N 约 {fmt(dn_amt)} 元，"
            "只当参考，不是结论，金额以律师或劳动人事争议仲裁委员会核定为准。")


def build(flags: set[str], *, n_amt: Decimal | None = None, dn_amt: Decimal | None = None,
          base: Decimal | None = None, capped: bool = False, years_fuzzy: int | None = None,
          entry_guessed: bool = False, leave_guessed: bool = False, reason_known: bool = True,
          reason: str = "", protected_hit: str = "") -> Lead:
    ld = Lead()
    if "criminal" in flags:
        ld.lines.append("刑事部分不在本技能范围：构不构成犯罪、会不会被追究、判多少，由公安机关、检察院、法院认定，本技能不替你下结论，"
                        "也不预测个案结果。刑事这一块请找刑事律师，或者向公安机关、劳动监察部门反映。")
        ld.lines.append("如果是你想告老板拒不支付劳动报酬罪：《中华人民共和国刑法》第二百七十六条之一规定，一般要先经政府有关部门责令支付、"
                        "逾期仍不支付的才追究刑事责任；拖欠的工资可以同时申请劳动仲裁（劳动合同履行地或单位所在地的劳动人事争议仲裁委员会，"
                        "不收费）或者向劳动监察部门投诉追讨，和刑事报案不冲突。")
        ld.lines.append("如果是单位报警指控你（比如职务侵占）又把你开除：劳动赔偿这一块和刑事分开看，取决于单位的解除理由能不能成立，"
                        "解除是否合法由单位承担举证责任（《最高人民法院关于审理劳动争议案件适用法律问题的解释（一）》（法释〔2020〕26号）"
                        "第四十四条）；单位拿不出证据的属于违法解除，可以主张 2N，入职日、离职日、工资给齐了可以照常算。")
        ld.add_ask("是你想告单位（比如欠薪不给），还是单位报警指控你（比如职务侵占）？")
        ld.add_ask("单位有没有书面解除通知？上面写的解除理由是什么？")
        ld.add_ask("入职日和离职日各是哪天？")
        ld.add_ask("离职前 12 个月每月税前应发多少（欠薪的话：一共欠了几个月、每月应发多少）？")
    if protected_hit and n_amt is not None and dn_amt is not None:
        who = {"pregnant": "女职工在孕期、产期、哺乳期", "medical_period": "患病或非因工负伤、还在医疗期内",
               "near_retire_15y": "在本单位连续工作满 15 年、离法定退休年龄不足 5 年"}.get(protected_hit, "属于第四十二条保护的情形")
        ld.lines.append(f"{who}的，单位不得依第四十条、第四十一条解除"
                        "（《中华人民共和国劳动合同法》第四十二条）；单位以部门撤销、客观情况变化、裁员这类理由解除或到期终止的，属于违法解除，"
                        f"你可以二选一：主张违法解除赔偿金 2N {fmt(dn_amt)} 元，或者要求继续履行劳动合同、回去上班"
                        f"（《中华人民共和国劳动合同法》第四十八条）。公司只给 N {fmt(n_amt)} 元不算合法了结。")
    if reason in ("misconduct", "probation_fail") and dn_amt is not None:
        why = "严重违纪" if reason == "misconduct" else "试用期不符合录用条件"
        ld.lines.append(f"单位以{why}解除：理由和证据都成立的，单位可以不给经济补偿；不成立的属于违法解除，可以主张 2N {fmt(dn_amt)} 元，"
                        "但这不是一定能拿到的数。解除是否合法由单位承担举证责任（《最高人民法院关于审理劳动争议案件适用法律问题的解释（一）》"
                        "（法释〔2020〕26号）第四十四条）：单位要拿出你违反的制度、制度经过公示或你签收、违纪事实的证据。")
        ld.add_ask("单位说你违反了哪一条规章制度（或哪一条录用条件）？")
        ld.add_ask("那份规章制度有没有公示过、你有没有签收过？")
        ld.add_ask("单位手里有什么证据（考勤、监控、书面警告、你签过字的材料）？")
    stop = flags & {"overseas", "dispatch", "outsourcing"}
    fuzzy = years_fuzzy is not None and base is not None
    if fuzzy and not reason_known and not stop and "transfer" not in flags:
        ld.lines.append("离职方式还没问清，先不下结论：N+1 只在单位依《中华人民共和国劳动合同法》第四十条解除（不能胜任、医疗期满、"
                        "客观情况重大变化）、又没提前 30 天书面通知时才有；单位提出协商解除、裁员、合同到期不续一般是 N；"
                        "单位拿不出合法理由和证据的违法解除才是 2N；自己辞职一般是 0。")
        ld.add_ask("是谁提出解除的？单位给的理由是什么（解除通知、聊天记录上怎么写的）？")
        ld.add_ask("单位有没有提前 30 天书面通知你？")
    if "overseas" in flags:
        ld.lines.append("本技能只按中国大陆劳动法测算。境外用工先要分清用人单位是谁、适用哪国法律：劳动合同是和国内公司签、"
                        "由国内公司外派出去的，一般可以按中国法向国内公司主张；由境外公司直接签约雇佣、辞退的，多按当地法律处理，"
                        "不在本技能测算范围。首要建议：先找熟悉涉外劳动的律师看劳动合同和外派协议"
                        "（国内公司外派的，也可以到国内公司所在地的劳动人事争议仲裁委员会咨询）。")
        ld.add_ask("你的劳动合同是和国内公司签的，还是和境外公司签的？有没有外派协议？")
        ld.add_ask("在境外工作期间，工资是哪家公司发的？国内社保有没有继续交？")
        ld.add_ask("辞退你的是哪家公司？有没有书面辞退通知，写的什么理由？")
    if "dispatch" in flags:
        ld.lines.append("劳务派遣不能直接按普通辞退算出确定金额：你的劳动合同在派遣单位（派遣公司），赔偿一般向派遣单位主张；"
                        "用工单位给你造成损害的，派遣单位和用工单位承担连带责任，申请仲裁时两家都列为被申请人"
                        "（《中华人民共和国劳动合同法》第九十二条第二款）。被退回后派遣单位没安排新岗位的，无工作期间派遣单位要按"
                        "当地最低工资标准按月给你发报酬（《中华人民共和国劳动合同法》第五十八条第二款）。")
        ld.add_ask("你的劳动合同是和派遣公司签的吗？合同上写的用人单位是哪家？")
        ld.add_ask("派遣公司是书面通知和你解除劳动合同了，还是只让你回家待岗？有书面通知的话写的什么理由？")
        ld.add_ask("被退回以后，派遣公司有没有按月给你发钱？发了多少？")
    if "outsourcing" in flags:
        ld.lines.append("外包驻场不能直接按普通辞退给出确定金额：先要分清你和谁签的劳动合同、谁发工资、谁交社保；"
                        "一般向和你签劳动合同的外包公司主张，不是向甲方。甲方项目结束本身不是外包公司解除你的法定理由，"
                        "外包公司按哪一条解除、名为外包实为派遣的，都要另判。")
        ld.add_ask("你的劳动合同是和哪家公司签的？")
        ld.add_ask("工资是哪家公司发的（看银行流水上的付款方）？")
        ld.add_ask("社保是哪家公司交的？")
        ld.add_ask("外包公司有没有书面通知和你解除劳动合同？写的什么理由？还是只是不派活、不管你？")
    if stop:
        rng = _range(n_amt, dn_amt)
        if stop == {"overseas"}:
            rng = "如果最后认定可以按中国法向国内公司主张，" + rng
        ld.lines.append(rng)
        if stop - {"overseas"}:
            ld.lines.append(NEXT)
    if "transfer" in flags:
        ld.lines.append("先别急着辞职：自己辞职一般没有经济补偿。只有单位欠薪、未足额缴纳社保、未按劳动合同约定提供劳动保护或劳动条件"
                        "等《中华人民共和国劳动合同法》第三十八条情形，你以此为理由书面通知单位解除，才能要经济补偿 N"
                        "（《中华人民共和国劳动合同法》第四十六条）；单方调岗降薪算不算没按约定提供劳动条件，各地认定不一，"
                        "以当地劳动人事争议仲裁委员会的口径为准。辞职信不要写「个人原因」，先把调岗通知、工资条、社保缴费记录、聊天记录留好再决定。")
        if n_amt is not None and not stop:
            ld.lines.append(f"按你说的年限和工资：自己辞职是 0 元；如果有上面的第三十八条情形并以此书面解除，经济补偿 N 是 {fmt(n_amt)} 元。")
        ld.add_ask("调岗以后工资有没有降？降了多少？")
        ld.add_ask("调岗有没有书面通知？劳动合同里约定的岗位和工作地点是什么？")
        ld.add_ask("单位有没有拖欠或克扣过你的工资？")
        ld.add_ask("单位有没有按你的实际工资足额交社保（有没有少交、断交）？")
    if fuzzy:
        lo, hi = Decimal(years_fuzzy) + Decimal("0.5"), Decimal(years_fuzzy + 1)
        if capped:
            lo, hi = min(lo, Decimal(12)), min(hi, Decimal(12))
        mt = (lambda m: f"{m:.1f}".rstrip("0").rstrip("."))
        ld.lines.append(f"你说的是大约「{years_fuzzy} 年多」，零头决定经济补偿 N 是几个月：零头不满 6 个月按 {mt(lo)} 个月，"
                        f"满 6 个月按 {mt(hi)} 个月（《中华人民共和国劳动合同法》第四十七条）；按月工资基数 {fmt(base)} 元，"
                        f"N 是 {fmt(base * lo)} 元或 {fmt(base * hi)} 元，N+1、2N 跟着变。下面的金额都是按假设估，不是结论，"
                        "要你给准确的入职日、离职日才能定。")
    if entry_guessed or years_fuzzy is not None:
        ld.add_ask("准确的入职日是哪天（实际开始上班那天，看劳动合同、入职登记或第一笔工资）？")
    if (leave_guessed or entry_guessed or years_fuzzy is not None) and "transfer" not in flags:
        ld.add_ask("准确的离职日是哪天（单位通知解除、或你最后上班的那天）？")
    return ld


def general(ld: Lead, *, conclusion: str, notes: list[str], limitation: str, barred: bool) -> None:
    """离职方式已问清、照常算的：结论整句、结论补充、时效句也由脚本打，放在特殊情形的句子后面。"""
    if conclusion:
        ld.lines.append(conclusion)
    ld.lines.extend(notes)
    if limitation:
        ld.lines.append(f"仲裁时效：{limitation}（《中华人民共和国劳动争议调解仲裁法》第二十七条）。")
    if barred:
        ld.lines.append("时效可以中断：离职后向单位书面要过钱、投诉到劳动监察或 12345、或者单位答应过付钱的，从那天起重新计算一年"
                        "（《中华人民共和国劳动争议调解仲裁法》第二十七条第二款），是否中断以当地劳动人事争议仲裁委员会认定为准。")
        ld.add_ask("离职后这一年里，有没有书面找单位要过钱、投诉到劳动监察或 12345、或者单位答应过付钱（有聊天记录、短信、邮件的）？")


def text(ld: Lead) -> list[str]:
    out: list[str] = []
    if ld.lines:
        out += ["## 【回答开头照抄】（原样放在回答第一段，前面不加话，不改写、不删句子）"] + [f"> {s}" for s in ld.lines] + [""]
    if ld.asks:
        out += ["## 【还要问（逐条照抄）】（每条单独问，不合并成一问，不挪进行动清单）"]
        out += [f"{i}. {q}" for i, q in enumerate(ld.asks, 1)] + [""]
    return out


def as_json(ld: Lead) -> dict:
    return {"回答开头照抄": ld.lines, "还要问（逐条照抄）": ld.asks}
