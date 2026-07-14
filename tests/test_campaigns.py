"""Unit tests for campaign CRUD API endpoint."""

import json
import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch
from io import BytesIO

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.admin.campaigns import (
    _validate_url,
    _now_iso,
    _save_campaign,
    _load_campaign,
    _list_campaigns,
    _get_campaign_path,
    CAMPAIGNS_DIR,
    VALID_PRODUCT_MODES,
    VALID_MARKETS,
    VALID_STATUSES,
)


class FakeHandler:
    """Fake HTTP handler for testing."""

    def __init__(self, method="GET", path="/api/admin/campaigns", body=None, headers=None):
        self.method = method
        self.path = path
        self._body = body
        self.headers = headers or {}
        self._response_code = None
        self._response_headers = {}
        self._response_body = b""
        self.wfile = BytesIO()

        # Set Content-Length header
        if body:
            raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.rfile = BytesIO(raw)
            self.headers["Content-Length"] = str(len(raw))
        else:
            self.rfile = BytesIO(b"")
            self.headers["Content-Length"] = "0"

    def send_response(self, code):
        self._response_code = code

    def send_header(self, key, value):
        self._response_headers[key] = value

    def end_headers(self):
        pass

    def get_response(self):
        """Parse the response body as JSON."""
        self.wfile.seek(0)
        raw = self.wfile.read()
        if raw:
            return json.loads(raw.decode("utf-8"))
        return None


class TestValidateUrl(unittest.TestCase):
    """Test URL validation helper."""

    def test_valid_http_url(self):
        self.assertTrue(_validate_url("http://example.com/image.png"))

    def test_valid_https_url(self):
        self.assertTrue(_validate_url("https://cdn.veimia.com/hero.webp"))

    def test_empty_url_is_valid(self):
        self.assertTrue(_validate_url(""))

    def test_none_url_is_valid(self):
        self.assertTrue(_validate_url(None))

    def test_ftp_url_invalid(self):
        self.assertFalse(_validate_url("ftp://example.com/file"))

    def test_no_scheme_invalid(self):
        self.assertFalse(_validate_url("example.com/image.png"))

    def test_url_exceeding_2048_chars(self):
        long_url = "https://example.com/" + "a" * 2048
        self.assertFalse(_validate_url(long_url))


