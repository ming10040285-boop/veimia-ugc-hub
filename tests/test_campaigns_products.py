"""Unit tests for the campaign product assignment API.

Tests validation logic for product assignment, mode constraints,
URL validation, override handling, and display_order/status validation.
"""

import json
import os
import sys
import unittest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.admin.campaign_products import (
    _validate_url,
    _validate_products_payload,
    _build_campaign_products,
    PRODUCT_LIMIT,
)


# Sample library products for testing
SAMPLE_LIBRARY = [
    {
        'product_id': 'prod-001',
        'product_name': 'Test Product 1',
        'product_image_url': 'https://cdn.example.com/img1.webp',
        'product_detail_url': 'https://example.com/product/1',
        'size_guide_url': 'https://example.com/size-guide/1',
        'short_description': 'Test product 1 description',
        'available_sizes': ['S', 'M', 'L'],
        'available_colors': ['Red', 'Blue'],
    },
    {
        'product_id': 'prod-002',
        'product_name': 'Test Product 2',
        'product_image_url': 'https://cdn.example.com/img2.webp',
        'product_detail_url': 'https://example.com/product/2',
        'size_guide_url': None,
        'short_description': 'Test product 2 description',
        'available_sizes': ['XS', 'S', 'M'],
        'available_colors': ['White', 'Black'],
    },
]


class TestUrlValidation(unittest.TestCase):
    """Tests for URL validation in campaigns_products."""

    def test_valid_https_url(self):
        self.assertTrue(_validate_url('https://example.com/image.png'))

    def test_valid_http_url(self):
        self.assertTrue(_validate_url('http://example.com/page'))

    def test_none_is_valid(self):
        """None means clear override - valid."""
        self.assertTrue(_validate_url(None))

    def test_empty_string_valid(self):
        """Empty string treated as no override."""
        self.assertTrue(_validate_url(''))

    def test_ftp_rejected(self):
        self.assertFalse(_validate_url('ftp://example.com/file'))

    def test_javascript_rejected(self):
        self.assertFalse(_validate_url('javascript:alert(1)'))

    def test_url_exceeds_2048(self):
        long_url = 'https://example.com/' + 'a' * 2030
        self.assertFalse(_validate_url(long_url))

    def test_url_exactly_2048(self):
        url = 'https://example.com/' + 'a' * (2048 - len('https://example.com/'))
        self.assertTrue(_validate_url(url))

    def test_non_string_rejected(self):
        self.assertFalse(_validate_url(123))
        self.assertFalse(_validate_url(['https://x.com']))


