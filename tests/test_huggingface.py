# tests/test_huggingface.py

import unittest
from unittest.mock import patch, MagicMock
from scrapers.huggingface import HuggingFacePapersEngine, HuggingFaceModelsEngine


def _mock_response(data, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    return resp


# ── Daily Papers Tests ────────────────────────────────────────

class TestHFPapersFieldMapping(unittest.TestCase):

    @patch("scrapers.huggingface.requests.get")
    def test_basic_field_mapping(self, mock_get):
        mock_get.return_value = _mock_response([
            {
                "paper": {
                    "id": "2410.12345",
                    "title": "Scaling Laws for Neural Networks",
                    "summary": "We study scaling laws...",
                    "publishedAt": "2024-10-15T00:00:00.000Z",
                    "upvotes": 42,
                    "authors": [
                        {"name": "Alice Smith"},
                        {"name": "Bob Jones"},
                    ],
                    "arxivId": "2410.12345",
                    "relatedModels": ["meta-llama/Llama-3"],
                    "relatedDatasets": [],
                },
                "numComments": 10,
            }
        ])

        engine = HuggingFacePapersEngine(name="HuggingFace Papers", config={
            "source_type": "ARTICLE",
            "content_type": "hf_papers",
        })
        items = engine.fetch()

        assert len(items) == 1
        item = items[0]

        assert item.title == "Scaling Laws for Neural Networks"
        assert item.original_url == "https://huggingface.co/papers/2410.12345"
        assert item.source_name == "HuggingFace Papers"
        assert item.source_type == "ARTICLE"
        assert item.content_type == "hf_papers"
        assert item.author == "Alice Smith, Bob Jones"
        assert item.body_text == "We study scaling laws..."
        assert item.raw_metrics["upvotes"] == 42
        assert item.raw_metrics["num_comments"] == 10
        assert item.extra["paper_id"] == "2410.12345"
        assert item.extra["arxiv_id"] == "2410.12345"
        assert item.extra["related_models"] == ["meta-llama/Llama-3"]
        assert item.published_at is not None

    @patch("scrapers.huggingface.requests.get")
    def test_truncates_summary_to_500(self, mock_get):
        long_summary = "A" * 1000
        mock_get.return_value = _mock_response([
            {"paper": {"id": "2410.99999", "title": "Test", "summary": long_summary, "upvotes": 10, "authors": []}, "numComments": 0}
        ])

        engine = HuggingFacePapersEngine(name="HuggingFace Papers", config={
            "source_type": "ARTICLE", "content_type": "hf_papers",
        })
        items = engine.fetch()

        assert len(items) == 1
        assert len(items[0].body_text) == 500

    @patch("scrapers.huggingface.requests.get")
    def test_many_authors_truncated(self, mock_get):
        authors = [{"name": f"Author{i}"} for i in range(10)]
        mock_get.return_value = _mock_response([
            {"paper": {"id": "2410.11111", "title": "Big Team Paper", "summary": "...", "upvotes": 5, "authors": authors}, "numComments": 0}
        ])

        engine = HuggingFacePapersEngine(name="HuggingFace Papers", config={
            "source_type": "ARTICLE", "content_type": "hf_papers",
        })
        items = engine.fetch()

        assert len(items) == 1
        assert "et al. (10)" in items[0].author
        assert items[0].author.startswith("Author0, Author1, Author2")


class TestHFPapersErrorHandling(unittest.TestCase):

    @patch("scrapers.huggingface.requests.get")
    def test_non_200_returns_empty(self, mock_get):
        mock_get.return_value = _mock_response(None, status_code=500)

        engine = HuggingFacePapersEngine(name="HuggingFace Papers", config={
            "source_type": "ARTICLE", "content_type": "hf_papers",
        })
        items = engine.fetch()
        assert items == []

    @patch("scrapers.huggingface.requests.get")
    def test_unexpected_structure_returns_empty(self, mock_get):
        mock_get.return_value = _mock_response({"unexpected": "structure"})

        engine = HuggingFacePapersEngine(name="HuggingFace Papers", config={
            "source_type": "ARTICLE", "content_type": "hf_papers",
        })
        items = engine.fetch()
        assert items == []

    @patch("scrapers.huggingface.requests.get")
    def test_empty_today_falls_back_to_yesterday(self, mock_get):
        """今天没数据时应自动尝试昨天"""
        yesterday_data = [
            {"paper": {"id": "2410.00001", "title": "Yesterday Paper", "summary": "...", "upvotes": 10, "authors": []}, "numComments": 0}
        ]
        # 第一次调用（今天）返回空，第二次（昨天）返回数据
        mock_get.side_effect = [
            _mock_response([]),
            _mock_response(yesterday_data),
        ]

        engine = HuggingFacePapersEngine(name="HuggingFace Papers", config={
            "source_type": "ARTICLE", "content_type": "hf_papers",
        })
        items = engine.fetch()

        assert len(items) == 1
        assert items[0].extra["paper_id"] == "2410.00001"


# ── Trending Models Tests ─────────────────────────────────────

class TestHFModelsFieldMapping(unittest.TestCase):

    @patch("scrapers.huggingface.requests.get")
    def test_basic_field_mapping(self, mock_get):
        mock_get.return_value = _mock_response([
            {
                "id": "meta-llama/Llama-3.1-8B",
                "author": "meta-llama",
                "pipeline_tag": "text-generation",
                "tags": ["transformers", "pytorch"],
                "downloads": 500000,
                "likes": 2000,
                "library_name": "transformers",
                "createdAt": "2024-07-01T00:00:00.000Z",
                "lastModified": "2024-10-01T00:00:00.000Z",
                "cardData": {
                    "description": "Llama 3.1 is a large language model...",
                },
            }
        ])

        engine = HuggingFaceModelsEngine(name="HuggingFace Models", config={
            "source_type": "REPO", "content_type": "hf_model",
            "min_likes": 50, "min_downloads": 1000,
        })
        items = engine.fetch()

        assert len(items) == 1
        item = items[0]

        assert item.title == "meta-llama/Llama-3.1-8B"
        assert item.original_url == "https://huggingface.co/meta-llama/Llama-3.1-8B"
        assert item.source_name == "HuggingFace Models"
        assert item.source_type == "REPO"
        assert item.content_type == "hf_model"
        assert item.author == "meta-llama"
        assert item.body_text == "Llama 3.1 is a large language model..."
        assert item.raw_metrics["likes"] == 2000
        assert item.raw_metrics["downloads"] == 500000
        assert item.extra["pipeline_tag"] == "text-generation"
        assert item.extra["library_name"] == "transformers"
        assert item.extra["tags"] == ["transformers", "pytorch"]
        assert item.published_at is not None


class TestHFModelsFiltering(unittest.TestCase):

    @patch("scrapers.huggingface.requests.get")
    def test_skip_low_likes(self, mock_get):
        mock_get.return_value = _mock_response([
            {"id": "org/model", "pipeline_tag": "text-generation", "likes": 10, "downloads": 5000, "cardData": {}, "createdAt": "2024-01-01T00:00:00Z"}
        ])

        engine = HuggingFaceModelsEngine(name="HuggingFace Models", config={
            "source_type": "REPO", "content_type": "hf_model",
            "min_likes": 50, "min_downloads": 1000,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.huggingface.requests.get")
    def test_skip_low_downloads(self, mock_get):
        mock_get.return_value = _mock_response([
            {"id": "org/model", "pipeline_tag": "text-generation", "likes": 100, "downloads": 100, "cardData": {}, "createdAt": "2024-01-01T00:00:00Z"}
        ])

        engine = HuggingFaceModelsEngine(name="HuggingFace Models", config={
            "source_type": "REPO", "content_type": "hf_model",
            "min_likes": 50, "min_downloads": 1000,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.huggingface.requests.get")
    def test_skip_empty_pipeline_tag(self, mock_get):
        mock_get.return_value = _mock_response([
            {"id": "org/model", "pipeline_tag": "", "likes": 100, "downloads": 5000, "cardData": {}, "createdAt": "2024-01-01T00:00:00Z"}
        ])

        engine = HuggingFaceModelsEngine(name="HuggingFace Models", config={
            "source_type": "REPO", "content_type": "hf_model",
            "min_likes": 50, "min_downloads": 1000,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.huggingface.requests.get")
    def test_skip_quantized_forks(self, mock_get):
        for suffix in ["-gguf", "-awq", "-gptq", "-fp8", "-int4", "-q4_0"]:
            mock_get.return_value = _mock_response([
                {"id": f"org/model{suffix}", "pipeline_tag": "text-generation", "likes": 100, "downloads": 5000, "cardData": {}, "createdAt": "2024-01-01T00:00:00Z"}
            ])
            engine = HuggingFaceModelsEngine(name="HuggingFace Models", config={
                "source_type": "REPO", "content_type": "hf_model",
                "min_likes": 50, "min_downloads": 1000,
            })
            items = engine.fetch()
            assert len(items) == 0, f"Should skip {suffix}"

    @patch("scrapers.huggingface.requests.get")
    def test_skip_derivatives(self, mock_get):
        for suffix in ["-merge", "-dpo-", "-lora-"]:
            mock_get.return_value = _mock_response([
                {"id": f"org/model{suffix}v2", "pipeline_tag": "text-generation", "likes": 100, "downloads": 5000, "cardData": {}, "createdAt": "2024-01-01T00:00:00Z"}
            ])
            engine = HuggingFaceModelsEngine(name="HuggingFace Models", config={
                "source_type": "REPO", "content_type": "hf_model",
                "min_likes": 50, "min_downloads": 1000,
            })
            items = engine.fetch()
            assert len(items) == 0, f"Should skip {suffix}"

    @patch("scrapers.huggingface.requests.get")
    def test_skip_base_model_derived(self, mock_get):
        mock_get.return_value = _mock_response([
            {"id": "org/finetuned-model", "pipeline_tag": "text-generation", "likes": 100, "downloads": 5000,
             "cardData": {"base_model": "meta-llama/Llama-3.1-8B"}, "createdAt": "2024-01-01T00:00:00Z"}
        ])

        engine = HuggingFaceModelsEngine(name="HuggingFace Models", config={
            "source_type": "REPO", "content_type": "hf_model",
            "min_likes": 50, "min_downloads": 1000,
        })
        items = engine.fetch()
        assert len(items) == 0

    @patch("scrapers.huggingface.requests.get")
    def test_keep_valid_model(self, mock_get):
        mock_get.return_value = _mock_response([
            {"id": "meta-llama/Llama-3.1-8B", "pipeline_tag": "text-generation", "likes": 2000,
             "downloads": 500000, "cardData": {"description": "..."}, "createdAt": "2024-07-01T00:00:00Z"}
        ])

        engine = HuggingFaceModelsEngine(name="HuggingFace Models", config={
            "source_type": "REPO", "content_type": "hf_model",
            "min_likes": 50, "min_downloads": 1000,
        })
        items = engine.fetch()
        assert len(items) == 1


class TestHFModelsErrorHandling(unittest.TestCase):

    @patch("scrapers.huggingface.requests.get")
    def test_non_200_returns_empty(self, mock_get):
        mock_get.return_value = _mock_response(None, status_code=429)

        engine = HuggingFaceModelsEngine(name="HuggingFace Models", config={
            "source_type": "REPO", "content_type": "hf_model",
        })
        items = engine.fetch()
        assert items == []

    @patch("scrapers.huggingface.requests.get")
    def test_network_error_returns_empty(self, mock_get):
        mock_get.side_effect = Exception("Timeout")

        engine = HuggingFaceModelsEngine(name="HuggingFace Models", config={
            "source_type": "REPO", "content_type": "hf_model",
        })
        items = engine.fetch()
        assert items == []
