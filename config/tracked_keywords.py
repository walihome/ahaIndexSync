# config/tracked_keywords.py
# 全局关键词追踪配置
# GitHub Search、HackerNews Search、Twitter 都从这里读
# 新增关注方向：加一行，不需要改任何 scraper

TRACKED_KEYWORDS = [
    # ── AI 新范式 ─────────────────────────────────────────────
    "context engineering",
    "context window",
    "MCP",                     # Model Context Protocol
    "skill",
    "agentic workflow",
    "multi-agent",

    # ── Agent 方向 ────────────────────────────────────────────
    "agent memory",
    "tool use",
    "function calling",
    "computer use",

    # ── 模型/训练 ─────────────────────────────────────────────
    "prompt caching",
    "KV cache",
    "speculative decoding",
    "fine-tuning",
    "LoRA",
    "RLHF",

    # ── 工程/框架 ─────────────────────────────────────────────
    "RAG",
    "vector database",
    "LangChain",
    "LlamaIndex",
    "DSPy",

    # ── 模型名 ───────────────────────────────────────────────
    "Claude",
    "GPT-5",
    "Gemini",
    "Llama",
    "Mistral",
    "DeepSeek",
]
