"""Unit tests for the registration endpoint validation logic."""
import json
import os
import sys
import pytest
from unittest.mock import patch

# Add the project root to path so we can import from api
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from api.register import (
    validate_registration,
    validate_size_color,
    find_product,
    load_campaign_config,
    apply_single_product_mode,
    check_product_closed,
    check_duplicate,
    persist_registration,
    append_with_retry,
    save_to_retry_queue,
    sync_to_excel,
    SheetsUnavailableError,
    MAX_RETRIES,
)


# --- Test fixtures ---

def make_valid_body():
    """Create a valid registration request body."""
    return {
        "campaign_id": "sample",
        "product_id": "prod-001",
        "selected_size": "M",
        "selected_color": "블랙",
        "instagram_id": "@creator_test",
        "name": "홍길동",
        "phone": "010-1234-5678",
        "address": "서울시 강남구 테헤란로 123",
        "postal_code": "06234",
        "consent": True,
        "member_type": "new",
    }


def make_sample_config():
    """Create a sample campaign config for testing."""
    return {
        "campaign_id": "sample",
        "products": [
            {
                "product_id": "prod-001",
                "product_name": "Test Product",
                "available_sizes": ["S", "M", "L", "XL", "2XL"],
                "available_colors": ["아이보리", "블랙", "핑크", "라벤더", "스킨베이지"],
                "status": "open",
            },
            {
                "product_id": "prod-002",
                "product_name": "Test Product 2",
                "available_sizes": ["XS", "S", "M", "L", "XL"],
                "available_colors": ["화이트", "블랙", "누드핑크", "민트"],
                "status": "open",
            },
        ],
    }


# --- validate_registration tests ---

class TestValidateRegistration:
    def test_valid_body_passes(self):
        body = make_valid_body()
        error_code, error_message = validate_registration(body)
        assert error_code is None
        assert error_message is None

    def test_missing_campaign_id(self):
        body = make_valid_body()
        del body["campaign_id"]
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_empty_campaign_id(self):
        body = make_valid_body()
        body["campaign_id"] = ""
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_whitespace_only_campaign_id(self):
        body = make_valid_body()
        body["campaign_id"] = "   "
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_missing_product_id(self):
        body = make_valid_body()
        del body["product_id"]
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_missing_instagram_id(self):
        body = make_valid_body()
        del body["instagram_id"]
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_instagram_id_max_length_exceeded(self):
        body = make_valid_body()
        body["instagram_id"] = "x" * 201
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_instagram_id_at_max_length(self):
        body = make_valid_body()
        body["instagram_id"] = "x" * 200
        error_code, _ = validate_registration(body)
        assert error_code is None

    def test_name_max_length_exceeded(self):
        body = make_valid_body()
        body["name"] = "가" * 101
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_name_at_max_length(self):
        body = make_valid_body()
        body["name"] = "가" * 100
        error_code, _ = validate_registration(body)
        assert error_code is None

    def test_phone_max_length_exceeded(self):
        body = make_valid_body()
        body["phone"] = "0" * 21
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_phone_at_max_length(self):
        body = make_valid_body()
        body["phone"] = "0" * 20
        error_code, _ = validate_registration(body)
        assert error_code is None

    def test_address_max_length_exceeded(self):
        body = make_valid_body()
        body["address"] = "가" * 301
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_address_at_max_length(self):
        body = make_valid_body()
        body["address"] = "가" * 300
        error_code, _ = validate_registration(body)
        assert error_code is None

    def test_postal_code_max_length_exceeded(self):
        body = make_valid_body()
        body["postal_code"] = "1" * 11
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_postal_code_at_max_length(self):
        body = make_valid_body()
        body["postal_code"] = "1" * 10
        error_code, _ = validate_registration(body)
        assert error_code is None

    def test_consent_false(self):
        body = make_valid_body()
        body["consent"] = False
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_consent_missing(self):
        body = make_valid_body()
        del body["consent"]
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_consent_string_true_rejected(self):
        body = make_valid_body()
        body["consent"] = "true"
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_consent_integer_one_rejected(self):
        body = make_valid_body()
        body["consent"] = 1
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_non_string_field_rejected(self):
        body = make_valid_body()
        body["name"] = 12345
        error_code, _ = validate_registration(body)
        assert error_code == "VALIDATION_ERROR"

    def test_member_type_new_is_valid(self):
        body = make_valid_body()
        body["member_type"] = "new"
        error_code, _ = validate_registration(body)
        assert error_code is None

    def test_member_type_returning_is_valid(self):
        body = make_valid_body()
        body["member_type"] = "returning"
        error_code, _ = validate_registration(body)
        assert error_code is None

    def test_member_type_missing_returns_invalid(self):
        body = make_valid_body()
        del body["member_type"]
        error_code, error_message = validate_registration(body)
        assert error_code == "INVALID_MEMBER_TYPE"
        assert error_message == "회원 유형을 선택해 주세요."

    def test_member_type_empty_string_returns_invalid(self):
        body = make_valid_body()
        body["member_type"] = ""
        error_code, error_message = validate_registration(body)
        assert error_code == "INVALID_MEMBER_TYPE"
        assert error_message == "회원 유형을 선택해 주세요."

    def test_member_type_display_text_rejected(self):
        """Display text '신규 회원' should be rejected, only internal values accepted."""
        body = make_valid_body()
        body["member_type"] = "신규 회원"
        error_code, error_message = validate_registration(body)
        assert error_code == "INVALID_MEMBER_TYPE"
        assert error_message == "회원 유형을 선택해 주세요."

    def test_member_type_display_text_returning_rejected(self):
        """Display text '기존 회원' should be rejected, only internal values accepted."""
        body = make_valid_body()
        body["member_type"] = "기존 회원"
        error_code, error_message = validate_registration(body)
        assert error_code == "INVALID_MEMBER_TYPE"
        assert error_message == "회원 유형을 선택해 주세요."

    def test_member_type_arbitrary_value_rejected(self):
        body = make_valid_body()
        body["member_type"] = "vip"
        error_code, error_message = validate_registration(body)
        assert error_code == "INVALID_MEMBER_TYPE"
        assert error_message == "회원 유형을 선택해 주세요."

    def test_member_type_none_value_rejected(self):
        body = make_valid_body()
        body["member_type"] = None
        error_code, error_message = validate_registration(body)
        assert error_code == "INVALID_MEMBER_TYPE"
        assert error_message == "회원 유형을 선택해 주세요."

    def test_member_type_integer_rejected(self):
        body = make_valid_body()
        body["member_type"] = 1
        error_code, error_message = validate_registration(body)
        assert error_code == "INVALID_MEMBER_TYPE"
        assert error_message == "회원 유형을 선택해 주세요."


