"""一键评估：切片粒度对比 + rerank 重排对比，输出真实数字。

运行：python run_eval.py
依赖：仅 Python 标准库（零 pip 安装）。
"""
import json
import os
import glob
from rag_core.chunker import Chunker
from rag_core.retriever import TfidfIndex
from rag_core.reranker import Reranker
from rag_core.eval import hit_rate_at_k, mrr_at_k, recall_at_k

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_docs():
    docs = {}
    for path in glob.glob(os.path.join(ROOT, "data", "policy_docs", "*.txt")):
        doc_id = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            docs[doc_id] = f.read()
    return docs


def build_index(docs, chunker):
    index = TfidfIndex()
    chunk_map = {}
    for doc_id, text in docs.items():
        for ch in chunker.chunk(text, doc_id):
            index.add(ch["chunk_id"], ch["text"])
            chunk_map[ch["chunk_id"]] = doc_id
    index.build()
    return index, chunk_map


def main():
    docs = load_docs()
    with open(os.path.join(ROOT, "data", "eval_questions.json"), encoding="utf-8") as f:
        questions = json.load(f)

    print("# 江陵政务 AI 预审 · RAG 评估与切片/重排对比\n")
    print(f"政策文档数：{len(docs)}（高血压 / 糖尿病 / 恶性肿瘤）｜测试问题数：{len(questions)}\n")

    results = {}
    for size in (200, 500):
        chunker = Chunker(size=size, overlap=int(size * 0.1))
        index, cmap = build_index(docs, chunker)
        rer = Reranker(index, alpha=0.3)
        doc_chunks = {}
        for cid, did in cmap.items():
            doc_chunks.setdefault(did, []).append(cid)

        m = {k: [] for k in [
            "v5_hr", "v5_mrr", "v5_rec", "r5_hr", "r5_mrr", "r5_rec",
            "v10_hr", "v10_mrr", "v10_rec"]}
        for q in questions:
            gold = set()
            for d in q["gold_docs"]:
                gold.update(doc_chunks.get(d, []))
            vec = index.search(q["question"], topk=10)
            rk = rer.rerank(q["question"], vec, topk=5)
            m["v5_hr"].append(hit_rate_at_k(vec, gold, 5))
            m["v5_mrr"].append(mrr_at_k(vec, gold, 5))
            m["v5_rec"].append(recall_at_k(vec, gold, 5))
            m["r5_hr"].append(hit_rate_at_k(rk, gold, 5))
            m["r5_mrr"].append(mrr_at_k(rk, gold, 5))
            m["r5_rec"].append(recall_at_k(rk, gold, 5))
            m["v10_hr"].append(hit_rate_at_k(vec, gold, 10))
            m["v10_mrr"].append(mrr_at_k(vec, gold, 10))
            m["v10_rec"].append(recall_at_k(vec, gold, 10))
        avg = {k: sum(v) / len(v) for k, v in m.items()}
        results[size] = (len(index.docs), avg)
        print(f"## 切片粒度 = {size} 字（共 {len(index.docs)} 个 chunk）\n")
        print("| 检索方式 | HitRate@5 | MRR@5 | Recall@5 | HitRate@10 | MRR@10 | Recall@10 |")
        print("|---|---|---|---|---|---|---|")
        print(f"| 仅向量检索 | {avg['v5_hr']:.3f} | {avg['v5_mrr']:.3f} | {avg['v5_rec']:.3f} | "
              f"{avg['v10_hr']:.3f} | {avg['v10_mrr']:.3f} | {avg['v10_rec']:.3f} |")
        print(f"| 向量 + rerank | {avg['r5_hr']:.3f} | {avg['r5_mrr']:.3f} | {avg['r5_rec']:.3f} | - | - | - |")
        print()

    # rerank 提升示例
    print("## rerank 提升示例\n")
    chunker = Chunker(size=500, overlap=50)
    index, cmap = build_index(docs, chunker)
    rer = Reranker(index, alpha=0.3)
    q = questions[4]  # 糖尿病合并肾病
    gold = set()
    for d in q["gold_docs"]:
        gold.update(c for c, dd in cmap.items() if dd == d)
    vec = index.search(q["question"], topk=10)
    rk = rer.rerank(q["question"], vec, topk=5)
    print(f"问题：{q['question']}")
    print(f"仅向量 top5 文档：{[cmap[c[1]] for c in vec[:5]]}")
    print(f"向量+rerank top5 文档：{[cmap[c[1]] for c in rk[:5]]}")
    print(f"相关文档（gold）：{q['gold_docs']}")
    print()

    print("## 结论\n")
    for size, (nch, avg) in results.items():
        print(f"- {size} 字切片：向量召回 HitRate@5={avg['v5_hr']:.3f}，加 rerank 后={avg['r5_hr']:.3f}；"
              f"MRR@5 {avg['v5_mrr']:.3f}→{avg['r5_mrr']:.3f}")


if __name__ == "__main__":
    main()
