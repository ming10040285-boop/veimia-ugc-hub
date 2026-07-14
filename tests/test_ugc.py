"""Unit tests for the UGC Gallery Management API endpoint.

Tests Instagram URL validation, gallery limit enforcement, add/remove/reorder
operations, and image data validation.
"""

import base64
import json
import os
import sys
import tempfile
import shutil
import uuid
import unittest
from io import BytesIO

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.admin.ugc import (
    MAX_UGC_POSTS,
    MAX_IMAGE_URL_LENGTH,
    MAX_IMAGE_SIZE_BYTES,
    INSTAGRAM_URL_PATTERN,
    _validate_instagram_url,
    _validate_image_url,
    _validate_image_data,
    _get_next_display_order,
    _handle_add,
    _handle_reorder,
    _handle_remove,
)


class MockHandler:
    """Mock HTTP handler for testing endpoint handlers."""

    def __init__(self, body_dict=None, path="/api/admin/ugc", method="POST"):
        self.body_json = json.dumps(body_dict).encode("utf-8") if body_dict else b""
        self.headers = {"Content-Length": str(len(self.body_json))}
        self.rfile = BytesIO(self.body_json)
        self.path = path
        self.response_status = None
        self._headers_sent = []
        self._wfile = BytesIO()

    @property
    def wfile(self):
        return self._wfile

    def send_response(self, status):
        self.response_status = status

    def send_header(self, key, value):
        self._headers_sent.append((key, value))

    def end_headers(self):
        pass

    def get_response(self):
        """Parse the JSON response body."""
        return json.loads(self._wfile.getvalue().decode("utf-8"))


class TestInstagramUrlValidation(unittest.TestCase):
    """Tests for Instagram URL format validation."""

    def test_valid_www_instagram_url(self):
        url = "https://www.instagram.com/p/ABC123def/"
        self.assertTrue(_validate_instagram_url(url))

    def test_valid_instagram_url_without_www(self):
        url = "https://instagram.com/p/ABC123def/"
        self.assertTrue(_validate_instagram_url(url))

    def test_valid_url_without_trailing_slash(self):
        url = "https://www.instagram.com/p/ABC123def"
        self.assertTrue(_validate_instagram_url(url))

    def test_valid_url_with_query_params(self):
        url = "https://www.instagram.com/p/ABC123def/?utm_source=share"
        self.assertTrue(_validate_instagram_url(url))

    def test_valid_url_with_hyphens_and_underscores(self):
        url = "https://www.instagram.com/p/A-B_C-123/"
        self.assertTrue(_validate_instagram_url(url))

    def test_none_source_url_is_valid(self):
        """None source_url is acceptable (field is optional)."""
        self.assertTrue(_validate_instagram_url(None))

    def test_empty_string_is_valid(self):
        """Empty string source_url is acceptable."""
        self.assertTrue(_validate_instagram_url(""))

    def test_invalid_http_url(self):
        """HTTP (non-HTTPS) Instagram URL is rejected."""
        url = "http://www.instagram.com/p/ABC123/"
        self.assertFalse(_validate_instagram_url(url))

    def test_invalid_non_instagram_domain(self):
        url = "https://www.example.com/p/ABC123/"
        self.assertFalse(_validate_instagram_url(url))

    def test_invalid_instagram_profile_url(self):
        """Instagram profile URL (not /p/) is rejected."""
        url = "https://www.instagram.com/username/"
        self.assertFalse(_validate_instagram_url(url))

    def test_invalid_instagram_reel_url(self):
        """Instagram reel URL is rejected."""
        url = "https://www.instagram.com/reel/ABC123/"
        self.assertFalse(_validate_instagram_url(url))

    def test_invalid_random_string(self):
        self.assertFalse(_validate_instagram_url("not-a-url"))

    def test_invalid_missing_post_id(self):
        """URL with /p/ but no post ID is rejected."""
        url = "https://www.instagram.com/p/"
        self.assertFalse(_validate_instagram_url(url))


