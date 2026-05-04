# tests/test_product_hunt.py

import os
import unittest
from unittest.mock import patch, MagicMock
from scrapers.product_hunt import ProductHuntEngine, _yesterday_pt_range


def _make_post_node(overrides: dict) -> dict:
    """构造一个最小的 PH post node，可覆盖任意字段。"""
    base = {
        "id": "123456",
        "name": "AI Copilot",
        "tagline": "Your AI-powered coding assistant",
        "description": "A tool that helps you write code faster with AI.",
        "url": "https://www.producthunt.com/posts/ai-copilot",
        "website": "https://aicopilot.dev",
        "votesCount": 350,
        "commentsCount": 42,
        "createdAt": "2024-10-15T07:00:00Z",
        "topics": {
            "edges": [
                {"node": {"name": "Artificial Intelligence", "slug": "artificial-intelligence"}},
                {"node": {"name": "Developer Tools", "slug": "developer-tools"}},
            ]
        },
        "makers": [
            {"name": "Alice", "username": "alice"},
            {"name": "Bob", "username": "bob"},
        ],
    }
    base.update(overrides)
    return {"node": base}


def _mock_response(edges: list[dict], status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"data": {"posts": {"edges": edges}}}
    return resp


class TestPHFieldMapping(unittest.TestCase):

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_basic_field_mapping(self, mock_post):
        mock_post.return_value = _mock_response([
            _make_post_node({
                "name": "AI Copilot",
                "tagline": "Your AI coding assistant",
                "description": "Write code faster.",
                "url": "https://www.producthunt.com/posts/ai-copilot",
                "website": "https://aicopilot.dev",
                "votesCount": 350,
                "commentsCount": 42,
                "createdAt": "2024-10-15T07:00:00Z",
            })
        ])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT",
            "content_type": "product_hunt",
            "min_votes": 200,
        })
        items = engine.fetch()

        assert len(items) == 1
        item = items[0]

        assert item.title == "AI Copilot"
        assert item.original_url == "https://www.producthunt.com/posts/ai-copilot"
        assert item.source_name == "Product Hunt"
        assert item.source_type == "PRODUCT"
        assert item.content_type == "product_hunt"
        assert "Your AI coding assistant" in item.body_text
        assert "Write code faster." in item.body_text
        assert item.raw_metrics["votes"] == 350
        assert item.raw_metrics["comments"] == 42
        assert item.extra["ph_id"] == "123456"
        assert item.extra["website"] == "https://aicopilot.dev"
        assert item.extra["tagline"] == "Your AI coding assistant"
        assert "Artificial Intelligence" in item.extra["topics"]
        assert item.published_at is not None

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_makers_as_author(self, mock_post):
        mock_post.return_value = _mock_response([_make_post_node({})])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt", "min_votes": 200,
        })
        items = engine.fetch()

        assert len(items) == 1
        assert items[0].author == "Alice, Bob"

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_many_makers_truncated(self, mock_post):
        node = _make_post_node({
            "makers": [{"name": f"M{i}", "username": f"m{i}"} for i in range(10)]
        })
        mock_post.return_value = _mock_response([node])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt", "min_votes": 200,
        })
        items = engine.fetch()

        assert len(items) == 1
        assert "+7" in items[0].author

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_summary_truncated_to_500(self, mock_post):
        long_desc = "A" * 600
        mock_post.return_value = _mock_response([_make_post_node({"description": long_desc})])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt", "min_votes": 200,
        })
        items = engine.fetch()

        assert len(items) == 1
        assert len(items[0].body_text) <= 500


