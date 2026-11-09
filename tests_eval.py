"""rag_core/eval.py 指标函数的边界测试（零依赖，python tests_eval.py 直接跑）。

覆盖需求里点名的三个边界：
1. 空 gold
2. k 大于库内 chunk 数（k > 候选数量）
3. 单文档多 chunk 的计分口径
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag_core.eval import (  # noqa: E402
    hit_rate_at_k, mrr_at_k, recall_at_k, precision_at_k,
)
from rag_core.chunker import Chunker  # noqa: E402
from rag_core.retriever import TfidfIndex  # noqa: E402

FAILED = []


def check(name, got, want, tol=1e-9):
    ok = abs(got - want) <= tol if isinstance(want, float) else got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got} want={want}")
    if not ok:
        FAILED.append(name)


def main():
    # 构造：docA 有 3 个 chunk，docB 有 1 个 chunk
    ranked = [(0.9, "A#0"), (0.8, "B#0"), (0.7, "A#1"), (0.6, "A#2")]
    gold_A = {"A#0", "A#1", "A#2"}

    print("== 1. 空 gold ==")
    check("空gold HitRate@5", hit_rate_at_k(ranked, set(), 5), 0.0)
    check("空gold Recall@5", recall_at_k(ranked, set(), 5), 0.0)
    check("空gold MRR@5", mrr_at_k(ranked, set(), 5), 0.0)
    check("空gold Precision@5", precision_at_k(ranked, set(), 5), 0.0)
    check("None gold 不崩", hit_rate_at_k(ranked, None, 5), 0.0)

    print("\n== 2. k 大于候选数 ==")
    # 只有 4 个候选，k=100：Precision 分母应按实际 4 个算，而不是 100
    check("k=100 HitRate", hit_rate_at_k(ranked, gold_A, 100), 1.0)
    check("k=100 Recall", recall_at_k(ranked, gold_A, 100), 1.0)
    check("k=100 Precision 分母取实际数", precision_at_k(ranked, gold_A, 100), 3 / 4)
    check("k=0 返回 0", hit_rate_at_k(ranked, gold_A, 0), 0.0)
    check("负数 k 返回 0", recall_at_k(ranked, gold_A, -3), 0.0)

    print("\n== 3. 单文档多 chunk 计分口径 ==")
    # gold 是整篇 A（3 个 chunk），top-2 只命中 1 个 chunk
    check("Recall@2（命中1/3）", recall_at_k(ranked, gold_A, 2), 1 / 3)
    check("HitRate@2（命中即可）", hit_rate_at_k(ranked, gold_A, 2), 1.0)
    check("Precision@2（1/2）", precision_at_k(ranked, gold_A, 2), 0.5)
    # MRR：第一个相关出现在第 1 名 → 1.0
    check("MRR@3 首位命中", mrr_at_k(ranked, gold_A, 3), 1.0)
    # 首位不相关时：gold 只有 A#1，排第 3 → 1/3
    check("MRR@3 第三位命中", mrr_at_k(ranked, {"A#1"}, 3), 1.0 / 3)
    check("MRR@2 超出窗口", mrr_at_k(ranked, {"A#1"}, 2), 0.0)

    print("\n== 4. 空候选 ==")
    check("空候选 HitRate", hit_rate_at_k([], gold_A, 5), 0.0)
    check("空候选 MRR", mrr_at_k([], gold_A, 5), 0.0)

    print("\n== 5. 真实索引冒烟（切片+检索+指标联动）==")
    idx = TfidfIndex()
    docs = {
        "docA": "高血压3级确诊。心功能II级以上且LVEDD>=6cm。",
        "docB": "糖尿病确诊。糖化血红蛋白>=6.5%。",
    }
    chunker = Chunker(size=20, overlap=5)
    cmap = {}
    for did, text in docs.items():
        for ch in chunker.chunk(text, did):
            idx.add(ch["chunk_id"], ch["text"])
            cmap[ch["chunk_id"]] = did
    idx.build()
    got = idx.search("高血压3级", topk=10)
    top_doc = cmap[got[0][1]]
    check("检索命中文档", top_doc, "docA")
    gold = {cid for cid, did in cmap.items() if did == "docA"}
    check("HitRate 可计算", hit_rate_at_k(got, gold, 3), 1.0)
    check("chunk 数大于 1", len(cmap) > 2, True)

    print("\n" + ("=" * 40))
    if FAILED:
        print(f"FAILED {len(FAILED)} 项：{FAILED}")
        return 1
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
