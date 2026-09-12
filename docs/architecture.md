# 某地政务 AI 预审系统 · 技术架构

> 定位：面试作品集 demo（脱敏、可一键启动、能讲清技术难点）
> 现有基础：单体 Spring Boot 原型 + Dify + Ollama(qwen2.5:7b) + Vue/H5
> 改造目标：单体 → Spring Cloud 微服务；加 Redis 缓存；知识库 Dify 默认 → 自建 RAG(Milvus)；RAG 核心用可评估的 Python 引擎

---

## 架构总览

```
                ┌─────────────────────────────────────────┐
   患者 H5 ─────▶│            Spring Cloud Gateway          │  (路由 / JWT 鉴权 / 限流)
                │            (port 8080)                    │
                └───────────────┬───────────────────────────┘
                                │ 注册发现 Nacos (8848)
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
┌──────────────┐      ┌──────────────────┐      ┌──────────────────┐
│ ai-engine    │      │ preaudit-business│      │ notification-svc │
│ -service     │      │ -service         │      │ (短信/通知 mock) │
│ RAG 检索 ────┼─────▶│ 预审记录/材料缓存 │      │                  │
│ Ollama 调用  │      │ RBAC/慢特病管理   │      └──────────────────┘
└──────┬───────┘      └────────┬─────────┘
       │                       │
       ▼                       ▼
  Milvus(19530)          Redis(6379)
  向量库(生产)            缓存/限流
   └── 本地演示用 TfidfIndex 兜底
       ▼
  Ollama(11434)  qwen2.5:7b + bge-m3 嵌入
```

> **本仓库 `rag_core/`** 即 `ai-engine-service` 的 RAG 核心：切片 → 检索 → 重排 → 生成，
> 并用 `eval.py` / `run_eval.py` 提供可量化的评估能力（Recall@k / MRR / HitRate）。
> 本地演示用零依赖 TF-IDF 检索，生产环境将 `TfidfIndex` 替换为 Milvus SDK，接口保持一致。

---

## 微服务拆分

| 服务 | 职责 | 关键技术点 |
|---|---|---|
| **gateway** | 统一入口、JWT 鉴权、Sentinel 限流 | Spring Cloud Gateway |
| **ai-engine-service** | RAG 检索 + Ollama 推理 + 结构化输出 | 本仓库 rag_core（Milvus SDK / RestTemplate 调 Ollama / Prompt 模板） |
| **preaudit-business-service** | 预审记录 CRUD、材料缓存、慢特病管理、RBAC | MyBatis-Plus、Redis 缓存 |
| **notification-service** | 短信通知（demo 用日志/mock 代替真实短信） | Spring Event / Stream 消息 |
| **common** | 统一返回、异常、实体、工具 | 被 3 个服务依赖 |

---

## Redis 改造点（3 处）

1. **预审记录缓存** —— 患者查「我的预审进度」高频读，缓存 5 分钟
2. **材料缓存** —— 上传材料 hash 去重，避免重复存储（呼应 16,554 条去重经验）
3. **接口限流 / 防重复提交** —— Gateway + Redis 计数器，1 分钟同一患者限 1 次提交

---

## RAG 改造点（知识库自建）

| 步骤 | 实现 | 工具 |
|---|---|---|
| 文档切片 | 慢特病政策按 300–500 字 + 句边界切段 | `Chunker`（含 overlap） |
| 向量化 | 本地嵌入模型 | Ollama `bge-m3`（演示用 TF-IDF 兜底） |
| 存储 | 向量库 | Milvus（演示用 `TfidfIndex` 兜底） |
| 召回 | 相似度 top-k | Milvus `search()` / `TfidfIndex.search()` |
| 重排 | cross-encoder 精排 | `Reranker`（预留 bge-reranker 接入） |
| 生成 | 大模型推理 | Ollama `qwen2.5:7b` |

---

## 面试能讲清的 3 个难点（背熟）

1. **为什么用 Spring Cloud 而不是继续单体** —— 预审/AI/通知解耦，AI 引擎可独立扩缩容
2. **RAG 召回不准怎么调** —— 切片粒度（实验已验证 500 字优于 200 字）、top-k、重排序（rerank）
3. **Redis 缓存一致性** —— 材料更新时删缓存（Cache-Aside），避免脏读

---

*关联：本项目隶属于「AI 应用落地工程师」作品集，同类项目与面试口径详见作品集仓库 README。*