# --- validate_size_color tests ---

class TestValidateSizeColor:
    def test_valid_size_and_color(self):
        body = make_valid_body()
        config = make_sample_config()
        error_code, _ = validate_size_color(body, config)
        assert error_code is None

    def test_invalid_size(self):
        body = make_valid_body()
        body["selected_size"] = "XXXL"
        config = make_sample_config()
        error_code, error_message = validate_size_color(body, config)
        assert error_code == "INVALID_SIZE_COLOR"
        assert error_message == "선택한 사이즈 또는 컬러가 유효하지 않습니다."

    def test_invalid_color(self):
        body = make_valid_body()
        body["selected_color"] = "빨강"
        config = make_sample_config()
        error_code, error_message = validate_size_color(body, config)
        assert error_code == "INVALID_SIZE_COLOR"
        assert error_message == "선택한 사이즈 또는 컬러가 유효하지 않습니다."

    def test_product_not_found(self):
        body = make_valid_body()
        body["product_id"] = "nonexistent-product"
        config = make_sample_config()
        error_code, error_message = validate_size_color(body, config)
        assert error_code == "INVALID_SIZE_COLOR"

    def test_size_from_different_product(self):
        """Size XS belongs to prod-002 but not prod-001."""
        body = make_valid_body()
        body["product_id"] = "prod-001"
        body["selected_size"] = "XS"
        config = make_sample_config()
        error_code, _ = validate_size_color(body, config)
        assert error_code == "INVALID_SIZE_COLOR"

    def test_color_from_different_product(self):
        """Color 민트 belongs to prod-002 but not prod-001."""
        body = make_valid_body()
        body["product_id"] = "prod-001"
        body["selected_color"] = "민트"
        config = make_sample_config()
        error_code, _ = validate_size_color(body, config)
        assert error_code == "INVALID_SIZE_COLOR"


# --- find_product tests ---

class TestFindProduct:
    def test_find_existing_product(self):
        config = make_sample_config()
        product = find_product(config, "prod-001")
        assert product is not None
        assert product["product_id"] == "prod-001"

    def test_find_nonexistent_product(self):
        config = make_sample_config()
        product = find_product(config, "nonexistent")
        assert product is None

    def test_find_product_empty_list(self):
        config = {"products": []}
        product = find_product(config, "prod-001")
        assert product is None


# --- load_campaign_config tests ---

class TestLoadCampaignConfig:
    def test_load_sample_config(self):
        """Test loading the actual sample config file."""
        config = load_campaign_config("sample")
        assert config is not None
        assert config["campaign_id"] == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        assert len(config["products"]) == 2

    def test_load_nonexistent_config(self):
        config = load_campaign_config("nonexistent-campaign-id")
        assert config is None

    def test_load_config_path_traversal_rejected(self):
        """Ensure path traversal attempts don't load arbitrary files."""
        config = load_campaign_config("../../requirements")
        # Should be None because the file won't be found with .json extension
        # or doesn't exist at that path
        assert config is None


# --- check_product_closed tests ---

