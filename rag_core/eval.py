"""RAG 评估指标：HitRate@k / MRR@k / Recall@k / Precision@k。

定义（与 paperswithcode / BEIR 常用口径一致）：
- HitRate@k：top-k 中至少命中一个相关片段 → 1.0，否则 0.0（回答「召回到了没有」）
- MRR@k    ：第一个相关片段排名的倒数（第 1 名得 1.0，第 3 名得 1/3）；top-k 内无命中得 0.0
- Recall@k ：top-k 命中的相关片段数 / 全部相关片段数（回答「漏没漏」）
- Precision@k：top-k 命中的相关片段数 / k（回答「top-k 里有多少是噪声」）

边界约定（旧版未定义、本版显式处理并在 tests 中覆盖）：
- gold 为空集合：所有指标返回 0.0（无标准答案时不给分，而不是给满分）
- k <= 0：返回 0.0
- k > 候选数：按实际返回的候选数计算 Precision@k 的分母（不虚高原值）
- ranked 为空：全部返回 0.0

ranked 的元素为 (score, chunk_id)，与 TfidfIndex.search 的返回一致。
"""


def _top(ranked, k):
    if k <= 0 or not ranked:
        return []
    return list(ranked[:k])


def hit_rate_at_k(ranked, gold, k):
    gold = set(gold or ())
    top = _top(ranked, k)
    if not gold or not top:
        return 0.0
    return 1.0 if any(c[1] in gold for c in top) else 0.0


def mrr_at_k(ranked, gold, k):
    gold = set(gold or ())
    top = _top(ranked, k)
    if not gold:
        return 0.0
    for i, c in enumerate(top, 1):
        if c[1] in gold:
            return 1.0 / i
    return 0.0


def recall_at_k(ranked, gold, k):
    gold = set(gold or ())
    top = _top(ranked, k)
    if not gold or not top:
        return 0.0
    return len({c[1] for c in top} & gold) / len(gold)


def precision_at_k(ranked, gold, k):
    gold = set(gold or ())
    top = _top(ranked, k)
    if not gold or not top:
        return 0.0
    return len({c[1] for c in top} & gold) / len(top)


METRICS = {
    "HitRate": hit_rate_at_k,
    "MRR": mrr_at_k,
    "Recall": recall_at_k,
    "Precision": precision_at_k,
}
