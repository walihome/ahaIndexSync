import unittest
from unittest.mock import patch

from infra.models import ContentRecord, RawItem
from stages.process import _extract_and_upload_media


class TestProcessMediaExtraction(unittest.TestCase):
    def test_repo_with_readme_images_skips_jina_readme_images(self):
        item = RawItem(
            title="bytedance/UI-TARS-desktop",
            original_url="https://github.com/bytedance/UI-TARS-desktop",
            source_name="GitHub Trending",
            source_type="REPO",
            content_type="repo",
            extra={
                "readme_images": [
                    "https://www.amazingindex.com/image/20260510/cover.png",
                ],
            },
        )
        content = ContentRecord(
            item_id=item.id,
            enriched_body=(
                "![cover](https://github.com/bytedance/UI-TARS-desktop/raw/main/images/tars.png)\n"
                "![demo](https://example.com/demo.png)"
            ),
        )

        with patch("stages.process.upload_image_to_oss") as upload:
            _extract_and_upload_media(item, content, snapshot_date="2026-05-10")

        self.assertNotIn("media_urls", item.extra)
        upload.assert_not_called()

    def test_repo_with_readme_images_preserves_body_videos(self):
        item = RawItem(
            title="repo",
            original_url="https://github.com/example/repo",
            source_name="GitHub Trending",
            source_type="REPO",
            content_type="repo",
            extra={
                "readme_images": [
                    "https://www.amazingindex.com/image/20260510/cover.png",
                ],
            },
        )
        content = ContentRecord(
            item_id=item.id,
            enriched_body=(
                "![cover](https://github.com/example/repo/raw/main/cover.png)\n"
                "![demo](https://example.com/demo.mp4)"
            ),
        )

        with patch("stages.process.upload_image_to_oss") as upload:
            _extract_and_upload_media(item, content, snapshot_date="2026-05-10")

        self.assertEqual(item.extra["media_urls"], ["https://example.com/demo.mp4"])
        upload.assert_not_called()

    def test_existing_media_urls_are_preserved_for_repo(self):
        item = RawItem(
            title="repo",
            original_url="https://github.com/example/repo",
            source_name="GitHub Search",
            source_type="REPO",
            content_type="repo",
            extra={
                "readme_images": ["https://www.amazingindex.com/image/20260510/cover.png"],
                "media_urls": ["https://example.com/demo.png"],
            },
        )
        content = ContentRecord(
            item_id=item.id,
            enriched_body="![duplicate](https://example.com/duplicate.png)",
        )

        with patch(
            "stages.process.upload_image_to_oss",
            side_effect=lambda url, date_str: f"https://oss/{date_str}/{url.rsplit('/', 1)[-1]}",
        ) as upload:
            _extract_and_upload_media(item, content, snapshot_date="2026-05-10")

        self.assertEqual(item.extra["media_urls"], ["https://oss/20260510/demo.png"])
        upload.assert_called_once_with("https://example.com/demo.png", "20260510")

    def test_non_repo_body_media_uses_snapshot_date(self):
        item = RawItem(
            title="article",
            original_url="https://example.com/article",
            source_name="Example",
            source_type="ARTICLE",
            content_type="article",
        )
        content = ContentRecord(
            item_id=item.id,
            enriched_body=(
                "![avatar](https://example.com/avatar.png)\n"
                "![chart](https://example.com/chart.png)\n"
                "![video](https://example.com/demo.mp4)"
            ),
        )

        with patch(
            "stages.process.upload_image_to_oss",
            side_effect=lambda url, date_str: f"https://oss/{date_str}/{url.rsplit('/', 1)[-1]}",
        ) as upload:
            _extract_and_upload_media(item, content, snapshot_date="2026-05-10")

        self.assertEqual(
            item.extra["media_urls"],
            ["https://oss/20260510/chart.png", "https://example.com/demo.mp4"],
        )
        upload.assert_called_once_with("https://example.com/chart.png", "20260510")


if __name__ == "__main__":
    unittest.main()