class TestCheckProductClosed:
    def test_open_product_not_closed(self):
        """An open product should return False."""
        config = make_sample_config()
        assert check_product_closed(config, "prod-001") is False

    def test_closed_product_detected(self):
        """A closed product should return True."""
        config = make_sample_config()
        # Modify prod-001 to be closed
        config["products"][0]["status"] = "closed"
        assert check_product_closed(config, "prod-001") is True

    def test_nonexistent_product_returns_false(self):
        """A product not in config should return False (handled elsewhere)."""
        config = make_sample_config()
        assert check_product_closed(config, "nonexistent") is False

    def test_product_without_status_field_not_closed(self):
        """A product missing the status field should not be considered closed."""
        config = {
            "products": [
                {
                    "product_id": "prod-no-status",
                    "product_name": "No Status Product",
                    "available_sizes": ["M"],
                    "available_colors": ["블랙"],
                }
            ]
        }
        assert check_product_closed(config, "prod-no-status") is False


# --- check_duplicate tests ---

class TestCheckDuplicate:
    def test_returns_false_when_no_env_vars(self):
        """Without env vars configured, check_duplicate returns False (skips check)."""
        with patch.dict(os.environ, {}, clear=True):
            result = check_duplicate("campaign-1", "prod-001", "@creator")
            assert result is False

    def test_returns_false_when_missing_sheet_id(self):
        """If GOOGLE_SHEETS_ID is missing, skip check."""
        with patch.dict(os.environ, {"GOOGLE_SHEETS_CREDENTIALS": '{"type":"service_account"}'}):
            result = check_duplicate("campaign-1", "prod-001", "@creator")
            assert result is False

    def test_returns_false_when_missing_credentials(self):
        """If GOOGLE_SHEETS_CREDENTIALS is missing, skip check."""
        with patch.dict(os.environ, {"GOOGLE_SHEETS_ID": "sheet-123"}):
            result = check_duplicate("campaign-1", "prod-001", "@creator")
            assert result is False

    @patch("api.register.gspread")
    @patch("api.register.Credentials")
    def test_returns_true_when_duplicate_found(self, mock_creds_class, mock_gspread):
        """Should return True when a matching row exists in the sheet."""
        mock_creds_class.from_service_account_info.return_value = "mock_creds"
        mock_worksheet = mock_gspread.authorize.return_value.open_by_key.return_value.sheet1
        mock_worksheet.get_all_values.return_value = [
            ["timestamp", "campaign_id", "product_id", "size", "color", "instagram_id", "name", "phone", "address", "postal", "consent"],
            ["2024-01-01T00:00:00Z", "campaign-1", "prod-001", "M", "블랙", "@creator", "홍길동", "010-1234", "서울", "12345", "true"],
        ]

        with patch.dict(os.environ, {
            "GOOGLE_SHEETS_CREDENTIALS": '{"type":"service_account","project_id":"test"}',
            "GOOGLE_SHEETS_ID": "sheet-123",
        }):
            result = check_duplicate("campaign-1", "prod-001", "@creator")
            assert result is True

    @patch("api.register.gspread")
    @patch("api.register.Credentials")
    def test_returns_false_when_no_match(self, mock_creds_class, mock_gspread):
        """Should return False when no matching row exists."""
        mock_creds_class.from_service_account_info.return_value = "mock_creds"
        mock_worksheet = mock_gspread.authorize.return_value.open_by_key.return_value.sheet1
        mock_worksheet.get_all_values.return_value = [
            ["timestamp", "campaign_id", "product_id", "size", "color", "instagram_id", "name", "phone", "address", "postal", "consent"],
            ["2024-01-01T00:00:00Z", "campaign-1", "prod-001", "M", "블랙", "@different_creator", "홍길동", "010-1234", "서울", "12345", "true"],
        ]

        with patch.dict(os.environ, {
            "GOOGLE_SHEETS_CREDENTIALS": '{"type":"service_account","project_id":"test"}',
            "GOOGLE_SHEETS_ID": "sheet-123",
        }):
            result = check_duplicate("campaign-1", "prod-001", "@creator")
            assert result is False

    @patch("api.register.gspread")
    @patch("api.register.Credentials")
    def test_returns_false_when_partial_match_campaign(self, mock_creds_class, mock_gspread):
        """Should return False when only campaign_id matches but not product/instagram."""
        mock_creds_class.from_service_account_info.return_value = "mock_creds"
        mock_worksheet = mock_gspread.authorize.return_value.open_by_key.return_value.sheet1
        mock_worksheet.get_all_values.return_value = [
            ["timestamp", "campaign_id", "product_id", "size", "color", "instagram_id", "name", "phone", "address", "postal", "consent"],
            ["2024-01-01T00:00:00Z", "campaign-1", "prod-002", "M", "블랙", "@creator", "홍길동", "010-1234", "서울", "12345", "true"],
        ]

        with patch.dict(os.environ, {
            "GOOGLE_SHEETS_CREDENTIALS": '{"type":"service_account","project_id":"test"}',
            "GOOGLE_SHEETS_ID": "sheet-123",
        }):
            # Same campaign and instagram, but different product
            result = check_duplicate("campaign-1", "prod-001", "@creator")
            assert result is False

    @patch("api.register.gspread")
    @patch("api.register.Credentials")
    def test_returns_false_on_sheets_exception(self, mock_creds_class, mock_gspread):
        """Should return False (skip check) when Google Sheets raises an exception."""
        mock_creds_class.from_service_account_info.return_value = "mock_creds"
        mock_gspread.authorize.return_value.open_by_key.side_effect = Exception("API Error")

        with patch.dict(os.environ, {
            "GOOGLE_SHEETS_CREDENTIALS": '{"type":"service_account","project_id":"test"}',
            "GOOGLE_SHEETS_ID": "sheet-123",
        }):
            result = check_duplicate("campaign-1", "prod-001", "@creator")
            assert result is False

    @patch("api.register.gspread")
    @patch("api.register.Credentials")
    def test_returns_false_when_sheet_empty(self, mock_creds_class, mock_gspread):
        """Should return False when sheet has only a header row."""
        mock_creds_class.from_service_account_info.return_value = "mock_creds"
        mock_worksheet = mock_gspread.authorize.return_value.open_by_key.return_value.sheet1
        mock_worksheet.get_all_values.return_value = [
            ["timestamp", "campaign_id", "product_id", "size", "color", "instagram_id", "name", "phone", "address", "postal", "consent"],
        ]

        with patch.dict(os.environ, {
            "GOOGLE_SHEETS_CREDENTIALS": '{"type":"service_account","project_id":"test"}',
            "GOOGLE_SHEETS_ID": "sheet-123",
        }):
            result = check_duplicate("campaign-1", "prod-001", "@creator")
            assert result is False

    @patch("api.register.gspread")
    @patch("api.register.Credentials")
    def test_same_creator_different_campaign_not_duplicate(self, mock_creds_class, mock_gspread):
        """Same creator registering for same product in different campaign is not a duplicate."""
        mock_creds_class.from_service_account_info.return_value = "mock_creds"
        mock_worksheet = mock_gspread.authorize.return_value.open_by_key.return_value.sheet1
        mock_worksheet.get_all_values.return_value = [
            ["timestamp", "campaign_id", "product_id", "size", "color", "instagram_id", "name", "phone", "address", "postal", "consent"],
            ["2024-01-01T00:00:00Z", "campaign-2", "prod-001", "M", "블랙", "@creator", "홍길동", "010-1234", "서울", "12345", "true"],
        ]

        with patch.dict(os.environ, {
            "GOOGLE_SHEETS_CREDENTIALS": '{"type":"service_account","project_id":"test"}',
            "GOOGLE_SHEETS_ID": "sheet-123",
        }):
            result = check_duplicate("campaign-1", "prod-001", "@creator")
            assert result is False


