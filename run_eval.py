"""一键评估：切片粒度对比 + rerank 重排对比，输出真实数字。

运行：python run_eval.py
依赖：仅 Python 标准库（零 pip 安装）

v2 变更（2026-11-08，评估重建）
- 语料：data/policy_docs/*.txt（真实材料抽取）+ data/interference/*.txt（干扰文档）
- 题库：data/eval_questions_v2.json（38 题，gold 精确到具体文档）
- k：3 / 5 / 10 三档，同时报 HitRate / Recall / MRR / Precision
- 边界：空 gold、k 大于库内 chunk 数、单文档多 chunk 计分口径统一（按 chunk 级 gold 集合）
- 旧结果不覆盖：v1 的 5 篇/1473 字口径与 1.000 数字保留在 RESULTS.md「旧结果」一节
"""
import json
import os
import glob
import sys

from rag_core.chunker import Chunker
from rag_core.retriever import TfidfIndex
from rag_core.reranker import Reranker
from rag_core.eval import hit_rate_at_k, mrr_at_k, recall_at_k, precision_at_k

ROOT = os.path.dirname(os.path.abspath(__file__))
KS = (3, 5, 10)
RERANK_ALPHA = 0.3


def load_docs():
    docs, interfere = {}, {}
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "policy_docs", "*.txt"))):
        with open(path, encoding="utf-8") as f:
            docs[os.path.splitext(os.path.basename(path))[0]] = f.read()
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "interference", "*.txt"))):
        with open(path, encoding="utf-8") as f:
            interfere[os.path.splitext(os.path.basename(path))[0]] = f.read()
    return docs, interfere


def load_questions(name="eval_questions_v2.json"):
    with open(os.path.join(ROOT, "data", name), encoding="utf-8") as f:
        return json.load(f)


def build_index(all_docs, chunker):
    """返回 index 与 chunk→doc 映射；gold 以 chunk 级集合表示，单文档多 chunk 口径一致。"""
    index = TfidfIndex()
    chunk_doc = {}
    for doc_id, text in all_docs.items():
        for ch in chunker.chunk(text, doc_id):
            index.add(ch["chunk_id"], ch["text"])
            chunk_doc[ch["chunk_id"]] = doc_id
    index.build()
    return index, chunk_doc


def gold_chunks(gold_docs, chunk_doc):
    """文档级 gold 展开为 chunk 集合；gold 文档切不出 chunk 时视为空 gold。"""
    wanted = set(gold_docs)
    return {cid for cid, did in chunk_doc.items() if did in wanted}


def evaluate(questions, index, chunk_doc, rer=None):
    acc = {}
    for k in KS:
        for m in ("hit", "recall", "mrr", "precision"):
            acc[f"{m}@{k}"] = []
    rows = []
    maxk = max(KS)
    for q in questions:
        gold = gold_chunks(q["gold_docs"], chunk_doc)
        retrieved = index.search(q["question"], topk=maxk)
        if rer is not None:
            retrieved = rer.rerank(q["question"], retrieved, topk=maxk)
        row = {"id": q["id"], "type": q["type"], "question": q["question"],
               "gold_docs": q["gold_docs"], "gold_chunks": len(gold)}
        for k in KS:
            v = {
                "hit": hit_rate_at_k(retrieved, gold, k),
                "recall": recall_at_k(retrieved, gold, k),
                "mrr": mrr_at_k(retrieved, gold, k),
                "precision": precision_at_k(retrieved, gold, k),
            }
            for m, val in v.items():
                row[f"{m}@{k}"] = val
                acc[f"{m}@{k}"].append(val)
        row["top1_doc"] = chunk_doc.get(retrieved[0][1]) if retrieved else None
        rows.append(row)
    summary = {key: (sum(v) / len(v) if v else 0.0) for key, v in acc.items()}
    return summary, rows


def fmt_table(summary):
    lines = ["| 指标 | k=3 | k=5 | k=10 |", "|---|---|---|---|"]
    for name, key in (("HitRate", "hit"), ("Recall", "recall"),
                      ("MRR", "mrr"), ("Precision", "precision")):
        cells = " | ".join(f"{summary[f'{key}@{k}']:.3f}" for k in KS)
        lines.append(f"| {name} | {cells} |")
    return "\n".join(lines)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    with_interference = "--no-interference" not in argv

    docs, interfere = load_docs()
    questions = load_questions()
    corpus = dict(docs)
    if with_interference:
        corpus.update(interfere)

    total_chars = sum(len(v) for v in corpus.values())
    print("# 某地政务 AI 预审 · RAG 评估（v2 重建）\n")
    print(f"语料：{len(docs)} 篇真实材料文档 + "
          f"{len(interfere) if with_interference else 0} 篇干扰文档，合计 {total_chars} 字符")
    print(f"题库：{len(questions)} 题（{'/'.join(sorted({q['type'] for q in questions}))}）\n")

    saved = {}
    for size in (200, 300, 500):
        chunker = Chunker(size=size, overlap=int(size * 0.1))
        index, chunk_doc = build_index(corpus, chunker)
        n_chunk = len(index.docs)
        print(f"## 切片粒度 = {size} 字（{n_chunk} 个 chunk）\n")
        print(f"> k=10 时 top-10 覆盖全库 {min(10, n_chunk) / n_chunk:.0%}"
              + ("　**接近全库，指标饱和**" if n_chunk <= 12 else ""))
        print()
        summary, rows = evaluate(questions, index, chunk_doc)
        print(fmt_table(summary))
        print()

        rer = Reranker(index, alpha=RERANK_ALPHA)
        summary_rr, rows_rr = evaluate(questions, index, chunk_doc, rer)
        print(f"重排后（alpha={RERANK_ALPHA}）：\n")
        print(fmt_table(summary_rr))
        print()

        saved[size] = {"chunk_size": size, "n_chunk": n_chunk,
                       "vector": summary, "rerank": summary_rr}

        if size == 500:
            fails = [r for r in rows if r["hit@5"] == 0]
            print(f"### 未命中（HitRate@5 = 0）共 {len(fails)} 题\n")
            for r in fails:
                print(f"- `{r['id']}`（{r['type']}）{r['question']}")
                print(f"  - gold={r['gold_docs']}｜top1 落在：{r['top1_doc']}")
            print()
            with open(os.path.join(ROOT, "data", "eval_result_v2.json"), "w", encoding="utf-8") as f:
                json.dump({"summary_by_chunk_size": saved, "rows_500": rows},
                          f, ensure_ascii=False, indent=2)

    print("## 与 v1 的关系\n")
    print("- v1：语料 5 篇 / 1,473 字；200 字切片得 10 个 chunk、500 字切片仅得 5 个 chunk，")
    print("  而评估用 top-5 —— 也就是「把整个知识库全捞回来」，HitRate@5 恒等于 1.000 是算术必然。")
    print("- v2：语料扩到 %d 篇 / %d 字符并加入干扰文档，题库扩到 %d 题，k 分三档。" %
          (len(corpus), total_chars, len(questions)))
    print("- 详细对照与局限见 RESULTS.md。")


if __name__ == "__main__":
    main()
