"""Rerank 重排序：在向量召回 top-N 之后，用「向量分 + BM25 交互分」加权重排。

为什么需要 rerank：
向量检索（ANN/余弦）擅长「语义粗召」，但对关键词精确匹配、稀有词（如病名、
药品名）容易漏召回。rerank 阶段用 cross-encoder 风格的交互特征做精排，
能显著提升 HitRate / MRR。这里用可解释的 BM25 交互作为轻量实现，
生产环境可替换为 bge-reranker-v2-m3 等 cross-encoder 模型。
"""
import math
from collections import Counter

from .retriever import tokenize


class Reranker:
    def __init__(self, index, alpha: float = 0.3):
        # alpha: 向量分权重；(1-alpha): 交互分权重
        self.index = index
        self.alpha = alpha

    def rerank(self, query: str, candidates, topk: int = 5):
        qtoks = tokenize(query)
        qtf = Counter(qtoks)
        ql = math.sqrt(len(qtoks)) or 1.0
        scored = []
        for cos, cid in candidates:
            tf = self.index.docs[cid]
            # BM25 交互项（k1=1.5, b=0.75, 文档长度近似 1）
            score = 0.0
            for t in qtoks:
                if t in tf:
                    idf = self.index.idf.get(t, 0.0)
                    f = tf[t]
                    score += idf * (f * (1.5 + 1.0)) / (f + 1.5 * (1 - 0.75 + 0.75))
            bm25 = score / ql
            final = self.alpha * cos + (1 - self.alpha) * bm25
            scored.append((final, cid))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:topk]