# --- Integration tests for closed product rejection in handler ---

class TestClosedProductRejection:
    """Test that the handler rejects registrations for closed products."""

    def _make_closed_product_config(self):
        """Config with a closed product."""
        config = make_sample_config()
        config["products"][0]["status"] = "closed"
        return config

    @patch("api.register.load_campaign_config")
    def test_closed_product_returns_error(self, mock_load_config):
        """Submitting for a closed product should return PRODUCT_UNAVAILABLE."""
        from io import BytesIO
        from http.server import BaseHTTPRequestHandler
        from api.register import handler

        config = self._make_closed_product_config()
        mock_load_config.return_value = config

        body = make_valid_body()
        body_bytes = json.dumps(body).encode("utf-8")

        # Create a mock request
        import http.server
        from unittest.mock import MagicMock

        mock_handler = MagicMock(spec=handler)
        mock_handler.headers = {"Content-Length": str(len(body_bytes))}
        mock_handler.rfile = BytesIO(body_bytes)

        responses = []

        def mock_send_json(status_code, data):
            responses.append((status_code, data))

        mock_handler._send_json = mock_send_json

        # Call do_POST on our handler
        handler.do_POST(mock_handler)

        assert len(responses) == 1
        status_code, data = responses[0]
        assert status_code == 400
        assert data["code"] == "PRODUCT_UNAVAILABLE"
        assert data["message"] == "현재 해당 상품은 신청할 수 없습니다."


# --- Integration tests for duplicate detection in handler ---