class TestImageUrlValidation(unittest.TestCase):
    """Tests for image URL validation."""

    def test_valid_https_url(self):
        self.assertTrue(_validate_image_url("https://cdn.example.com/image.webp"))

    def test_valid_http_url(self):
        self.assertTrue(_validate_image_url("http://cdn.example.com/image.png"))

    def test_empty_url_rejected(self):
        self.assertFalse(_validate_image_url(""))

    def test_none_url_rejected(self):
        self.assertFalse(_validate_image_url(None))

    def test_ftp_scheme_rejected(self):
        self.assertFalse(_validate_image_url("ftp://cdn.example.com/image.png"))

    def test_url_exceeding_2048_chars_rejected(self):
        long_url = "https://cdn.example.com/" + "a" * 2048
        self.assertFalse(_validate_image_url(long_url))

    def test_url_exactly_2048_chars_accepted(self):
        url = "https://cdn.example.com/" + "a" * (2048 - len("https://cdn.example.com/"))
        self.assertTrue(_validate_image_url(url))


class TestImageDataValidation(unittest.TestCase):
    """Tests for base64 image data validation."""

    def test_valid_small_image(self):
        data = base64.b64encode(b'\x89PNG' + b'\x00' * 100).decode('ascii')
        is_valid, size = _validate_image_data(data)
        self.assertTrue(is_valid)
        self.assertEqual(size, 104)

    def test_valid_data_uri_jpeg(self):
        raw = b'\xff\xd8\xff\xe0' + b'\x00' * 100
        data = "data:image/jpeg;base64," + base64.b64encode(raw).decode('ascii')
        is_valid, size = _validate_image_data(data)
        self.assertTrue(is_valid)

    def test_valid_data_uri_png(self):
        raw = b'\x89PNG' + b'\x00' * 50
        data = "data:image/png;base64," + base64.b64encode(raw).decode('ascii')
        is_valid, size = _validate_image_data(data)
        self.assertTrue(is_valid)

    def test_valid_data_uri_webp(self):
        raw = b'RIFF' + b'\x00' * 50
        data = "data:image/webp;base64," + base64.b64encode(raw).decode('ascii')
        is_valid, size = _validate_image_data(data)
        self.assertTrue(is_valid)

    def test_invalid_data_uri_gif_rejected(self):
        raw = b'GIF89a' + b'\x00' * 50
        data = "data:image/gif;base64," + base64.b64encode(raw).decode('ascii')
        is_valid, size = _validate_image_data(data)
        self.assertFalse(is_valid)

    def test_exceeds_5mb_rejected(self):
        large = b'\x00' * (MAX_IMAGE_SIZE_BYTES + 1)
        data = base64.b64encode(large).decode('ascii')
        is_valid, size = _validate_image_data(data)
        self.assertFalse(is_valid)
        self.assertGreater(size, MAX_IMAGE_SIZE_BYTES)

    def test_empty_string_rejected(self):
        is_valid, size = _validate_image_data("")
        self.assertFalse(is_valid)

    def test_none_rejected(self):
        is_valid, size = _validate_image_data(None)
        self.assertFalse(is_valid)

    def test_invalid_base64_rejected(self):
        is_valid, size = _validate_image_data("not-valid-base64!!!")
        self.assertFalse(is_valid)


class TestGetNextDisplayOrder(unittest.TestCase):
    """Tests for display order computation."""

    def test_empty_gallery(self):
        self.assertEqual(_get_next_display_order([]), 1)

    def test_one_post(self):
        gallery = [{"display_order": 1}]
        self.assertEqual(_get_next_display_order(gallery), 2)

    def test_multiple_posts(self):
        gallery = [{"display_order": 1}, {"display_order": 3}, {"display_order": 2}]
        self.assertEqual(_get_next_display_order(gallery), 4)

    def test_gap_in_orders(self):
        gallery = [{"display_order": 1}, {"display_order": 5}]
        self.assertEqual(_get_next_display_order(gallery), 6)