class TestProductsPayloadValidation(unittest.TestCase):
    """Tests for _validate_products_payload."""

    def _valid_product_item(self, product_id='prod-001', display_order=1, status='open'):
        """Return a valid product assignment item."""
        return {
            'product_id': product_id,
            'display_order': display_order,
            'status': status,
        }

    # --- Product mode constraints ---

    def test_single_mode_one_product_valid(self):
        products = [self._valid_product_item()]
        is_valid, _, _ = _validate_products_payload(products, 'single', SAMPLE_LIBRARY)
        self.assertTrue(is_valid)

    def test_single_mode_two_products_rejected(self):
        products = [
            self._valid_product_item('prod-001', 1),
            self._valid_product_item('prod-002', 2),
        ]
        is_valid, code, _ = _validate_products_payload(products, 'single', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'PRODUCT_LIMIT')

    def test_single_mode_zero_products_rejected(self):
        """Empty products array is rejected (must have exactly 1 product)."""
        is_valid, code, _ = _validate_products_payload([], 'single', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    def test_multiple_mode_50_products_valid(self):
        """50 products is the limit for multiple mode."""
        # Create 50 library products
        library = [{'product_id': f'prod-{i:03d}', 'product_name': f'P{i}'}
                   for i in range(50)]
        products = [self._valid_product_item(f'prod-{i:03d}', i + 1) for i in range(50)]
        is_valid, _, _ = _validate_products_payload(products, 'multiple', library)
        self.assertTrue(is_valid)

    def test_multiple_mode_51_products_rejected(self):
        """51 products exceeds the limit for multiple mode."""
        library = [{'product_id': f'prod-{i:03d}', 'product_name': f'P{i}'}
                   for i in range(51)]
        products = [self._valid_product_item(f'prod-{i:03d}', (i % 50) + 1) for i in range(51)]
        is_valid, code, msg = _validate_products_payload(products, 'multiple', library)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'PRODUCT_LIMIT')
        self.assertIn('50', msg)

    # --- Product ID validation ---

    def test_product_id_not_in_library_rejected(self):
        products = [self._valid_product_item('nonexistent-prod')]
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    def test_duplicate_product_id_rejected(self):
        products = [
            self._valid_product_item('prod-001', 1),
            self._valid_product_item('prod-001', 2),
        ]
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    def test_missing_product_id_rejected(self):
        products = [{'display_order': 1, 'status': 'open'}]
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    # --- Override URL validation ---

    def test_valid_override_url(self):
        products = [self._valid_product_item()]
        products[0]['override_product_image_url'] = 'https://cdn.example.com/override.webp'
        is_valid, _, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertTrue(is_valid)

    def test_null_override_url_valid(self):
        """Null override clears the override (revert to default)."""
        products = [self._valid_product_item()]
        products[0]['override_product_image_url'] = None
        is_valid, _, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertTrue(is_valid)

    def test_invalid_override_url_rejected(self):
        products = [self._valid_product_item()]
        products[0]['override_product_detail_url'] = 'ftp://invalid.com/page'
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'INVALID_URL')

    def test_override_url_exceeds_2048_rejected(self):
        products = [self._valid_product_item()]
        products[0]['override_size_guide_url'] = 'https://x.com/' + 'a' * 2040
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'INVALID_URL')

    # --- Override short description validation ---

    def test_valid_override_short_description(self):
        products = [self._valid_product_item()]
        products[0]['override_short_description'] = 'Custom campaign description'
        is_valid, _, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertTrue(is_valid)

    def test_null_override_description_valid(self):
        products = [self._valid_product_item()]
        products[0]['override_short_description'] = None
        is_valid, _, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertTrue(is_valid)

    def test_override_description_exceeds_500_rejected(self):
        products = [self._valid_product_item()]
        products[0]['override_short_description'] = 'X' * 501
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    # --- Display order validation ---

    def test_display_order_1_valid(self):
        products = [self._valid_product_item(display_order=1)]
        is_valid, _, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertTrue(is_valid)

    def test_display_order_50_valid(self):
        products = [self._valid_product_item(display_order=50)]
        is_valid, _, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertTrue(is_valid)

    def test_display_order_0_rejected(self):
        products = [self._valid_product_item(display_order=0)]
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    def test_display_order_51_rejected(self):
        products = [self._valid_product_item(display_order=51)]
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    def test_display_order_missing_rejected(self):
        products = [{'product_id': 'prod-001', 'status': 'open'}]
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    def test_display_order_boolean_rejected(self):
        """Booleans should not pass as integers."""
        products = [self._valid_product_item()]
        products[0]['display_order'] = True
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    # --- Status validation ---

    def test_status_open_valid(self):
        products = [self._valid_product_item(status='open')]
        is_valid, _, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertTrue(is_valid)

    def test_status_closed_valid(self):
        products = [self._valid_product_item(status='closed')]
        is_valid, _, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertTrue(is_valid)

    def test_status_invalid_rejected(self):
        products = [self._valid_product_item(status='active')]
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    def test_status_missing_rejected(self):
        products = [{'product_id': 'prod-001', 'display_order': 1}]
        is_valid, code, _ = _validate_products_payload(products, 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')

    # --- Non-list input ---

    def test_non_list_products_rejected(self):
        is_valid, code, _ = _validate_products_payload('not a list', 'multiple', SAMPLE_LIBRARY)
        self.assertFalse(is_valid)
        self.assertEqual(code, 'VALIDATION_ERROR')


class TestBuildCampaignProducts(unittest.TestCase):
    """Tests for _build_campaign_products merge/override logic."""

    def test_no_overrides_uses_library_defaults(self):
        """When no overrides set, resolved values equal library defaults."""
        payload = [{
            'product_id': 'prod-001',
            'display_order': 1,
            'status': 'open',
        }]
        result = _build_campaign_products(payload, SAMPLE_LIBRARY)
        self.assertEqual(len(result), 1)
        product = result[0]
        self.assertEqual(product['product_image_url'], 'https://cdn.example.com/img1.webp')
        self.assertEqual(product['product_detail_url'], 'https://example.com/product/1')
        self.assertEqual(product['size_guide_url'], 'https://example.com/size-guide/1')
        self.assertEqual(product['short_description'], 'Test product 1 description')
        self.assertIsNone(product['override_product_image_url'])

    def test_override_image_url_applied(self):
        """Override product_image_url replaces library default."""
        payload = [{
            'product_id': 'prod-001',
            'display_order': 1,
            'status': 'open',
            'override_product_image_url': 'https://cdn.example.com/campaign-special.webp',
        }]
        result = _build_campaign_products(payload, SAMPLE_LIBRARY)
        product = result[0]
        self.assertEqual(product['product_image_url'], 'https://cdn.example.com/campaign-special.webp')
        self.assertEqual(product['override_product_image_url'], 'https://cdn.example.com/campaign-special.webp')

    def test_override_detail_url_applied(self):
        payload = [{
            'product_id': 'prod-001',
            'display_order': 1,
            'status': 'open',
            'override_product_detail_url': 'https://campaign.example.com/detail',
        }]
        result = _build_campaign_products(payload, SAMPLE_LIBRARY)
        product = result[0]
        self.assertEqual(product['product_detail_url'], 'https://campaign.example.com/detail')

    def test_override_short_description_applied(self):
        payload = [{
            'product_id': 'prod-001',
            'display_order': 1,
            'status': 'open',
            'override_short_description': 'Campaign special description!',
        }]
        result = _build_campaign_products(payload, SAMPLE_LIBRARY)
        product = result[0]
        self.assertEqual(product['short_description'], 'Campaign special description!')

    def test_null_override_uses_library_default(self):
        """Null override means use library default (clearing override)."""
        payload = [{
            'product_id': 'prod-001',
            'display_order': 1,
            'status': 'open',
            'override_product_image_url': None,
            'override_product_detail_url': None,
            'override_size_guide_url': None,
            'override_short_description': None,
        }]
        result = _build_campaign_products(payload, SAMPLE_LIBRARY)
        product = result[0]
        # Should use library defaults
        self.assertEqual(product['product_image_url'], 'https://cdn.example.com/img1.webp')
        self.assertEqual(product['product_detail_url'], 'https://example.com/product/1')
        self.assertEqual(product['size_guide_url'], 'https://example.com/size-guide/1')
        self.assertEqual(product['short_description'], 'Test product 1 description')

    def test_sorted_by_display_order(self):
        """Products are sorted by display_order."""
        payload = [
            {'product_id': 'prod-002', 'display_order': 2, 'status': 'open'},
            {'product_id': 'prod-001', 'display_order': 1, 'status': 'open'},
        ]
        result = _build_campaign_products(payload, SAMPLE_LIBRARY)
        self.assertEqual(result[0]['product_id'], 'prod-001')
        self.assertEqual(result[1]['product_id'], 'prod-002')

    def test_preserves_available_sizes_colors_from_library(self):
        """Campaign products inherit available_sizes and available_colors from library."""
        payload = [{'product_id': 'prod-001', 'display_order': 1, 'status': 'open'}]
        result = _build_campaign_products(payload, SAMPLE_LIBRARY)
        product = result[0]
        self.assertEqual(product['available_sizes'], ['S', 'M', 'L'])
        self.assertEqual(product['available_colors'], ['Red', 'Blue'])

    def test_multiple_overrides_mixed(self):
        """Some fields overridden, others use defaults."""
        payload = [{
            'product_id': 'prod-001',
            'display_order': 1,
            'status': 'closed',
            'override_product_image_url': 'https://new-image.com/img.png',
            'override_short_description': 'New description',
            # detail and size guide left as default
        }]
        result = _build_campaign_products(payload, SAMPLE_LIBRARY)
        product = result[0]
        self.assertEqual(product['product_image_url'], 'https://new-image.com/img.png')
        self.assertEqual(product['short_description'], 'New description')
        self.assertEqual(product['product_detail_url'], 'https://example.com/product/1')
        self.assertEqual(product['size_guide_url'], 'https://example.com/size-guide/1')
        self.assertEqual(product['status'], 'closed')


if __name__ == '__main__':
    unittest.main()
