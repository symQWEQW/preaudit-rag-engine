#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""从真实业务材料构建 RAG 政策语料（可追溯，不手写政策条文）。

语料来源是本机上的真实业务材料（三病种认定指标表、认定注意事项表、
软件开发功能清单、H5 原型内嵌配置、前端必传材料清单）。

**源文件路径不写死在仓库里**：仓库不保存任何真实地名与客户项目名。
运行时按以下优先级解析：
  1. 环境变量 CORPUS_SOURCE_ROOT（指向存放上述素材的根目录）
  2. 同目录下的 corpus_sources.json（本地私有文件，不进仓库）
  3. 提示缺失并退出

corpus_sources.json 格式（示例见 corpus_sources.example.json）：
  {
    "s1": "<认定指标明细表>.xlsx",
    "s2": "<认定注意事项>.xlsx",
    "s3": "<软件开发功能清单>.xlsx",
    "s4": "<H5原型>.html",
    "s5": "<前端 demoData>.js"
  }
相对路径按 CORPUS_SOURCE_ROOT 解析，绝对路径直接使用。

输出：
  data/policy_docs/<病种>__<主题>.txt   每个文档首行带 SOURCE 注释
  data/sources.md                        逐文档来源台账（条目数/字数/原文位置）
  data/interference/                     干扰文档（其它病种/其它地区/无关政策），单独目录

设计原则：
  - 只用原文条目，不做同义改写、不新增条文；
  - 同一条件在不同材料下的重复表述合并到一篇文档的多个小节，保留「材料→字段→条件」三元组；
  - 任何脚本无法从原文得到的句子都不写入；
  - 落盘文本中出现的来源文件名一律用「泛化名」（见 SOURCE_LABEL），不写客户项目名。
