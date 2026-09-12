"""生成模块：默认调用本地 Ollama（qwen2.5:7b），支持 mock 离线返回。"""
import json
import urllib.request


def generate(prompt: str, model: str = "qwen2.5:7b",
             base_url: str = "http://localhost:11434", mock: bool = True) -> str:
    if mock:
        return (
            f"[MOCK 生成 · 模型={model}]\n"
            f"基于检索到的政策片段生成结构化预审结论：\n"
            f"1) 材料完整性核对；2) 诊断标准比对；3) 待遇类别建议。\n"
            f"（接入真实 Ollama 后将输出模型推理结果）"
        )
    payload = {"model": model, "prompt": prompt, "stream": False}
    req = urllib.request.Request(
        base_url + "/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))["response"]
