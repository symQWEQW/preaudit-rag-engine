"""江陵政务 AI 预审 · RAG 核心引擎（零依赖，纯标准库实现）。

设计目标：在没有 Milvus / GPU / 网络的环境下也能真实跑出 RAG 评估数字，
用于面试作品集「能讲深」的证据。生产环境可把 TfidfIndex 替换为 Milvus SDK，
接口保持一致（add / build / search）。
"""

from .chunker import Chunker
from .retriever import TfidfIndex, tokenize
from .reranker import Reranker
from .generator import generate
from .eval import hit_rate_at_k, mrr_at_k, recall_at_k

__all__ = [
    "Chunker", "TfidfIndex", "tokenize", "Reranker",
    "generate", "hit_rate_at_k", "mrr_at_k", "recall_at_k",
]