class TestUgcHandlerPost(unittest.TestCase):
    """Integration-style tests for the UGC POST handler (add post)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.campaign_id = str(uuid.uuid4())
        self.campaign = {
            "campaign_id": self.campaign_id,
            "campaign_name": "Test Campaign",
            "product_mode": "single",
            "market": "ko",
            "hero_image_url": "",
            "introduction_text": "",
            "status": "draft",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "products": [],
            "ugc_gallery": []
        }
        self._save_campaign(self.campaign)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _save_campaign(self, campaign):
        path = os.path.join(self.temp_dir, f"{campaign['campaign_id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(campaign, f)

    def _load_campaign(self, campaign_id):
        path = os.path.join(self.temp_dir, f"{campaign_id}.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _call_add(self, body, campaign_id=None):
        from unittest.mock import patch
        mock = MockHandler(body)
        cid = campaign_id or body.get("campaign_id", "")
        with patch('api.admin.ugc.CAMPAIGNS_DIR', self.temp_dir):
            _handle_add(mock, cid)
        return mock

    def test_add_post_with_image_url(self):
        """Successfully add a UGC post with image_url."""
        mock = self._call_add({
            "image_url": "https://cdn.example.com/image.webp",
            "source_url": "https://www.instagram.com/p/ABC123/"
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 201)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")
        self.assertIn("post_id", response["data"])
        self.assertEqual(response["data"]["display_order"], 1)
        self.assertEqual(response["data"]["image_url"], "https://cdn.example.com/image.webp")
        self.assertEqual(response["data"]["source_url"], "https://www.instagram.com/p/ABC123/")

    def test_add_post_with_image_data(self):
        """Successfully add a UGC post with base64 image data."""
        data = base64.b64encode(b'\x89PNG' + b'\x00' * 100).decode('ascii')
        mock = self._call_add({
            "image_data": data
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 201)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")
        self.assertIn("post_id", response["data"])
        self.assertTrue(response["data"]["image_url"].startswith("https://"))
        self.assertIsNone(response["data"]["source_url"])

    def test_add_post_without_source_url(self):
        """source_url is optional; null when not provided."""
        mock = self._call_add({
            "image_url": "https://cdn.example.com/image.webp"
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 201)
        response = mock.get_response()
        self.assertIsNone(response["data"]["source_url"])

    def test_gallery_limit_enforced(self):
        """Cannot add more than 20 posts to a campaign."""
        self.campaign["ugc_gallery"] = [
            {"post_id": str(uuid.uuid4()), "image_url": f"https://img.com/{i}.webp",
             "source_url": None, "display_order": i + 1}
            for i in range(20)
        ]
        self._save_campaign(self.campaign)

        mock = self._call_add({
            "image_url": "https://cdn.example.com/image21.webp"
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "GALLERY_LIMIT")
        self.assertEqual(response["message"], "UGC 갤러리는 최대 20개까지 등록 가능합니다.")

    def test_invalid_instagram_url_rejected(self):
        """Invalid Instagram URL returns INVALID_URL error."""
        mock = self._call_add({
            "image_url": "https://cdn.example.com/image.webp",
            "source_url": "https://www.facebook.com/post/123"
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "INVALID_URL")
        self.assertEqual(response["message"], "Instagram URL을 확인할 수 없습니다.")

    def test_campaign_not_found(self):
        """Non-existent campaign returns NOT_FOUND."""
        mock = self._call_add({
            "image_url": "https://cdn.example.com/image.webp"
        }, campaign_id="non-existent-id")
        self.assertEqual(mock.response_status, 404)
        response = mock.get_response()
        self.assertEqual(response["code"], "NOT_FOUND")

    def test_missing_body(self):
        """Missing body returns VALIDATION_ERROR."""
        from unittest.mock import patch
        mock = MockHandler(None)
        with patch('api.admin.ugc.CAMPAIGNS_DIR', self.temp_dir):
            _handle_add(mock, self.campaign_id)
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "VALIDATION_ERROR")

    def test_both_image_url_and_data_rejected(self):
        """Providing both image_url and image_data is rejected."""
        data = base64.b64encode(b'\x00' * 100).decode('ascii')
        mock = self._call_add({
            "image_url": "https://cdn.example.com/img.webp",
            "image_data": data
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "VALIDATION_ERROR")

    def test_neither_image_url_nor_data_rejected(self):
        """Must provide either image_url or image_data."""
        mock = self._call_add({
            "source_url": "https://www.instagram.com/p/ABC123/"
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "VALIDATION_ERROR")

    def test_display_order_increments(self):
        """Each added post gets the next display_order."""
        self.campaign["ugc_gallery"] = [
            {"post_id": "existing-1", "image_url": "https://img.com/1.webp",
             "source_url": None, "display_order": 1},
            {"post_id": "existing-2", "image_url": "https://img.com/2.webp",
             "source_url": None, "display_order": 2}
        ]
        self._save_campaign(self.campaign)

        mock = self._call_add({
            "image_url": "https://cdn.example.com/new.webp"
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 201)
        response = mock.get_response()
        self.assertEqual(response["data"]["display_order"], 3)

    def test_post_saved_to_campaign_json(self):
        """Added post is persisted in the campaign config file."""
        mock = self._call_add({
            "image_url": "https://cdn.example.com/saved.webp",
            "source_url": "https://www.instagram.com/p/XYZ789/"
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 201)

        # Verify campaign file was updated
        campaign = self._load_campaign(self.campaign_id)
        self.assertEqual(len(campaign["ugc_gallery"]), 1)
        post = campaign["ugc_gallery"][0]
        self.assertEqual(post["image_url"], "https://cdn.example.com/saved.webp")
        self.assertEqual(post["source_url"], "https://www.instagram.com/p/XYZ789/")


class TestUgcHandlerPut(unittest.TestCase):
    """Integration-style tests for the UGC PUT handler (reorder)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.campaign_id = str(uuid.uuid4())
        self.post_ids = [str(uuid.uuid4()) for _ in range(3)]
        self.campaign = {
            "campaign_id": self.campaign_id,
            "campaign_name": "Test Campaign",
            "product_mode": "single",
            "market": "ko",
            "hero_image_url": "",
            "introduction_text": "",
            "status": "draft",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "products": [],
            "ugc_gallery": [
                {"post_id": self.post_ids[0], "image_url": "https://img.com/1.webp",
                 "source_url": None, "display_order": 1},
                {"post_id": self.post_ids[1], "image_url": "https://img.com/2.webp",
                 "source_url": None, "display_order": 2},
                {"post_id": self.post_ids[2], "image_url": "https://img.com/3.webp",
                 "source_url": None, "display_order": 3}
            ]
        }
        self._save_campaign(self.campaign)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _save_campaign(self, campaign):
        path = os.path.join(self.temp_dir, f"{campaign['campaign_id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(campaign, f)

    def _load_campaign(self, campaign_id):
        path = os.path.join(self.temp_dir, f"{campaign_id}.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _call_reorder(self, body, campaign_id=None):
        from unittest.mock import patch
        mock = MockHandler(body)
        cid = campaign_id or body.get("campaign_id", "")
        with patch('api.admin.ugc.CAMPAIGNS_DIR', self.temp_dir):
            _handle_reorder(mock, cid)
        return mock

    def test_successful_reorder(self):
        """Reorder posts successfully using post_ids array."""
        mock = self._call_reorder({
            "post_ids": [self.post_ids[2], self.post_ids[0], self.post_ids[1]]
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")

        # Verify order in response
        data = response["data"]
        self.assertEqual(data[0]["post_id"], self.post_ids[2])
        self.assertEqual(data[0]["display_order"], 1)
        self.assertEqual(data[1]["post_id"], self.post_ids[0])
        self.assertEqual(data[1]["display_order"], 2)

    def test_reorder_persisted(self):
        """Reorder is saved to campaign JSON file."""
        self._call_reorder({
            "post_ids": [self.post_ids[1], self.post_ids[2], self.post_ids[0]]
        }, campaign_id=self.campaign_id)
        campaign = self._load_campaign(self.campaign_id)
        self.assertEqual(campaign["ugc_gallery"][0]["post_id"], self.post_ids[1])

    def test_invalid_post_id_rejected(self):
        """Non-existent post_id returns NOT_FOUND."""
        mock = self._call_reorder({
            "post_ids": ["nonexistent-id"]
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 404)

    def test_campaign_not_found(self):
        """Non-existent campaign returns NOT_FOUND."""
        mock = self._call_reorder({
            "post_ids": []
        }, campaign_id="non-existent")
        self.assertEqual(mock.response_status, 404)

    def test_missing_post_ids_array(self):
        """Missing orders/post_ids array returns VALIDATION_ERROR."""
        mock = self._call_reorder({}, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "VALIDATION_ERROR")

    def test_reorder_with_orders_pairs(self):
        """Reorder posts using explicit {post_id, display_order} pairs."""
        mock = self._call_reorder({
            "orders": [
                {"post_id": self.post_ids[2], "display_order": 1},
                {"post_id": self.post_ids[0], "display_order": 2},
                {"post_id": self.post_ids[1], "display_order": 3}
            ]
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")

        # Verify order in response — sorted by display_order
        data = response["data"]
        self.assertEqual(data[0]["post_id"], self.post_ids[2])
        self.assertEqual(data[0]["display_order"], 1)
        self.assertEqual(data[1]["post_id"], self.post_ids[0])
        self.assertEqual(data[1]["display_order"], 2)
        self.assertEqual(data[2]["post_id"], self.post_ids[1])
        self.assertEqual(data[2]["display_order"], 3)

    def test_reorder_with_invalid_display_order(self):
        """Invalid display_order value returns VALIDATION_ERROR."""
        mock = self._call_reorder({
            "orders": [
                {"post_id": self.post_ids[0], "display_order": 0}
            ]
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "VALIDATION_ERROR")


class TestUgcHandlerDelete(unittest.TestCase):
    """Integration-style tests for the UGC DELETE handler (remove post)."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.campaign_id = str(uuid.uuid4())
        self.post_ids = [str(uuid.uuid4()) for _ in range(3)]
        self.campaign = {
            "campaign_id": self.campaign_id,
            "campaign_name": "Test Campaign",
            "product_mode": "single",
            "market": "ko",
            "hero_image_url": "",
            "introduction_text": "",
            "status": "draft",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "products": [],
            "ugc_gallery": [
                {"post_id": self.post_ids[0], "image_url": "https://img.com/1.webp",
                 "source_url": None, "display_order": 1},
                {"post_id": self.post_ids[1], "image_url": "https://img.com/2.webp",
                 "source_url": None, "display_order": 2},
                {"post_id": self.post_ids[2], "image_url": "https://img.com/3.webp",
                 "source_url": None, "display_order": 3}
            ]
        }
        self._save_campaign(self.campaign)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _save_campaign(self, campaign):
        path = os.path.join(self.temp_dir, f"{campaign['campaign_id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(campaign, f)

    def _load_campaign(self, campaign_id):
        path = os.path.join(self.temp_dir, f"{campaign_id}.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _call_remove(self, body, campaign_id=None):
        from unittest.mock import patch
        mock = MockHandler(body)
        cid = campaign_id or (body.get("campaign_id", "") if body else "")
        with patch('api.admin.ugc.CAMPAIGNS_DIR', self.temp_dir):
            _handle_remove(mock, cid)
        return mock

    def test_successful_delete_via_body(self):
        """Successfully remove a post via request body."""
        mock = self._call_remove({
            "post_id": self.post_ids[1]
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")

        # Verify remaining posts have reordered display_order
        data = response["data"]
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["display_order"], 1)
        self.assertEqual(data[1]["display_order"], 2)

    def test_delete_reorders_remaining(self):
        """After delete, remaining posts are reordered 1..n."""
        self._call_remove({
            "post_id": self.post_ids[0]
        }, campaign_id=self.campaign_id)
        campaign = self._load_campaign(self.campaign_id)
        for i, post in enumerate(campaign["ugc_gallery"]):
            self.assertEqual(post["display_order"], i + 1)

    def test_delete_nonexistent_post(self):
        """Deleting a non-existent post returns NOT_FOUND."""
        mock = self._call_remove({
            "post_id": "nonexistent-post-id"
        }, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 404)

    def test_delete_from_nonexistent_campaign(self):
        """Deleting from non-existent campaign returns NOT_FOUND."""
        mock = self._call_remove({
            "post_id": self.post_ids[0]
        }, campaign_id="nonexistent-campaign")
        self.assertEqual(mock.response_status, 404)

    def test_missing_post_id(self):
        """Missing post_id returns VALIDATION_ERROR."""
        mock = self._call_remove({}, campaign_id=self.campaign_id)
        self.assertEqual(mock.response_status, 400)

    def test_delete_persisted(self):
        """Deletion is saved to campaign JSON file."""
        self._call_remove({
            "post_id": self.post_ids[1]
        }, campaign_id=self.campaign_id)
        campaign = self._load_campaign(self.campaign_id)
        self.assertEqual(len(campaign["ugc_gallery"]), 2)
        post_ids_in_gallery = [p["post_id"] for p in campaign["ugc_gallery"]]
        self.assertNotIn(self.post_ids[1], post_ids_in_gallery)


if __name__ == '__main__':
    unittest.main()
