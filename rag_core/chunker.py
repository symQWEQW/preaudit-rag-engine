"""文档切片：支持不同粒度（字符数），用于切片策略对比实验。"""
import re


class Chunker:
    def __init__(self, size: int = 500, overlap: int = 50):
        self.size = size
        self.overlap = overlap

    def _sentences(self, text: str):
        # 按中英文句末标点断句，保留标点
        parts = re.split(r"(?<=[。！？!?；;\n])", text)
        return [p.strip() for p in parts if p.strip()]

    def chunk(self, text: str, doc_id: str, source: str = "") -> list:
        sentences = self._sentences(text)
        chunks = []
        buf = ""
        idx = 0
        for s in sentences:
            if len(buf) + len(s) <= self.size:
                buf += s
            else:
                if buf:
                    chunks.append(self._make(buf, doc_id, idx, source))
                    idx += 1
                    # 携带 overlap 尾部，增强跨句上下文
                    buf = buf[-self.overlap:] if self.overlap else ""
                if len(s) > self.size:  # 超长单句硬切
                    for i in range(0, len(s), self.size):
                        chunks.append(self._make(s[i:i + self.size], doc_id, idx, source))
                        idx += 1
                    buf = ""
                else:
                    buf = s
        if buf:
            chunks.append(self._make(buf, doc_id, idx, source))
        return chunks

    def _make(self, text: str, doc_id: str, idx: int, source: str) -> dict:
        return {
            "chunk_id": f"{doc_id}#{idx}",
            "doc_id": doc_id,
            "text": text,
            "source": source,
            "len": len(text),
        }
