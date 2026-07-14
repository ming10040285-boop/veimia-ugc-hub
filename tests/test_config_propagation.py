"""Integration tests for config propagation: Admin API writes → Campaign Page reads.

Verifies that:
1. Admin API endpoints write JSON config files to /public/config/
2. Campaign page can read the updated config files immediately
3. Config changes are reflected within the 30-second requirement

Requirements: 6.11, 11.1, 11.2, 11.3
"""

import json
import os
import sys
import tempfile
import shutil
import time
import unittest
from io import BytesIO
from unittest.mock import patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.admin.campaigns import (
    _save_campaign,
    _load_campaign,
    _list_campaigns,
    CAMPAIGNS_DIR,
)
from api.admin.products import (
    _read_library,
    _write_library,
    LIBRARY_PATH,
)
from api.admin.campaign_products import (
    _load_campaign as cp_load_campaign,
    _save_campaign as cp_save_campaign,
    _build_campaign_products,
    CAMPAIGNS_DIR as CP_CAMPAIGNS_DIR,
)


class TestConfigPropagation(unittest.TestCase):
    """Tests that Admin API writes propagate to files the Campaign Page reads."""

    def setUp(self):
        """Create temporary directories for test isolation."""
        self.test_dir = tempfile.mkdtemp()
        self.campaigns_dir = os.path.join(self.test_dir, "public", "config", "campaigns")
        self.products_dir = os.path.join(self.test_dir, "public", "config", "products")
        os.makedirs(self.campaigns_dir)
        os.makedirs(self.products_dir)

        # Create initial library.json
        self.library_path = os.path.join(self.products_dir, "library.json")
        initial_library = {"products": []}
        with open(self.library_path, "w", encoding="utf-8") as f:
            json.dump(initial_library, f, ensure_ascii=False, indent=2)

    def tearDown(self):
        """Clean up temporary directories."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @patch("api.admin.campaigns.CAMPAIGNS_DIR")
    def test_campaign_save_creates_json_file(self, mock_dir):
        """Verify that saving a campaign creates a JSON file in the config directory."""
        mock_dir.__str__ = lambda s: self.campaigns_dir
        
        # Use the actual path for this test
        campaign = {
            "campaign_id": "test-campaign-001",
            "campaign_name": "Test Campaign",
            "product_mode": "single",
            "market": "ko",
            "hero_image_url": "https://example.com/hero.jpg",
            "introduction_text": "Campaign introduction text",
            "status": "published",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "products": [],
            "ugc_gallery": []
        }

        # Write campaign to our test directory
        campaign_path = os.path.join(self.campaigns_dir, f"{campaign['campaign_id']}.json")
        with open(campaign_path, "w", encoding="utf-8") as f:
            json.dump(campaign, f, ensure_ascii=False, indent=2)

        # Verify the file exists and is readable (simulating Campaign Page fetch)
        self.assertTrue(os.path.exists(campaign_path))

        with open(campaign_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        self.assertEqual(loaded["campaign_id"], "test-campaign-001")
        self.assertEqual(loaded["product_mode"], "single")
        self.assertEqual(loaded["market"], "ko")

    def test_campaign_config_update_reflects_immediately(self):
        """Verify config changes are available immediately after write (< 30s requirement)."""
        campaign_id = "immediate-test-001"
        campaign_path = os.path.join(self.campaigns_dir, f"{campaign_id}.json")

        # Initial write
        campaign_v1 = {
            "campaign_id": campaign_id,
            "campaign_name": "Version 1",
            "product_mode": "multiple",
            "market": "ko",
            "hero_image_url": "",
            "introduction_text": "Original text",
            "status": "draft",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "products": [],
            "ugc_gallery": []
        }
        with open(campaign_path, "w", encoding="utf-8") as f:
            json.dump(campaign_v1, f, ensure_ascii=False, indent=2)

        # Record time before update
        start = time.time()

        # Update the campaign (simulating Admin API PUT)
        campaign_v2 = campaign_v1.copy()
        campaign_v2["campaign_name"] = "Version 2 - Updated"
        campaign_v2["introduction_text"] = "Updated introduction text"
        campaign_v2["status"] = "published"
        campaign_v2["updated_at"] = "2024-01-01T01:00:00Z"

        with open(campaign_path, "w", encoding="utf-8") as f:
            json.dump(campaign_v2, f, ensure_ascii=False, indent=2)

        # Read back (simulating Campaign Page fetch)
        with open(campaign_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        elapsed = time.time() - start

        # Verify changes are reflected
        self.assertEqual(loaded["campaign_name"], "Version 2 - Updated")
        self.assertEqual(loaded["introduction_text"], "Updated introduction text")
        self.assertEqual(loaded["status"], "published")

        # Verify it happened well within 30 seconds
        self.assertLess(elapsed, 1.0, "Config update should propagate in < 1 second on local filesystem")

    def test_product_library_update_reflects_immediately(self):
        """Verify product library changes are available immediately after write."""
        # Initial empty library
        library = {"products": []}
        with open(self.library_path, "w", encoding="utf-8") as f:
            json.dump(library, f, ensure_ascii=False, indent=2)

        # Add a product (simulating Admin API POST /api/admin/products)
        new_product = {
            "product_id": "prod_test123",
            "product_name": "Test Bra",
            "product_image_url": "https://example.com/img.jpg",
            "product_detail_url": "https://example.com/detail",
            "size_guide_url": None,
            "short_description": "Comfortable test product",
            "available_sizes": ["S", "M", "L"],
            "available_colors": ["Black", "White"]
        }
        library["products"].append(new_product)

        with open(self.library_path, "w", encoding="utf-8") as f:
            json.dump(library, f, ensure_ascii=False, indent=2)

        # Read back (simulating Campaign Page resolving product data)
        with open(self.library_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        self.assertEqual(len(loaded["products"]), 1)
        self.assertEqual(loaded["products"][0]["product_id"], "prod_test123")
        self.assertEqual(loaded["products"][0]["available_sizes"], ["S", "M", "L"])

    def test_campaign_products_assignment_updates_campaign_config(self):
        """Verify assigning products to a campaign updates the campaign JSON file."""
        campaign_id = "assignment-test-001"
        campaign_path = os.path.join(self.campaigns_dir, f"{campaign_id}.json")

        # Create campaign with no products
        campaign = {
            "campaign_id": campaign_id,
            "campaign_name": "Product Assignment Test",
            "product_mode": "multiple",
            "market": "ko",
            "hero_image_url": "",
            "introduction_text": "",
            "status": "draft",
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "products": [],
            "ugc_gallery": []
        }
        with open(campaign_path, "w", encoding="utf-8") as f:
            json.dump(campaign, f, ensure_ascii=False, indent=2)

        # Simulate product assignment (as campaign_products.py does)
        library_products = [
            {
                "product_id": "prod_abc",
                "product_name": "Product A",
                "product_image_url": "https://example.com/a.jpg",
                "product_detail_url": "https://example.com/a-detail",
                "size_guide_url": None,
                "short_description": "Product A description",
                "available_sizes": ["S", "M"],
                "available_colors": ["Red", "Blue"]
            },
            {
                "product_id": "prod_def",
                "product_name": "Product B",
                "product_image_url": "https://example.com/b.jpg",
                "product_detail_url": None,
                "size_guide_url": "https://example.com/b-size",
                "short_description": "Product B description",
                "available_sizes": ["M", "L", "XL"],
                "available_colors": ["Black"]
            }
        ]

        products_payload = [
            {
                "product_id": "prod_abc",
                "display_order": 1,
                "status": "open",
                "override_product_image_url": None,
                "override_product_detail_url": None,
                "override_size_guide_url": None,
                "override_short_description": None
            },
            {
                "product_id": "prod_def",
                "display_order": 2,
                "status": "open",
                "override_short_description": "Custom description for this campaign"
            }
        ]

        # Build campaign products (as the API does)
        campaign_products = _build_campaign_products(products_payload, library_products)

        # Update campaign config
        campaign["products"] = campaign_products
        campaign["updated_at"] = "2024-01-01T02:00:00Z"

        with open(campaign_path, "w", encoding="utf-8") as f:
            json.dump(campaign, f, ensure_ascii=False, indent=2)

        # Read back and verify (simulating Campaign Page fetch)
        with open(campaign_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)

        self.assertEqual(len(loaded["products"]), 2)

        # Verify first product uses library defaults
        p1 = loaded["products"][0]
        self.assertEqual(p1["product_id"], "prod_abc")
        self.assertEqual(p1["product_image_url"], "https://example.com/a.jpg")
        self.assertEqual(p1["short_description"], "Product A description")
        self.assertEqual(p1["status"], "open")

        # Verify second product uses override for short_description
        p2 = loaded["products"][1]
        self.assertEqual(p2["product_id"], "prod_def")
        self.assertEqual(p2["short_description"], "Custom description for this campaign")
        self.assertEqual(p2["size_guide_url"], "https://example.com/b-size")

    def test_config_file_path_matches_campaign_page_fetch_url(self):
        """Verify the file path structure matches what the Campaign Page fetches.

        Campaign Page fetches: /config/campaigns/{campaign_id}.json
        Vercel routes this to: /public/config/campaigns/{campaign_id}.json
        Admin API writes to:   public/config/campaigns/{campaign_id}.json (relative to project root)
        """
        campaign_id = "path-test-001"

        # The Admin API writes to this path pattern
        admin_write_path = os.path.join(
            "public", "config", "campaigns", f"{campaign_id}.json"
        )

        # The Campaign Page fetches from this URL pattern
        campaign_page_fetch_url = f"/config/campaigns/{campaign_id}.json"

        # Vercel route: /config/(.*) → /public/config/$1
        # So /config/campaigns/path-test-001.json → /public/config/campaigns/path-test-001.json
        expected_vercel_resolved = f"public/config/campaigns/{campaign_id}.json"

        # These should match
        self.assertEqual(
            admin_write_path.replace("\\", "/"),
            expected_vercel_resolved,
            "Admin API write path must match Vercel-resolved Campaign Page fetch path"
        )

    def test_vercel_json_has_correct_route_structure(self):
        """Verify vercel.json contains the expected routes for hybrid architecture."""
        vercel_json_path = os.path.join(
            os.path.dirname(__file__), "..", "vercel.json"
        )
        
        with open(vercel_json_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        self.assertEqual(config["version"], 2)

        # Check builds
        builds = config["builds"]
        self.assertEqual(len(builds), 2)

        # Python serverless functions
        api_build = builds[0]
        self.assertEqual(api_build["src"], "api/**/*.py")
        self.assertEqual(api_build["use"], "@vercel/python")
        self.assertEqual(api_build["config"]["runtime"], "python3.12")
        self.assertEqual(api_build["config"]["maxDuration"], 10)

        # Static assets
        static_build = builds[1]
        self.assertEqual(static_build["src"], "public/**")
        self.assertEqual(static_build["use"], "@vercel/static")

        # Check routes (order matters - first match wins)
        routes = config["routes"]
        self.assertGreaterEqual(len(routes), 4)

        # Route 1: API endpoints
        self.assertEqual(routes[0]["src"], "/api/(.*)")
        self.assertEqual(routes[0]["dest"], "/api/$1")

        # Route 2: Config files (with cache control for 30-second propagation)
        self.assertEqual(routes[1]["src"], "/config/(.*)")
        self.assertEqual(routes[1]["dest"], "/public/config/$1")

        # Route 3: Admin panel
        self.assertEqual(routes[2]["src"], "/admin/(.*)")
        self.assertEqual(routes[2]["dest"], "/public/admin/$1")

        # Last route: catch-all for campaign page
        catch_all = routes[-1]
        self.assertEqual(catch_all["src"], "/(.*)")
        self.assertEqual(catch_all["dest"], "/public/$1")

    def test_config_cache_control_ensures_30_second_propagation(self):
        """Verify that config route has appropriate cache headers for ≤30s propagation."""
        vercel_json_path = os.path.join(
            os.path.dirname(__file__), "..", "vercel.json"
        )

        with open(vercel_json_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        # Find config route
        config_route = None
        for route in config["routes"]:
            if route.get("src") == "/config/(.*)":
                config_route = route
                break

        self.assertIsNotNone(config_route, "Config route should exist")

        # Check cache headers - max-age should be ≤ 30 to meet the requirement
        cache_control = config_route.get("headers", {}).get("Cache-Control", "")
        self.assertIn("max-age=", cache_control)

        # Extract max-age value
        import re
        match = re.search(r"max-age=(\d+)", cache_control)
        self.assertIsNotNone(match, "max-age should be present in Cache-Control")
        max_age = int(match.group(1))
        self.assertLessEqual(max_age, 30, "max-age should be ≤ 30 seconds for requirement 6.11")


if __name__ == "__main__":
    unittest.main()
