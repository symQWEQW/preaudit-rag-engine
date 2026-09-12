"""TF-IDF 向量检索（零依赖）。生产环境可替换为 Milvus 向量检索，接口对齐。"""
import re
import math
from collections import Counter


def tokenize(text: str):
    """中文：字符 + 字符 bigram；英文/数字：小写词。零依赖中文分词近似。"""
    text = (text or "").lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    for seg in re.findall(r"[一-鿿]+", text):
        chars = list(seg)
        tokens.extend("c_" + c for c in chars)
        for i in range(len(chars) - 1):
            tokens.append("b_" + chars[i] + chars[i + 1])
    return tokens


class TfidfIndex:
    def __init__(self):
        self.docs = {}      # chunk_id -> tf(Counter)
        self.df = Counter()
        self.N = 0
        self.idf = {}

    def add(self, cid: str, text: str):
        tf = Counter(tokenize(text))
        self.docs[cid] = tf
        for t in tf:
            self.df[t] += 1
        self.N += 1

    def build(self):
        for t, df in self.df.items():
            # 平滑 IDF
            self.idf[t] = math.log((self.N - df + 0.5) / (df + 0.5) + 1.0) + 1.0

    def _vec(self, tf: Counter):
        return {t: (1.0 + math.log(tf[t])) * self.idf.get(t, 0.0) for t in tf}

    @staticmethod
    def _norm(vec):
        return math.sqrt(sum(v * v for v in vec.values()))

    def search(self, query: str, topk: int = 10):
        qvec = self._vec(Counter(tokenize(query)))
        ql = self._norm(qvec) or 1.0
        scored = []
        for cid, tf in self.docs.items():
            dvec = self._vec(tf)
            dl = self._norm(dvec) or 1.0
            dot = sum(qvec.get(t, 0.0) * dvec.get(t, 0.0) for t in qvec)
            cos = dot / (ql * dl)
            scored.append((cos, cid))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:topk]