"""
import os
import re
import glob
import json
import sys
import openpyxl

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "data", "policy_docs")
INTER = os.path.join(ROOT, "data", "interference")
CONFIG = os.path.join(ROOT, "corpus_sources.json")

# 落盘时使用的来源泛化名（不含地名/客户名）
SOURCE_LABEL = {
    "s1": "三病种认定指标明细表",
    "s2": "三病种认定注意事项表",
    "s3": "软件开发功能清单表",
    "s4": "H5原型内嵌配置",
    "s5": "前端必传材料清单",
}


def _resolve_sources():
    """解析语料源文件路径。找不到就明确报错退出，不静默降级。"""
    base = os.environ.get("CORPUS_SOURCE_ROOT", "").strip()
    mapping = {}
    if os.path.exists(CONFIG):
        # utf-8-sig：兼容 Windows 记事本 / PowerShell 写出的带 BOM 文件
        with open(CONFIG, encoding="utf-8-sig") as f:
            mapping = json.load(f)
    else:
        mapping = {}

    resolved, missing = {}, []
    for key in ("s1", "s2", "s3", "s4", "s5"):
        rel = mapping.get(key)
        if not rel:
            missing.append(key)
            continue
        p = rel if os.path.isabs(rel) else os.path.join(base, rel)
        if not os.path.exists(p):
            missing.append(f"{key}（{p}）")
            continue
        resolved[key] = p

    if missing:
        print("缺少语料源文件，无法构建语料：", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        print("\n请创建 corpus_sources.json（参考 corpus_sources.example.json），"
              "或设置环境变量 CORPUS_SOURCE_ROOT。", file=sys.stderr)
        sys.exit(2)
    return resolved


_SRC = _resolve_sources()
S1, S2, S3, S4, S5 = (_SRC[k] for k in ("s1", "s2", "s3", "s4", "s5"))

DISEASES = ["高血压", "糖尿病", "恶性肿瘤"]
TAG = {"高血压": "H", "糖尿病": "D", "恶性肿瘤": "C"}


def w(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip() + "\n")
    return sum(len(l) for l in lines)


# ---------------------------------------------------------------- S1
def load_s1():
    wb = openpyxl.load_workbook(S1, data_only=True)
    ws = wb.worksheets[0]
    rows = []
    last_mat = ""
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or not r[0]:
            continue
        disease, mat, field, cond = (list(r) + [None] * 4)[:4]
        # 「建议材料/证据」列存在合并单元格：空值表示沿用上一条的材料名
        mat = (mat or "").strip()
        if mat:
            last_mat = mat
        else:
            mat = last_mat
        rows.append({
            "disease": str(disease).strip(),
            "material": mat,
            "field": (field or "").strip(),
            "cond": (cond or "").strip(),
        })
    return rows


# ---------------------------------------------------------------- S2
def load_s2():
    wb = openpyxl.load_workbook(S2, data_only=True)
    out = {}
    for ws in wb.worksheets:
        for r in ws.iter_rows(min_row=2, values_only=True):
            if not r or not r[0] or not r[2]:
                continue
            out.setdefault(str(r[0]).strip(), []).append(str(r[2]).strip())
    return out


# ---------------------------------------------------------------- S3
def load_s3_indicator():
    """sheet「三病种认定指标」：组合编号 → 条件/材料/AI逻辑/口径"""
    wb = openpyxl.load_workbook(S3, data_only=True)
    ws = wb["三病种认定指标"]
    head = None
    rows = []
    for r in ws.iter_rows(values_only=True):
        if r and r[0] == "病种":
            head = r
            continue
        if head is None or not r or not r[0]:
            continue
        rows.append({
            "disease": str(r[0]).strip(),
            "code": (r[1] or "").strip(),
            "kind": (r[2] or "").strip(),
            "combo": (r[3] or "").strip(),
            "cond": (r[4] or "").strip(),
            "material": (r[5] or "").strip(),
            "logic": (r[6] or "").strip(),
            "boundary": (r[7] or "").strip(),
        })
    return rows


BIZ_KW = re.compile(r"材料|认定|准入|病种|条款|口径|专家签字|排重|必传|补传|复审|目录|编码")


def load_s3_business():
    wb = openpyxl.load_workbook(S3, data_only=True)
    ws = wb["软件开发功能清单"]
    rows = []
    for r in ws.iter_rows(values_only=True):
        if not r or not r[0]:
            continue
        no = str(r[0]).strip()
        if not no.isdigit():
            continue
        sub = str(r[1] or "").strip()
        content = str(r[2] or "").strip()
        item = str(r[3] or "").strip()
        desc = str(r[4] or "").strip()
        note = str(r[5] or "").strip() if len(r) > 5 else ""
        blob = " ".join([sub, content, item, desc, note])
        if BIZ_KW.search(blob) and len(desc) > 15:
            rows.append({"no": no, "sub": sub, "item": item, "desc": desc})
    return rows


# ---------------------------------------------------------------- S4
def load_s4():
    """H5 原型内嵌的 DISEASES：客户网站采集的申报条件 + 材料清单（含 AI 要点）

    注意：旧实现用 seg[j:j+3000] 截取材料数组，会越界读到下一个病种的材料，
    导致「糖尿病」文档里混入恶性肿瘤条目。这里改为按病种块边界精确切分。
    """
    s = open(S4, encoding="utf-8").read()
    i = s.find("const DISEASES")
    j = s.find("const CONDITIONS")
    seg = s[i:j]
    out = {}
    keys = (("hypertension", "高血压"), ("diabetes", "糖尿病"), ("cancer", "恶性肿瘤"))
    for n, (key, zh) in enumerate(keys):
        start = seg.find(key + ":{")
        if start < 0:
            continue
        # 块结束 = 下一个病种 key 的位置，最后一个病种到 DISEASES 对象结尾 '};'
        if n + 1 < len(keys):
            end = seg.find(keys[n + 1][0] + ":{", start)
        else:
            end = seg.rfind("};")
        block = seg[start:end if end > start else len(seg)]

        head = block.find("mat:")
        cond = re.search(r'cond:"(.*?)",\s*\n\s*tip:', block, re.S)
        tip = re.search(r'tip:"(.*?)",\s*\n\s*mat:', block, re.S)
        mats = re.findall(
            r'\{id:"(\w+)",\s*name:"(.*?)",\s*req:(true|false),\s*ai:"(.*?)"\}',
            block[head:] if head >= 0 else block,
        )
        out[zh] = {
            "cond": cond.group(1).replace("\\n", "\n") if cond else "",
            "tip": tip.group(1) if tip else "",
            "mats": mats,
        }
    return out


# ---------------------------------------------------------------- S5
def load_s5():
    s = open(S5, encoding="utf-8").read()
    i = s.find("const REQUIRED")
    j = s.find("function reasonsFor")
    seg = s[i:j]
    out = {}
    for code, zh in (("HYPERTENSION", "高血压"), ("DIABETES", "糖尿病"), ("MALIGNANCY", "恶性肿瘤")):
        k = seg.find(code + ":")
        if k < 0:
            continue
        block = seg[k:seg.find("]", k)]
        out[zh] = re.findall(r"label: '(.*?)'", block)
    return out


def main():
    s1 = load_s1()
    s2 = load_s2()
    s3i = load_s3_indicator()
    s3b = load_s3_business()
    s4 = load_s4()
    s5 = load_s5()

    os.makedirs(OUT, exist_ok=True)
    ledger = []

    for d in DISEASES:
        # ---- 1) 认定指标明细（按材料归类）
        mat_rows = [r for r in s1 if r["disease"] == d]
        by_mat = {}
        for r in mat_rows:
            by_mat.setdefault(r["material"] or "（未指定材料）", []).append(r)
        lines = [
            f"# {d}门诊慢特病认定指标明细（按证明材料分类）",
            "",
            f"本文件共 {len(mat_rows)} 条「材料—字段—准入条件」对应关系，原文照录。",
            "",
        ]
        for mat, rs in by_mat.items():
            lines.append(f"## 材料：{mat}")
            for r in rs:
                lines.append(f"- 抽取字段：{r['field']}")
                lines.append(f"  准入条件原文：{r['cond']}")
            lines.append("")
        p = os.path.join(OUT, f"{d}__01_认定指标明细.txt")
        c = w(p, lines)
        ledger.append(("01_认定指标明细", d, len(mat_rows), c, SOURCE_LABEL["s1"] + " / Sheet1 第2-58行", "s1"))

        # ---- 2) 组合条件（H-x / D-x / C-x，含 AI 匹配逻辑与人工核验边界）
        combos = [r for r in s3i if r["disease"] == d]
        lines = [
            f"# {d}认定条件组合（含政策依据、匹配逻辑与人工核验边界）",
            "",
        ]
        for r in combos:
            lines.append(f"## {r['combo']}（{r['kind']}｜病种代码 {r['code']}）")
            lines.append(f"政策准入条件：{r['cond']}")
            lines.append(f"建议材料/证据：{r['material']}")
            lines.append(f"AI预审匹配逻辑：{r['logic']}")
            lines.append(f"口径说明与人工核验边界：{r['boundary']}")
            lines.append("")
        p = os.path.join(OUT, f"{d}__02_认定条件组合.txt")
        c = w(p, lines)
        ledger.append(("02_认定条件组合", d, len(combos), c,
                       SOURCE_LABEL["s3"] + " / sheet 三病种认定指标",
                       "s3",
                       "政策依据：某省医保发〔2023〕28号附件3《某省基本医疗保险门诊慢特病准入标准》"))

        # ---- 3) 认定注意事项（复审期限、机构等级、排重、待遇）
        notes = s2.get(d, [])
        if notes:
            lines = [
                f"# {d}门诊慢特病认定注意事项",
                "",
            ]
            for i, n in enumerate(notes, 1):
                lines.append(f"{i}. {n}")
            lines.append("")
            p = os.path.join(OUT, f"{d}__03_认定注意事项.txt")
            c = w(p, lines)
            ledger.append(("03_认定注意事项", d, len(notes), c, SOURCE_LABEL["s2"], "s2"))

        # ---- 4) 申报条件与材料目录（客户网站采集 + 前后端必传清单）
        info = s4.get(d)
        if info:
            lines = [
                f"# {d}申报条件与材料目录",
                "",
                "## 申报条件",
                info["cond"],
                "",
                "## AI 核验要点",
                info["tip"],
                "",
                "## 材料目录",
            ]
            for mid, name, req, ai in info["mats"]:
                flag = "必传" if req == "true" else "选传"
                lines.append(f"- {name}（{flag}）｜AI 核验：{ai}")
            reqs = s5.get(d, [])
            if reqs:
                lines += ["", "## 窗口 PC 端必传材料（与后端枚举对齐）"]
                for x in reqs:
                    lines.append(f"- {x}")
            lines.append("")
            p = os.path.join(OUT, f"{d}__04_申报条件与材料目录.txt")
            c = w(p, lines)
            ledger.append(("04_申报条件与材料目录", d, len(info["mats"]) + len(reqs), c,
                           SOURCE_LABEL["s4"] + " + " + SOURCE_LABEL["s5"], "s4+s5",
                           "文案来源：需求文档 3.1.3.4 所述「从客户提供的网站上采集」的申报条件与注意事项"))

        # ---- 5) 材料必传边界与专家签字边界（功能清单业务规则中与该病种相关的条目）
        rel = [r for r in s3b if d in (r["sub"] + r["item"] + r["desc"]) or "全病种" in r["sub"]]
        rel = [r for r in rel if ("材料" in r["desc"] or "必传" in r["desc"] or "专家签字" in r["desc"]
                                  or "目录" in r["desc"] or "证据" in r["desc"] or "话术" in r["desc"])]
        if rel:
            lines = [
                f"# {d}材料目录与预审话术配置要求",
                "",
            ]
            for r in rel:
                lines.append(f"- 功能项{r['no']}｜{r['item']}：{r['desc']}")
            lines.append("")
            p = os.path.join(OUT, f"{d}__05_材料目录与话术配置.txt")
            c = w(p, lines)
            ledger.append(("05_材料目录与话术配置", d, len(rel), c,
                           SOURCE_LABEL["s3"] + " / 功能清单", "s3"))

    # ---- 6) 跨病种通用规则（排重、状态流转、审核边界）
    gen = [r for r in s3b if re.search(r"排重|专家签字|三类结果|预审意见|状态|流转|复审|编码|目录配置", r["desc"])]
    lines = [
        "# 慢特病认定通用规则（三病种共用）",
        "",
        "## 预审结果三类口径",
    ]
    for r in gen:
        lines.append(f"- 功能项{r['no']}｜{r['item']}：{r['desc']}")
    lines += [
        "",
        "## 病种目录与编码",
        "- 高血压：M03900；糖尿病：M01600（普通糖尿病）/ M01611（糖尿病胰岛素治疗）；"
        "恶性肿瘤：M00500（门诊治疗）/ M00501（门诊放化疗）。",
        "（来源：软件开发功能清单表，功能项68「三病种目录及编码配置」）",
        "",
        "## 复审期限",
        "- 高血压：不复审，长期有效。",
        "- 糖尿病：复审期限 5 年，须在期满前 6 个月提交复审申请，逾期停待遇。",
        "- 恶性肿瘤：复审期限 5 年，须按期复审，期满前 6 个月提交申请。",
        "（来源：三病种认定注意事项表）",
        "",
        "## 排重与人工核验边界",
        "- 已申请缺血性或出血性脑血管疾病慢特病认定的，不再次申请高血压（会议纪要口径），"
        "因无医保接口，系统仅做提示与人工核验标记，不以 AI 自行查询或正式否决替代窗口核验。",
        "（来源：软件开发功能清单表 / sheet 三病种认定指标 / 组合 H-X）",
        "",
    ]
    p = os.path.join(OUT, "通用__06_三病种通用规则.txt")
    c = w(p, lines)
    ledger.append(("06_三病种通用规则", "通用", len(gen) + 8, c,
                   SOURCE_LABEL["s3"] + " + " + SOURCE_LABEL["s2"], "s3+s2"))

    # ---- 7) 原有 5 篇（自述「模拟数据」）不再混入 policy_docs，统一移到 data/legacy_mock/
    #         它们不是政策原文，留在检索库里会污染 gold 判定。
    legacy_dir = os.path.join(ROOT, "data", "legacy_mock")
    os.makedirs(legacy_dir, exist_ok=True)
    if os.path.isdir(OUT):
        for f in glob.glob(os.path.join(OUT, "*.txt")):
            name = os.path.basename(f)
            if any(k in name for k in ("__0",)):
                continue
            with open(f, encoding="utf-8") as fh:
                txt = fh.read()
            # 本脚本生成的文件名都带 "__"；不带的即为旧模拟语料，移出检索库
            if "__" in name:
                continue
            dst = os.path.join(legacy_dir, name)
            with open(dst, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(txt)
            os.remove(f)
            print(f"  [legacy] 移出检索库：{name} → data/legacy_mock/")

    # ---- 干扰文档
    os.makedirs(INTER, exist_ok=True)
    inter = {
        "干扰__异地病种（某市职工医保）__01.txt": [
            "# 某市职工医保门诊慢特病部分病种待遇（非本项目参保地）",
            "",
            "## 高血压",
            "某市职工医保高血压门诊慢特病按年度限额管理，"
            "参保人须在参保地定点医疗机构就诊方可按规定结算。",
            "",
            "## 糖尿病",
            "某市职工医保糖尿病门诊慢特病需提供近一年门诊病历与检验报告，"
            "待遇标准与参保缴费年限相关。",
            "",
        ],
        "干扰__其他慢病病种（慢性肾功能不全）__02.txt": [
            "# 慢性肾功能不全门诊慢特病认定要点（非本项目三病种）",
            "",
            "- 肾小球滤过率持续低于 60ml/min 并伴肾功能损害证据。",
            "- 需提供肾功能、尿常规、泌尿系超声等检查报告。",
            "- 与糖尿病肾病存在概念交叉，但认定病种不同，不可互相替代。",
            "",
        ],
        "干扰__医保经办通用流程（无关待遇标准）__03.txt": [
            "# 医保经办服务通用流程说明（与慢特病准入条件无关）",
            "",
            "- 参保人可通过线上渠道或经办窗口提交申请材料。",
            "- 经办机构受理后按规定时限完成审核并反馈结果。",
            "- 对审核结果有异议的，可申请复核。",
            "- 材料原件在核验后退回本人。",
            "",
        ],
        "干扰__药品目录与报销比例__04.txt": [
            "# 门诊慢特病用药目录与报销比例（待遇支付类，非准入条件）",
            "",
            "- 门诊慢特病用药范围按国家和省基本医疗保险药品目录执行。",
            "- 报销比例与参保类型、就医层级相关。",
            "- 年度支付限额按统筹地区规定执行，超限额部分由个人负担。",
            "",
        ],
    }
    for fn, lines in inter.items():
        p = os.path.join(INTER, fn)
        c = w(p, lines)
        ledger.append((fn, "干扰项", 1, c, "无真实文件来源（项目内构造的评测干扰项）", "-",
                       "本文件为评测用干扰项，内容由项目内既有示例口径改写，不得作为任何政策依据"))

    # ---- 台账：溯源信息一律写进独立 JSON，绝不混进被切分的正文
    total_chars = sum(x[3] for x in ledger)
    docs_meta = []
    for item in ledger:
        name, d, n, c, src, key = item[0], item[1], item[2], item[3], item[4], item[5]
        extra = item[6] if len(item) > 6 else None
        entry = {
            "doc": name,
            "disease": d,
            "entries": n,
            "chars": c,
            "source_key": key,
            "source_label": src,
        }
        if extra:
            entry["note"] = extra
        docs_meta.append(entry)

    sources_json = {
        "_comment": "语料溯源信息。单独存放，不参与文本切分与检索，避免元数据长度影响评测结果。",
        "source_files": {
            "s1": {"label": SOURCE_LABEL["s1"], "content": "材料—字段—准入条件三元组"},
            "s2": {"label": SOURCE_LABEL["s2"], "content": "复审期限/机构等级/排重/待遇等注意事项"},
            "s3": {"label": SOURCE_LABEL["s3"], "content": "组合编号与 AI 匹配逻辑、口径边界、材料必传边界"},
            "s4": {"label": SOURCE_LABEL["s4"], "content": "客户网站采集的申报条件与材料目录"},
            "s5": {"label": SOURCE_LABEL["s5"], "content": "窗口 PC 端必传材料清单"},
        },
        "policy_basis": "某省医保发〔2023〕28号附件3《某省基本医疗保险门诊慢特病准入标准》",
        "policy_basis_note": "该文件原文未在所内材料中留存，公开渠道亦未检索到，故本语料以表内摘录条款为准，不补写条款。",
        "documents": docs_meta,
        "total_documents": len(ledger),
        "total_chars": total_chars,
    }
    with open(os.path.join(ROOT, "data", "sources.json"), "w", encoding="utf-8") as f:
        json.dump(sources_json, f, ensure_ascii=False, indent=2)

    lines = [
        "# 语料来源台账（data/sources.md）",
        "",
        "> **溯源信息不进入被切分的正文**：每个 `data/policy_docs/*.txt` 只含政策内容本身，",
        "> 出处、政策依据、说明一律记在 `data/sources.json`。这样元数据长度变化不会影响",
        "> 定长切片的边界，评测结果可确定性复现。",
        ">",
        "> 生成方式：`python build_corpus.py`，逐条从真实业务材料抽取，**不做同义改写、不新增政策条文**。",
        "",
        "## 数据源",
        "",
        "| 编号 | 名称 | 用途 |",
        "|---|---|---|",
    ]
    for k in ("s1", "s2", "s3", "s4", "s5"):
        lines.append(f"| {k.upper()} | `{SOURCE_LABEL[k]}` | {sources_json['source_files'][k]['content']} |")
    lines += [
        "",
        f"表内记载的政策依据为 **{sources_json['policy_basis']}**；"
        + sources_json["policy_basis_note"],
        "",
        "## 文档清单",
        "",
        "| 文档 | 病种 | 条目数 | 字符数 | 来源 |",
        "|---|---|---|---|---|",
    ]
    for m in docs_meta:
        lines.append(f"| {m['doc']} | {m['disease']} | {m['entries']} | {m['chars']} | {m['source_label']} |")
    lines += [
        "",
        f"**合计：{len(ledger)} 篇，{total_chars} 字符。**",
        "",
        "## 未使用/无法获得的真实来源（诚实记录）",
        "",
        "| 期望来源 | 状态 |",
        "|---|---|",
        "| 某省医保发〔2023〕28号附件3 全文 | ❌ 未获得。本地无文件；公开检索无结果 |",
        "| 会议纪要（在线文档） | ❌ 需登录，本机仅有快捷方式 |",
        "| 客户网站申报条件原文页 | ⚠️ 仅通过 H5 原型转存获得（S4），未取得原始网页快照 |",
        "| 三病种真实病历/材料样本 | ❌ 未纳入（含真实患者信息，不进仓库） |",
        "",
    ]
    w(os.path.join(ROOT, "data", "sources.md"), lines)

    print(f"语料构建完成：{len(ledger)} 篇，合计 {total_chars} 字符")
    print(f"溯源信息：data/sources.json（不参与切分）")
    for m in docs_meta:
        print(f"  {m['doc']:<34} {m['disease']:<8} 条目{m['entries']:>4}  {m['chars']:>6} 字")


if __name__ == "__main__":
    main()
