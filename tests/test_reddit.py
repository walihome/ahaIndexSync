# tests/test_reddit.py

import json
import unittest
from unittest.mock import patch, MagicMock
from scrapers.reddit import RedditEngine


def _make_post(overrides: dict) -> dict:
    """构造一个最小的 Reddit post data，可覆盖任意字段。"""
    base = {
        "title": "Test Post",
        "selftext": "This is a long enough selftext content that should pass the 200 character filter. " * 3,
        "permalink": "/r/LocalLLaMA/comments/abc123/test_post/",
        "score": 100,
        "num_comments": 20,
        "created_utc": 1700000000,
        "author": "testuser",
        "over_18": False,
        "stickied": False,
        "link_flair_text": "",
        "is_self": True,
        "url": "https://www.reddit.com/r/LocalLLaMA/comments/abc123/test_post/",
        "id": "abc123",
        "upvote_ratio": 0.95,
        "domain": "self.LocalLLaMA",
    }
    base.update(overrides)
    return {"data": base}


def _mock_response(posts: list[dict], status_code: int = 200) -> MagicMock:
    """构造 mock 的 requests.Response"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"data": {"children": posts}}
    return resp


class TestRedditFieldMapping(unittest.TestCase):
    """验证字段映射正确。"""

    @patch("scrapers.reddit.requests.get")
    def test_basic_field_mapping(self, mock_get):
        mock_get.return_value = _mock_response([
            _make_post({
                "title": "New LLM Framework Released",
                "selftext": "Check out this amazing framework. " * 10,
                "permalink": "/r/LocalLLaMA/comments/xyz789/new_llm/",
                "score": 200,
                "num_comments": 50,
                "created_utc": 1700000000,
                "author": "ai_researcher",
                "is_self": True,
                "id": "xyz789",
            })
        ])

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
        })
        items = engine.fetch()

        assert len(items) == 1
        item = items[0]

        assert item.title == "New LLM Framework Released"
        assert item.original_url == "https://reddit.com/r/LocalLLaMA/comments/xyz789/new_llm/"
        assert item.source_name == "Reddit r/LocalLLaMA"
        assert item.source_type == "NEWS"
        assert item.content_type == "reddit"
        assert item.author == "ai_researcher"
        assert item.author_url == "https://reddit.com/user/ai_researcher"
        assert item.raw_metrics["score"] == 200
        assert item.raw_metrics["comments"] == 50
        assert item.extra["subreddit"] == "LocalLLaMA"
        assert item.extra["post_id"] == "xyz789"
        assert item.extra["is_self"] is True
        assert item.published_at is not None

    @patch("scrapers.reddit.requests.get")
    def test_external_link_post_summary(self, mock_get):
        """外链帖的 summary 应为 title + domain"""
        mock_get.return_value = _mock_response([
            _make_post({
                "title": "Great AI Article",
                "is_self": False,
                "url": "https://example.com/ai-article",
                "domain": "example.com",
                "score": 100,
                "selftext": "",
            })
        ])

        engine = RedditEngine(name="Reddit r/MachineLearning", config={
            "subreddit": "MachineLearning",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
        })
        items = engine.fetch()

        assert len(items) == 1
        assert items[0].body_text == "Great AI Article · example.com"
        assert items[0].extra["external_url"] == "https://example.com/ai-article"

    @patch("scrapers.reddit.requests.get")
    def test_selftext_truncated_to_500(self, mock_get):
        long_text = "A" * 1000
        mock_get.return_value = _mock_response([
            _make_post({"selftext": long_text, "is_self": True, "score": 100})
        ])

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
        })
        items = engine.fetch()

        assert len(items) == 1
        assert len(items[0].body_text) == 500


class TestRedditFiltering(unittest.TestCase):
    """验证过滤规则。"""

    @patch("scrapers.reddit.requests.get")
    def test_skip_nsfw(self, mock_get):
        mock_get.return_value = _mock_response([
            _make_post({"over_18": True, "score": 500}),
        ])

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
            "skip_nsfw": True,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.reddit.requests.get")
    def test_skip_stickied(self, mock_get):
        mock_get.return_value = _mock_response([
            _make_post({"stickied": True, "score": 500}),
        ])

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
            "skip_stickied": True,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.reddit.requests.get")
    def test_skip_low_score(self, mock_get):
        mock_get.return_value = _mock_response([
            _make_post({"score": 30}),
        ])

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.reddit.requests.get")
    def test_skip_discussion_flair_low_score(self, mock_get):
        """Discussion flair + score < 100 应跳过"""
        mock_get.return_value = _mock_response([
            _make_post({"link_flair_text": "Discussion", "score": 80}),
        ])

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
            "skip_discussion_below": 100,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.reddit.requests.get")
    def test_keep_discussion_flair_high_score(self, mock_get):
        """Discussion flair + score >= 100 应保留"""
        mock_get.return_value = _mock_response([
            _make_post({"link_flair_text": "Discussion", "score": 150}),
        ])

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
            "skip_discussion_below": 100,
        })
        items = engine.fetch()
        assert len(items) == 1

    @patch("scrapers.reddit.requests.get")
    def test_skip_short_self_post(self, mock_get):
        mock_get.return_value = _mock_response([
            _make_post({"is_self": True, "selftext": "too short", "score": 100}),
        ])

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
            "skip_self_text_below": 200,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.reddit.requests.get")
    def test_external_post_not_skipped_by_selftext(self, mock_get):
        """外链帖不应被 selftext 长度过滤"""
        mock_get.return_value = _mock_response([
            _make_post({"is_self": False, "selftext": "", "score": 100, "domain": "example.com"}),
        ])

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
            "skip_self_text_below": 200,
        })
        items = engine.fetch()
        assert len(items) == 1


class TestRedditErrorHandling(unittest.TestCase):
    """验证错误处理。"""

    @patch("scrapers.reddit.requests.get")
    def test_non_200_returns_empty(self, mock_get):
        mock_get.return_value = _mock_response([], status_code=403)

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
        })
        items = engine.fetch()
        assert items == []

    @patch("scrapers.reddit.requests.get")
    def test_network_error_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("Connection refused")

        engine = RedditEngine(name="Reddit r/LocalLLaMA", config={
            "subreddit": "LocalLLaMA",
            "source_type": "NEWS",
            "content_type": "reddit",
            "min_score": 50,
        })
        items = engine.fetch()
        assert items == []