class TestDuplicateDetection:
    """Test that the handler rejects duplicate registrations."""

    @patch("api.register.check_duplicate")
    @patch("api.register.load_campaign_config")
    def test_duplicate_returns_409(self, mock_load_config, mock_check_dup):
        """Submitting a duplicate registration should return HTTP 409."""
        from io import BytesIO
        from api.register import handler
        from unittest.mock import MagicMock

        mock_load_config.return_value = make_sample_config()
        mock_check_dup.return_value = True  # Simulate duplicate found

        body = make_valid_body()
        body_bytes = json.dumps(body).encode("utf-8")

        mock_handler = MagicMock(spec=handler)
        mock_handler.headers = {"Content-Length": str(len(body_bytes))}
        mock_handler.rfile = BytesIO(body_bytes)

        responses = []

        def mock_send_json(status_code, data):
            responses.append((status_code, data))

        mock_handler._send_json = mock_send_json

        handler.do_POST(mock_handler)

        assert len(responses) == 1
        status_code, data = responses[0]
        assert status_code == 409
        assert data["code"] == "DUPLICATE_REGISTRATION"
        assert data["message"] == "이미 해당 상품에 신청하셨습니다."

    @patch("api.register.sync_to_excel")
    @patch("api.register.persist_registration")
    @patch("api.register.check_duplicate")
    @patch("api.register.load_campaign_config")
    def test_no_duplicate_allows_registration(self, mock_load_config, mock_check_dup, mock_persist, mock_sync):
        """When no duplicate exists, registration should succeed."""
        from io import BytesIO
        from api.register import handler
        from unittest.mock import MagicMock

        mock_load_config.return_value = make_sample_config()
        mock_check_dup.return_value = False  # No duplicate
        mock_persist.return_value = ["2024-01-01T00:00:00Z", "sample", "prod-001",
                                     "M", "블랙", "@creator_test", "홍길동",
                                     "010-1234-5678", "서울시 강남구 테헤란로 123",
                                     "06234", "true"]

        body = make_valid_body()
        body_bytes = json.dumps(body).encode("utf-8")

        mock_handler = MagicMock(spec=handler)
        mock_handler.headers = {"Content-Length": str(len(body_bytes))}
        mock_handler.rfile = BytesIO(body_bytes)

        responses = []

        def mock_send_json(status_code, data):
            responses.append((status_code, data))

        mock_handler._send_json = mock_send_json

        handler.do_POST(mock_handler)

        assert len(responses) == 1
        status_code, data = responses[0]
        assert status_code == 200
        assert data["status"] == "success"


# --- apply_single_product_mode tests ---

