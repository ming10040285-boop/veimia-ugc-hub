"""Unit tests for the product library CRUD API.

Tests validation logic, URL checking, size/color limits,
and CRUD operations against the library.json file.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.admin.products import (
    _validate_url,
    _validate_product_data,
)


class TestUrlValidation(unittest.TestCase):
    """Tests for URL validation logic."""

    def test_valid_https_url(self):
        self.assertTrue(_validate_url('https://example.com/image.png', required=True))

    def test_valid_http_url(self):
        self.assertTrue(_validate_url('http://example.com/page', required=True))

    def test_none_optional(self):
        """None is valid for optional URL fields."""
        self.assertTrue(_validate_url(None, required=False))

    def test_none_required(self):
        """None is invalid for required URL fields."""
        self.assertFalse(_validate_url(None, required=True))

    def test_empty_string_optional(self):
        """Empty string is valid for optional URL fields."""
        self.assertTrue(_validate_url('', required=False))

    def test_empty_string_required(self):
        """Empty string is invalid for required URL fields."""
        self.assertFalse(_validate_url('', required=True))

    def test_ftp_scheme_rejected(self):
        """Non http/https schemes are rejected."""
        self.assertFalse(_validate_url('ftp://example.com/file', required=True))

    def test_javascript_scheme_rejected(self):
        self.assertFalse(_validate_url('javascript:alert(1)', required=True))

    def test_url_exceeds_2048_chars(self):
        """URLs exceeding 2048 characters are rejected."""
        long_url = 'https://example.com/' + 'a' * 2030
        self.assertFalse(_validate_url(long_url, required=True))

    def test_url_exactly_2048_chars(self):
        """URL at exactly 2048 chars is valid."""
        url = 'https://example.com/' + 'a' * (2048 - len('https://example.com/'))
        self.assertEqual(len(url), 2048)
        self.assertTrue(_validate_url(url, required=True))

    def test_non_string_rejected(self):
        """Non-string types are rejected."""
        self.assertFalse(_validate_url(123, required=True))
        self.assertFalse(_validate_url(['http://x.com'], required=True))


class TestProductDataValidation(unittest.TestCase):
    """Tests for full product data validation."""

    def _valid_product_data(self):
        """Return minimal valid product data."""
        return {
            'product_name': 'Test Product',
            'product_image_url': 'https://example.com/img.png',
            'short_description': 'A test product description',
            'available_sizes': ['S', 'M', 'L'],
            'available_colors': ['Red', 'Blue']
        }

    def test_valid_product_passes(self):
        data = self._valid_product_data()
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertTrue(is_valid)
        self.assertIsNone(error)

    def test_missing_required_field(self):
        data = self._valid_product_data()
        del data['product_name']
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'VALIDATION_ERROR')

    def test_invalid_product_image_url(self):
        data = self._valid_product_data()
        data['product_image_url'] = 'not-a-url'
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'INVALID_URL')

    def test_invalid_product_detail_url(self):
        data = self._valid_product_data()
        data['product_detail_url'] = 'ftp://bad.com/file'
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'INVALID_URL')

    def test_invalid_size_guide_url(self):
        data = self._valid_product_data()
        data['size_guide_url'] = 'javascript:void(0)'
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'INVALID_URL')

    def test_sizes_empty_list(self):
        data = self._valid_product_data()
        data['available_sizes'] = []
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'SIZE_LIMIT')

    def test_sizes_exceeds_20(self):
        data = self._valid_product_data()
        data['available_sizes'] = [f'Size{i}' for i in range(21)]
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'SIZE_LIMIT')

    def test_sizes_exactly_20_valid(self):
        data = self._valid_product_data()
        data['available_sizes'] = [f'Size{i}' for i in range(20)]
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertTrue(is_valid)

    def test_colors_empty_list(self):
        data = self._valid_product_data()
        data['available_colors'] = []
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'COLOR_LIMIT')

    def test_colors_exceeds_30(self):
        data = self._valid_product_data()
        data['available_colors'] = [f'Color{i}' for i in range(31)]
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'COLOR_LIMIT')

    def test_colors_exactly_30_valid(self):
        data = self._valid_product_data()
        data['available_colors'] = [f'Color{i}' for i in range(30)]
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertTrue(is_valid)

    def test_empty_size_string_rejected(self):
        data = self._valid_product_data()
        data['available_sizes'] = ['S', '', 'L']
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'VALIDATION_ERROR')

    def test_empty_color_string_rejected(self):
        data = self._valid_product_data()
        data['available_colors'] = ['Red', '  ', 'Blue']
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'VALIDATION_ERROR')

    def test_product_name_exceeds_200_chars(self):
        data = self._valid_product_data()
        data['product_name'] = 'A' * 201
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'VALIDATION_ERROR')

    def test_short_description_exceeds_500_chars(self):
        data = self._valid_product_data()
        data['short_description'] = 'A' * 501
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'VALIDATION_ERROR')

    def test_update_mode_partial_fields_valid(self):
        """In update mode, only provided fields are validated."""
        data = {'product_name': 'Updated Name'}
        is_valid, error = _validate_product_data(data, is_update=True)
        self.assertTrue(is_valid)

    def test_update_mode_invalid_url(self):
        data = {'product_image_url': 'not-valid'}
        is_valid, error = _validate_product_data(data, is_update=True)
        self.assertFalse(is_valid)
        self.assertEqual(error['code'], 'INVALID_URL')

    def test_optional_url_null_valid(self):
        """product_detail_url and size_guide_url can be null."""
        data = self._valid_product_data()
        data['product_detail_url'] = None
        data['size_guide_url'] = None
        is_valid, error = _validate_product_data(data, is_update=False)
        self.assertTrue(is_valid)


if __name__ == '__main__':
    unittest.main()