class TestPHFiltering(unittest.TestCase):

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_skip_low_votes(self, mock_post):
        mock_post.return_value = _mock_response([_make_post_node({"votesCount": 100})])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt", "min_votes": 200,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_skip_crypto_topics(self, mock_post):
        node = _make_post_node({
            "topics": {"edges": [
                {"node": {"name": "Crypto", "slug": "crypto"}},
                {"node": {"name": "Web3", "slug": "web3"}},
            ]},
            "votesCount": 500,
        })
        mock_post.return_value = _mock_response([node])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt", "min_votes": 200,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_skip_non_whitelisted_topics(self, mock_post):
        node = _make_post_node({
            "topics": {"edges": [
                {"node": {"name": "Fashion", "slug": "fashion"}},
                {"node": {"name": "Food", "slug": "food"}},
            ]},
            "votesCount": 500,
        })
        mock_post.return_value = _mock_response([node])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt", "min_votes": 200,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_keep_whitelisted_topic(self, mock_post):
        node = _make_post_node({
            "topics": {"edges": [
                {"node": {"name": "Artificial Intelligence", "slug": "artificial-intelligence"}},
            ]},
            "votesCount": 300,
        })
        mock_post.return_value = _mock_response([node])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt", "min_votes": 200,
        })
        items = engine.fetch()
        assert len(items) == 1

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_mixed_topics_with_whitelist(self, mock_post):
        """有白名单 topic + 非白名单 topic 应保留"""
        node = _make_post_node({
            "topics": {"edges": [
                {"node": {"name": "Artificial Intelligence", "slug": "artificial-intelligence"}},
                {"node": {"name": "Design", "slug": "design"}},
            ]},
            "votesCount": 300,
        })
        mock_post.return_value = _mock_response([node])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt", "min_votes": 200,
        })
        items = engine.fetch()
        assert len(items) == 1

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_custom_whitelist_override(self, mock_post):
        """config 中的 topic_whitelist 应覆盖默认值"""
        node = _make_post_node({
            "topics": {"edges": [{"node": {"name": "Gaming", "slug": "gaming"}}]},
            "votesCount": 300,
        })
        mock_post.return_value = _mock_response([node])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt", "min_votes": 200,
            "topic_whitelist": ["gaming"],
        })
        items = engine.fetch()
        assert len(items) == 1


class TestPHTokenHandling(unittest.TestCase):

    @patch.dict(os.environ, {}, clear=True)
    def test_no_token_returns_empty(self):
        env = {k: v for k, v in os.environ.items() if k != "PRODUCTHUNT_TOKEN"}
        with patch.dict(os.environ, env, clear=True):
            engine = ProductHuntEngine(name="Product Hunt", config={
                "source_type": "PRODUCT", "content_type": "product_hunt",
            })
            items = engine.fetch()
            assert items == []

    @patch("scrapers.product_hunt.requests.post")
    def test_config_token_overrides_env(self, mock_post):
        mock_post.return_value = _mock_response([])

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt",
            "api_token": "config-token",
        })
        engine.fetch()

        call_headers = mock_post.call_args[1].get("headers") or mock_post.call_args[0][2]
        assert call_headers["Authorization"] == "Bearer config-token"


class TestPHErrorHandling(unittest.TestCase):

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_non_200_returns_empty(self, mock_post):
        mock_post.return_value = _mock_response(None, status_code=401)

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt",
        })
        items = engine.fetch()
        assert items == []

    @patch("scrapers.product_hunt.requests.post")
    @patch.dict(os.environ, {"PRODUCTHUNT_TOKEN": "test-token"})
    def test_network_error_returns_empty(self, mock_post):
        mock_post.side_effect = Exception("Connection refused")

        engine = ProductHuntEngine(name="Product Hunt", config={
            "source_type": "PRODUCT", "content_type": "product_hunt",
        })
        items = engine.fetch()
        assert items == []


class TestPHTimezone(unittest.TestCase):

    def test_yesterday_pt_range_returns_valid_iso(self):
        start, end = _yesterday_pt_range()
        # 验证是合法 ISO 格式
        from datetime import datetime as dt
        dt.fromisoformat(start)
        dt.fromisoformat(end)
        # 验证间隔 24h
        s = dt.fromisoformat(start)
        e = dt.fromisoformat(end)
        assert (e - s).total_seconds() == 86400