class TestApplySingleProductMode:
    """Tests for single-product auto-association logic (Task 2.2)."""

    def _make_single_product_config(self, product_status="open"):
        """Create a single-product campaign config."""
        return {
            "campaign_id": "single-campaign",
            "product_mode": "single",
            "products": [
                {
                    "product_id": "prod-single-001",
                    "product_name": "Single Product",
                    "available_sizes": ["S", "M", "L"],
                    "available_colors": ["블랙", "화이트"],
                    "status": product_status,
                }
            ],
        }

    def test_single_mode_overrides_client_product_id(self):
        """In single mode, client-provided product_id should be overridden."""
        body = make_valid_body()
        body["product_id"] = "client-provided-id"
        config = self._make_single_product_config()

        error_code, error_message = apply_single_product_mode(body, config)

        assert error_code is None
        assert error_message is None
        assert body["product_id"] == "prod-single-001"

    def test_single_mode_overrides_even_if_matching(self):
        """In single mode, product_id is always set from config, even if client sent the same."""
        body = make_valid_body()
        body["product_id"] = "prod-single-001"
        config = self._make_single_product_config()

        error_code, _ = apply_single_product_mode(body, config)

        assert error_code is None
        assert body["product_id"] == "prod-single-001"

    def test_multiple_mode_does_not_override(self):
        """In multiple mode, product_id should NOT be overridden."""
        body = make_valid_body()
        body["product_id"] = "client-product-id"
        config = make_sample_config()  # product_mode is "multiple"

        error_code, error_message = apply_single_product_mode(body, config)

        assert error_code is None
        assert error_message is None
        assert body["product_id"] == "client-product-id"

    def test_single_mode_no_products_returns_unavailable(self):
        """Single mode with empty products list should return PRODUCT_UNAVAILABLE."""
        body = make_valid_body()
        config = {
            "campaign_id": "empty-campaign",
            "product_mode": "single",
            "products": [],
        }

        error_code, error_message = apply_single_product_mode(body, config)

        assert error_code == "PRODUCT_UNAVAILABLE"
        assert error_message == "현재 해당 상품은 신청할 수 없습니다."

    def test_single_mode_products_key_missing_returns_unavailable(self):
        """Single mode with missing products key should return PRODUCT_UNAVAILABLE."""
        body = make_valid_body()
        config = {
            "campaign_id": "no-products-key",
            "product_mode": "single",
        }

        error_code, error_message = apply_single_product_mode(body, config)

        assert error_code == "PRODUCT_UNAVAILABLE"
        assert error_message == "현재 해당 상품은 신청할 수 없습니다."

    def test_single_mode_closed_product_returns_unavailable(self):
        """Single mode with a closed product should return PRODUCT_UNAVAILABLE."""
        body = make_valid_body()
        config = self._make_single_product_config(product_status="closed")

        error_code, error_message = apply_single_product_mode(body, config)

        assert error_code == "PRODUCT_UNAVAILABLE"
        assert error_message == "현재 해당 상품은 신청할 수 없습니다."

    def test_single_mode_product_without_id_returns_unavailable(self):
        """Single mode product missing product_id should return PRODUCT_UNAVAILABLE."""
        body = make_valid_body()
        config = {
            "campaign_id": "bad-product",
            "product_mode": "single",
            "products": [
                {
                    "product_name": "Missing ID Product",
                    "available_sizes": ["M"],
                    "available_colors": ["블랙"],
                    "status": "open",
                }
            ],
        }

        error_code, error_message = apply_single_product_mode(body, config)

        assert error_code == "PRODUCT_UNAVAILABLE"
        assert error_message == "현재 해당 상품은 신청할 수 없습니다."

    def test_single_mode_empty_product_id_returns_unavailable(self):
        """Single mode product with empty string product_id should return PRODUCT_UNAVAILABLE."""
        body = make_valid_body()
        config = {
            "campaign_id": "empty-id",
            "product_mode": "single",
            "products": [
                {
                    "product_id": "",
                    "product_name": "Empty ID Product",
                    "available_sizes": ["M"],
                    "available_colors": ["블랙"],
                    "status": "open",
                }
            ],
        }

        error_code, error_message = apply_single_product_mode(body, config)

        assert error_code == "PRODUCT_UNAVAILABLE"
        assert error_message == "현재 해당 상품은 신청할 수 없습니다."

    def test_single_mode_product_without_status_returns_unavailable(self):
        """Single mode product missing status field should return PRODUCT_UNAVAILABLE."""
        body = make_valid_body()
        config = {
            "campaign_id": "no-status",
            "product_mode": "single",
            "products": [
                {
                    "product_id": "prod-no-status",
                    "product_name": "No Status Product",
                    "available_sizes": ["M"],
                    "available_colors": ["블랙"],
                }
            ],
        }

        error_code, error_message = apply_single_product_mode(body, config)

        assert error_code == "PRODUCT_UNAVAILABLE"
        assert error_message == "현재 해당 상품은 신청할 수 없습니다."

    def test_single_mode_product_with_unexpected_status_returns_unavailable(self):
        """Single mode product with unexpected status (not 'open') should return PRODUCT_UNAVAILABLE."""
        body = make_valid_body()
        config = {
            "campaign_id": "unexpected-status",
            "product_mode": "single",
            "products": [
                {
                    "product_id": "prod-weird-status",
                    "product_name": "Weird Status Product",
                    "available_sizes": ["M"],
                    "available_colors": ["블랙"],
                    "status": "draft",
                }
            ],
        }

        error_code, error_message = apply_single_product_mode(body, config)

        assert error_code == "PRODUCT_UNAVAILABLE"
        assert error_message == "현재 해당 상품은 신청할 수 없습니다."

    def test_config_without_product_mode_does_not_override(self):
        """Config missing product_mode entirely should not trigger override."""
        body = make_valid_body()
        body["product_id"] = "original-id"
        config = {
            "campaign_id": "no-mode",
            "products": [
                {
                    "product_id": "some-product",
                    "status": "open",
                }
            ],
        }

        error_code, _ = apply_single_product_mode(body, config)

        assert error_code is None
        assert body["product_id"] == "original-id"


# --- Persistence tests (Task 2.4) ---

class TestAppendWithRetry:
    """Tests for append_with_retry function."""

    def test_success_on_first_attempt(self):
        """Should return True when append_row succeeds immediately."""
        from unittest.mock import MagicMock

        mock_worksheet = MagicMock()
        mock_worksheet.append_row.return_value = None

        row_data = ["2024-01-01T00:00:00Z", "camp-1", "prod-1", "M", "블랙",
                    "@creator", "홍길동", "010-1234", "서울", "12345", "true"]

        result = append_with_retry(mock_worksheet, row_data)
        assert result is True
        assert mock_worksheet.append_row.call_count == 1

    def test_success_after_retry(self):
        """Should succeed after initial failures and retries."""
        from unittest.mock import MagicMock

        mock_worksheet = MagicMock()
        mock_worksheet.append_row.side_effect = [
            Exception("API Error"),
            None,  # Success on second attempt
        ]

        row_data = ["2024-01-01T00:00:00Z", "camp-1", "prod-1", "M", "블랙",
                    "@creator", "홍길동", "010-1234", "서울", "12345", "true"]

        result = append_with_retry(mock_worksheet, row_data)
        assert result is True
        assert mock_worksheet.append_row.call_count == 2

    @patch("api.register.save_to_retry_queue")
    def test_raises_after_max_retries(self, mock_save_queue):
        """Should raise SheetsUnavailableError after MAX_RETRIES failures."""
        from unittest.mock import MagicMock

        mock_worksheet = MagicMock()
        mock_worksheet.append_row.side_effect = Exception("Persistent API Error")

        row_data = ["2024-01-01T00:00:00Z", "camp-1", "prod-1", "M", "블랙",
                    "@creator", "홍길동", "010-1234", "서울", "12345", "true"]

        with pytest.raises(SheetsUnavailableError):
            append_with_retry(mock_worksheet, row_data)

        assert mock_worksheet.append_row.call_count == MAX_RETRIES
        mock_save_queue.assert_called_once_with(row_data)

    @patch("api.register.save_to_retry_queue")
    def test_success_on_third_attempt(self, mock_save_queue):
        """Should succeed on the last retry attempt without saving to queue."""
        from unittest.mock import MagicMock

        mock_worksheet = MagicMock()
        mock_worksheet.append_row.side_effect = [
            Exception("Error 1"),
            Exception("Error 2"),
            None,  # Success on third attempt
        ]

        row_data = ["2024-01-01T00:00:00Z", "camp-1", "prod-1", "M", "블랙",
                    "@creator", "홍길동", "010-1234", "서울", "12345", "true"]

        result = append_with_retry(mock_worksheet, row_data)
        assert result is True
        assert mock_worksheet.append_row.call_count == 3
        mock_save_queue.assert_not_called()


