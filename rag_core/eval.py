"""RAG 评估指标：HitRate@k / MRR@k / Recall@k。

- HitRate@k：top-k 中是否至少命中一个相关 chunk（回答「召回到了没有」）
- MRR@k    ：第一个相关 chunk 的排名倒数（回答「排得有多靠前」）
- Recall@k ：top-k 覆盖的相关 chunk 比例（多相关文档场景）
注意输入 gold 为 chunk_id 集合。
"""


def hit_rate_at_k(ranked, gold, k):
    top = {c[1] for c in ranked[:k]}
    return 1.0 if (top & set(gold)) else 0.0


def mrr_at_k(ranked, gold, k):
    gold = set(gold)
    for i, c in enumerate(ranked[:k], 1):
        if c[1] in gold:
            return 1.0 / i
    return 0.0


def recall_at_k(ranked, gold, k):
    top = {c[1] for c in ranked[:k]}
    gold = set(gold)
    if not gold:
        return 0.0
    return len(top & gold) / len(gold)