class TestCampaignCRUD(unittest.TestCase):
    """Test campaign CRUD operations using temp directory."""

    def setUp(self):
        """Create a temporary campaigns directory for testing."""
        self.test_dir = tempfile.mkdtemp()
        self._orig_campaigns_dir = None

    def tearDown(self):
        """Clean up temp directory."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _patch_dir(self):
        """Patch the CAMPAIGNS_DIR module variable."""
        import api.admin.campaigns as mod
        self._orig_campaigns_dir = mod.CAMPAIGNS_DIR
        mod.CAMPAIGNS_DIR = self.test_dir
        return mod

    def _unpatch_dir(self, mod):
        """Restore original CAMPAIGNS_DIR."""
        mod.CAMPAIGNS_DIR = self._orig_campaigns_dir

    def test_create_campaign_success(self):
        """POST with valid product_mode creates a campaign."""
        from api.admin.campaigns import _handle_post

        mod = self._patch_dir()
        try:
            h = FakeHandler(body={"product_mode": "single", "campaign_name": "Test Campaign"})
            _handle_post(h)

            self.assertEqual(h._response_code, 201)
            resp = h.get_response()
            self.assertEqual(resp["status"], "success")
            self.assertEqual(resp["data"]["product_mode"], "single")
            self.assertEqual(resp["data"]["campaign_name"], "Test Campaign")
            self.assertEqual(resp["data"]["status"], "draft")
            self.assertIn("campaign_id", resp["data"])
            self.assertIn("created_at", resp["data"])
            self.assertEqual(resp["data"]["products"], [])
            self.assertEqual(resp["data"]["ugc_gallery"], [])
        finally:
            self._unpatch_dir(mod)

    def test_create_campaign_missing_product_mode(self):
        """POST without product_mode returns VALIDATION_ERROR."""
        from api.admin.campaigns import _handle_post

        mod = self._patch_dir()
        try:
            h = FakeHandler(body={"campaign_name": "Test"})
            _handle_post(h)

            self.assertEqual(h._response_code, 400)
            resp = h.get_response()
            self.assertEqual(resp["code"], "VALIDATION_ERROR")
            self.assertIn("product_mode is required", resp["message"])
        finally:
            self._unpatch_dir(mod)

    def test_create_campaign_invalid_product_mode(self):
        """POST with invalid product_mode returns VALIDATION_ERROR."""
        from api.admin.campaigns import _handle_post

        mod = self._patch_dir()
        try:
            h = FakeHandler(body={"product_mode": "invalid"})
            _handle_post(h)

            self.assertEqual(h._response_code, 400)
            resp = h.get_response()
            self.assertEqual(resp["code"], "VALIDATION_ERROR")
        finally:
            self._unpatch_dir(mod)

    def test_get_campaign_by_id(self):
        """GET with campaign_id returns that campaign."""
        from api.admin.campaigns import _handle_post, _handle_get

        mod = self._patch_dir()
        try:
            # Create a campaign first
            h = FakeHandler(body={"product_mode": "multiple", "campaign_name": "My Campaign"})
            _handle_post(h)
            campaign_id = h.get_response()["data"]["campaign_id"]

            # Get it
            h2 = FakeHandler(path=f"/api/admin/campaigns?campaign_id={campaign_id}")
            _handle_get(h2)

            self.assertEqual(h2._response_code, 200)
            resp = h2.get_response()
            self.assertEqual(resp["data"]["campaign_id"], campaign_id)
            self.assertEqual(resp["data"]["campaign_name"], "My Campaign")
        finally:
            self._unpatch_dir(mod)

    def test_get_campaign_not_found(self):
        """GET with nonexistent campaign_id returns 404."""
        from api.admin.campaigns import _handle_get

        mod = self._patch_dir()
        try:
            h = FakeHandler(path="/api/admin/campaigns?campaign_id=nonexistent-id")
            _handle_get(h)

            self.assertEqual(h._response_code, 404)
            resp = h.get_response()
            self.assertEqual(resp["code"], "NOT_FOUND")
        finally:
            self._unpatch_dir(mod)

    def test_list_campaigns(self):
        """GET without campaign_id returns list of all campaigns."""
        from api.admin.campaigns import _handle_post, _handle_get

        mod = self._patch_dir()
        try:
            # Create two campaigns
            h1 = FakeHandler(body={"product_mode": "single", "campaign_name": "Campaign A"})
            _handle_post(h1)
            h2 = FakeHandler(body={"product_mode": "multiple", "campaign_name": "Campaign B"})
            _handle_post(h2)

            # List
            h3 = FakeHandler(path="/api/admin/campaigns")
            _handle_get(h3)

            self.assertEqual(h3._response_code, 200)
            resp = h3.get_response()
            self.assertEqual(len(resp["data"]), 2)
        finally:
            self._unpatch_dir(mod)

    def test_update_campaign(self):
        """PUT updates campaign fields."""
        from api.admin.campaigns import _handle_post, _handle_put

        mod = self._patch_dir()
        try:
            # Create
            h = FakeHandler(body={"product_mode": "single", "campaign_name": "Original"})
            _handle_post(h)
            campaign_id = h.get_response()["data"]["campaign_id"]

            # Update
            h2 = FakeHandler(body={
                "campaign_id": campaign_id,
                "campaign_name": "Updated Name",
                "market": "ja"
            })
            _handle_put(h2)

            self.assertEqual(h2._response_code, 200)
            resp = h2.get_response()
            self.assertEqual(resp["data"]["campaign_name"], "Updated Name")
            self.assertEqual(resp["data"]["market"], "ja")
        finally:
            self._unpatch_dir(mod)

    def test_publish_with_no_products_rejected(self):
        """PUT to publish campaign with no products returns NO_PRODUCTS error."""
        from api.admin.campaigns import _handle_post, _handle_put

        mod = self._patch_dir()
        try:
            # Create (draft, no products)
            h = FakeHandler(body={"product_mode": "single", "campaign_name": "Empty Campaign"})
            _handle_post(h)
            campaign_id = h.get_response()["data"]["campaign_id"]

            # Try to publish
            h2 = FakeHandler(body={
                "campaign_id": campaign_id,
                "status": "published"
            })
            _handle_put(h2)

            self.assertEqual(h2._response_code, 400)
            resp = h2.get_response()
            self.assertEqual(resp["code"], "NO_PRODUCTS")
            self.assertIn("최소 1개의 상품을 등록해 주세요", resp["message"])
        finally:
            self._unpatch_dir(mod)

    def test_publish_with_products_succeeds(self):
        """PUT to publish campaign with products succeeds."""
        from api.admin.campaigns import _handle_post, _handle_put

        mod = self._patch_dir()
        try:
            # Create
            h = FakeHandler(body={"product_mode": "single", "campaign_name": "Full Campaign"})
            _handle_post(h)
            campaign_id = h.get_response()["data"]["campaign_id"]

            # Add products and publish
            h2 = FakeHandler(body={
                "campaign_id": campaign_id,
                "status": "published",
                "products": [{"product_id": "prod-001", "status": "open"}]
            })
            _handle_put(h2)

            self.assertEqual(h2._response_code, 200)
            resp = h2.get_response()
            self.assertEqual(resp["data"]["status"], "published")
            self.assertEqual(len(resp["data"]["products"]), 1)
        finally:
            self._unpatch_dir(mod)

    def test_delete_campaign(self):
        """DELETE removes the campaign JSON file."""
        from api.admin.campaigns import _handle_post, _handle_delete, _handle_get

        mod = self._patch_dir()
        try:
            # Create
            h = FakeHandler(body={"product_mode": "single", "campaign_name": "To Delete"})
            _handle_post(h)
            campaign_id = h.get_response()["data"]["campaign_id"]

            # Delete
            h2 = FakeHandler(path=f"/api/admin/campaigns?campaign_id={campaign_id}")
            _handle_delete(h2)

            self.assertEqual(h2._response_code, 200)
            resp = h2.get_response()
            self.assertEqual(resp["status"], "success")

            # Verify it's gone
            h3 = FakeHandler(path=f"/api/admin/campaigns?campaign_id={campaign_id}")
            _handle_get(h3)
            self.assertEqual(h3._response_code, 404)
        finally:
            self._unpatch_dir(mod)

    def test_delete_nonexistent_campaign(self):
        """DELETE with nonexistent campaign_id returns 404."""
        from api.admin.campaigns import _handle_delete

        mod = self._patch_dir()
        try:
            h = FakeHandler(path="/api/admin/campaigns?campaign_id=does-not-exist")
            _handle_delete(h)

            self.assertEqual(h._response_code, 404)
            resp = h.get_response()
            self.assertEqual(resp["code"], "NOT_FOUND")
        finally:
            self._unpatch_dir(mod)

    def test_create_campaign_persists_to_file(self):
        """Creating a campaign persists a JSON file on disk."""
        from api.admin.campaigns import _handle_post

        mod = self._patch_dir()
        try:
            h = FakeHandler(body={"product_mode": "multiple", "campaign_name": "Persisted"})
            _handle_post(h)
            campaign_id = h.get_response()["data"]["campaign_id"]

            # Verify file exists
            filepath = os.path.join(self.test_dir, f"{campaign_id}.json")
            self.assertTrue(os.path.exists(filepath))

            # Verify file contents
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["campaign_id"], campaign_id)
            self.assertEqual(data["product_mode"], "multiple")
            self.assertEqual(data["campaign_name"], "Persisted")
        finally:
            self._unpatch_dir(mod)

    def test_create_campaign_default_market_is_ko(self):
        """Campaign defaults to Korean market if not specified."""
        from api.admin.campaigns import _handle_post

        mod = self._patch_dir()
        try:
            h = FakeHandler(body={"product_mode": "single"})
            _handle_post(h)
            resp = h.get_response()
            self.assertEqual(resp["data"]["market"], "ko")
        finally:
            self._unpatch_dir(mod)


if __name__ == "__main__":
    unittest.main()