class TestSaveToRetryQueue:
    """Tests for save_to_retry_queue function."""

    def test_saves_row_to_jsonl_file(self, tmp_path):
        """Should append row data as JSON line to retry_queue.jsonl."""
        row_data = ["2024-01-01T00:00:00Z", "camp-1", "prod-1", "M", "블랙",
                    "@creator", "홍길동", "010-1234", "서울시", "12345", "true"]

        # Patch the project root to use tmp_path
        with patch("api.register.os.path.dirname") as mock_dirname:
            mock_dirname.return_value = str(tmp_path)
            # We need to patch at a more specific level
            pass

        # Direct test: write to a temp file
        queue_path = os.path.join(str(tmp_path), "retry_queue.jsonl")

        with patch("api.register.os.path.join") as mock_join:
            # Let the first call (getting project_root) work normally
            # but intercept to use our temp path
            import api.register as reg_module
            original_func = reg_module.save_to_retry_queue

            # Simpler approach: just test the file writing works
            with patch("api.register.os.path.normpath", return_value=queue_path):
                with patch("api.register.os.path.join", return_value=queue_path):
                    save_to_retry_queue(row_data)

        # Verify the file was created and contains valid JSON
        assert os.path.exists(queue_path)
        with open(queue_path, "r", encoding="utf-8") as f:
            line = f.readline()
            entry = json.loads(line)
            assert entry["row_data"] == row_data
            assert "failed_at" in entry


