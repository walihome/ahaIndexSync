```

---

## 未来加新抓取器只需两步

1. 新建 `scrapers/xxx/yyy.py` 实现 `fetch()`
2. 在 `main.py` 的 `SCRAPERS` 列表加一行

Actions 的 workflow 文件**完全不用动**，入口永远是 `python main.py`。

---

## 目录结构最终全貌
```
.
├── main.py
├── requirements.txt
├── .github/
│   └── workflows/
│       └── daily.yml          # 你现有的 Actions，不用改
└── scrapers/
    ├── __init__.py
    ├── base.py                # RawItem 数据类 + BaseScraper 基类
    ├── db.py                  # 所有写库 + AI 加工逻辑
    ├── github/
    │   ├── __init__.py
    │   ├── trending.py
    │   └── search.py
    ├── ai_blogs/
    │   ├── __init__.py
    │   ├── openai.py
    │   └── anthropic.py
    ├── news/
    │   ├── __init__.py
    │   └── hackernews.py
    └── social/
        ├── __init__.py
        └── twitter.py
