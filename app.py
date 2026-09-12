"""江陵 AI 预审 · 交互 Demo（Gradio）。面试当场可玩。

运行：python app.py  （需 pip install gradio）
生成模块默认 mock；取消 generate(..., mock=False) 可接本地 Ollama qwen2.5:7b。
"""
import os
import glob
from rag_core.chunker import Chunker
from rag_core.retriever import TfidfIndex
from rag_core.reranker import Reranker
from rag_core.generator import generate

ROOT = os.path.dirname(os.path.abspath(__file__))


def _load():
    docs = {}
    for path in glob.glob(os.path.join(ROOT, "data", "policy_docs", "*.txt")):
        doc_id = os.path.splitext(os.path.basename(path))[0]
        with open(path, encoding="utf-8") as f:
            docs[doc_id] = f.read()
    return docs


docs = _load()
chunker = Chunker(size=500, overlap=50)
index = TfidfIndex()
cmap = {}
cache = {}
for doc_id, text in docs.items():
    for ch in chunker.chunk(text, doc_id):
        index.add(ch["chunk_id"], ch["text"])
        cmap[ch["chunk_id"]] = doc_id
        cache[ch["chunk_id"]] = ch["text"]
index.build()
rer = Reranker(index, alpha=0.3)


def answer(question: str):
    vec = index.search(question, topk=10)
    rk = rer.rerank(question, vec, topk=3)
    ctx = "\n".join(f"【{cmap[c[1]]}】{cache[c[1]]}" for c in rk)
    prompt = f"问题：{question}\n检索到的政策片段：\n{ctx}"
    reply = generate(prompt, mock=True)
    sources = "\n".join(f"{i+1}. [{cmap[c[1]]}] 相关度={c[0]:.3f}" for i, c in enumerate(rk))
    return reply, sources


if __name__ == "__main__":
    try:
        import gradio as gr
        demo = gr.Interface(
            fn=answer,
            inputs=gr.Textbox(label="输入慢特病政策问题",
                             placeholder="如：高血压的认定标准里收缩压要达到多少？"),
            outputs=[gr.Textbox(label="AI 预审结论（mock 生成）"),
                     gr.Textbox(label="召回来源 Top3")],
            title="江陵政务 AI 预审 Demo",
            description="本地 RAG 检索 + 重排序演示（生成模块默认 mock，可接 Ollama qwen2.5:7b）",
        )
        demo.launch()
    except ImportError:
        print("未安装 gradio，可 `pip install gradio` 后启动，或直接调用 answer()：")
        print(answer("高血压的认定标准里收缩压要达到多少？")[0])