class TestPersistRegistration:
    """Tests for persist_registration function."""

    def test_raises_when_gspread_unavailable(self):
        """Should raise SheetsUnavailableError when gspread is not available."""
        with patch("api.register.GSPREAD_AVAILABLE", False):
            body = make_valid_body()
            with pytest.raises(SheetsUnavailableError):
                persist_registration(body)

    def test_raises_when_credentials_missing(self):
        """Should raise SheetsUnavailableError when env vars missing."""
        with patch.dict(os.environ, {}, clear=True):
            body = make_valid_body()
            with pytest.raises(SheetsUnavailableError):
                persist_registration(body)

    def test_raises_when_sheet_id_missing(self):
        """Should raise SheetsUnavailableError when GOOGLE_SHEETS_ID missing."""
        with patch.dict(os.environ, {"GOOGLE_SHEETS_CREDENTIALS": '{"type":"service_account"}'}):
            body = make_valid_body()
            with pytest.raises(SheetsUnavailableError):
                persist_registration(body)

    @patch("api.register.gspread")
    @patch("api.register.Credentials")
    def test_serializes_row_with_11_columns(self, mock_creds_class, mock_gspread):
        """Should serialize registration as row with exactly 11 columns in correct order."""
        mock_creds_class.from_service_account_info.return_value = "mock_creds"
        mock_worksheet = mock_gspread.authorize.return_value.open_by_key.return_value.sheet1
        mock_worksheet.append_row.return_value = None

        with patch.dict(os.environ, {
            "GOOGLE_SHEETS_CREDENTIALS": '{"type":"service_account","project_id":"test"}',
            "GOOGLE_SHEETS_ID": "sheet-123",
        }):
            body = make_valid_body()
            result = persist_registration(body)

            assert isinstance(result, list)
            mock_worksheet.append_row.assert_called_once()

            # Get the row data that was passed to append_row
            call_args = mock_worksheet.append_row.call_args
            row_data = call_args[0][0]

            # Verify exactly 11 columns
            assert len(row_data) == 11

            # Verify column order and values
            # Column 0: timestamp (ISO 8601 UTC)
            assert "T" in row_data[0]  # ISO format contains T
            assert row_data[0].endswith("Z")  # UTC timezone

            # Column 1: campaign_id
            assert row_data[1] == body["campaign_id"]

            # Column 2: product_id (internal identifier)
            assert row_data[2] == body["product_id"]

            # Column 3: selected_size (internal identifier)
            assert row_data[3] == body["selected_size"]

            # Column 4: selected_color (internal identifier)
            assert row_data[4] == body["selected_color"]

            # Column 5: instagram_id
            assert row_data[5] == body["instagram_id"]

            # Column 6: name
            assert row_data[6] == body["name"]

            # Column 7: phone
            assert row_data[7] == body["phone"]

            # Column 8: address
            assert row_data[8] == body["address"]

            # Column 9: postal_code
            assert row_data[9] == body["postal_code"]

            # Column 10: consent_status
            assert row_data[10] == "true"

    @patch("api.register.gspread")
    @patch("api.register.Credentials")
    def test_stores_internal_identifiers_not_display_text(self, mock_creds_class, mock_gspread):
        """Should store internal identifiers for product_id, size, color."""
        mock_creds_class.from_service_account_info.return_value = "mock_creds"
        mock_worksheet = mock_gspread.authorize.return_value.open_by_key.return_value.sheet1
        mock_worksheet.append_row.return_value = None

        with patch.dict(os.environ, {
            "GOOGLE_SHEETS_CREDENTIALS": '{"type":"service_account","project_id":"test"}',
            "GOOGLE_SHEETS_ID": "sheet-123",
        }):
            body = {
                "campaign_id": "camp-123",
                "product_id": "prod-internal-001",
                "selected_size": "M",
                "selected_color": "BLK",
                "instagram_id": "@test",
                "name": "Test User",
                "phone": "010-0000",
                "address": "Test Address",
                "postal_code": "00000",
                "consent": True,
            }
            persist_registration(body)

            call_args = mock_worksheet.append_row.call_args
            row_data = call_args[0][0]

            # These should be the raw internal identifiers from the body
            assert row_data[2] == "prod-internal-001"
            assert row_data[3] == "M"
            assert row_data[4] == "BLK"


class TestPersistRegistrationInHandler:
    """Tests for Google Sheets persistence integration in the handler."""

    @patch("api.register.sync_to_excel")
    @patch("api.register.persist_registration")
    @patch("api.register.check_duplicate")
    @patch("api.register.load_campaign_config")
    def test_sheets_unavailable_returns_503(self, mock_load_config, mock_check_dup, mock_persist, mock_sync):
        """When persistence fails, should return HTTP 503 with SHEETS_UNAVAILABLE."""
        from io import BytesIO
        from api.register import handler
        from unittest.mock import MagicMock

        mock_load_config.return_value = make_sample_config()
        mock_check_dup.return_value = False
        mock_persist.side_effect = SheetsUnavailableError("API unavailable")

        body = make_valid_body()
        body_bytes = json.dumps(body).encode("utf-8")

        mock_handler = MagicMock(spec=handler)
        mock_handler.headers = {"Content-Length": str(len(body_bytes))}
        mock_handler.rfile = BytesIO(body_bytes)

        responses = []

        def mock_send_json(status_code, data):
            responses.append((status_code, data))

        mock_handler._send_json = mock_send_json

        handler.do_POST(mock_handler)

        assert len(responses) == 1
        status_code, data = responses[0]
        assert status_code == 503
        assert data["code"] == "SHEETS_UNAVAILABLE"
        assert data["message"] == "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."

    @patch("api.register.sync_to_excel")
    @patch("api.register.persist_registration")
    @patch("api.register.check_duplicate")
    @patch("api.register.load_campaign_config")
    def test_successful_persistence_returns_200(self, mock_load_config, mock_check_dup, mock_persist, mock_sync):
        """When persistence succeeds, should return HTTP 200 success."""
        from io import BytesIO
        from api.register import handler
        from unittest.mock import MagicMock

        mock_load_config.return_value = make_sample_config()
        mock_check_dup.return_value = False
        mock_persist.return_value = ["2024-01-01T00:00:00Z", "sample", "prod-001",
                                     "M", "블랙", "@creator_test", "홍길동",
                                     "010-1234-5678", "서울시 강남구 테헤란로 123",
                                     "06234", "true"]

        body = make_valid_body()
        body_bytes = json.dumps(body).encode("utf-8")

        mock_handler = MagicMock(spec=handler)
        mock_handler.headers = {"Content-Length": str(len(body_bytes))}
        mock_handler.rfile = BytesIO(body_bytes)

        responses = []

        def mock_send_json(status_code, data):
            responses.append((status_code, data))

        mock_handler._send_json = mock_send_json

        handler.do_POST(mock_handler)

        assert len(responses) == 1
        status_code, data = responses[0]
        assert status_code == 200
        assert data["status"] == "success"
