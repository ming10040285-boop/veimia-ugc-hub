"""Unit tests for the image upload API endpoint.

Tests validation of file format (PNG, JPG, WebP only),
size constraints (max 5 MB), storage abstraction, multipart form data parsing,
and successful upload behavior.
"""

import base64
import json
import os
import sys
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock
from io import BytesIO

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from api.admin.upload import (
    MAX_FILE_SIZE,
    ACCEPTED_CONTENT_TYPES,
    ACCEPTED_EXTENSIONS,
    EXTENSION_TO_CONTENT_TYPE,
    _get_extension_from_filename,
    _get_extension_from_content_type,
    _upload_file,
    _save_locally,
    _parse_multipart,
)


class TestExtensionFromFilename(unittest.TestCase):
    """Tests for filename extension parsing."""

    def test_png_extension(self):
        self.assertEqual(_get_extension_from_filename("photo.png"), "png")

    def test_jpg_extension(self):
        self.assertEqual(_get_extension_from_filename("photo.jpg"), "jpg")

    def test_jpeg_extension(self):
        self.assertEqual(_get_extension_from_filename("photo.jpeg"), "jpg")

    def test_webp_extension(self):
        self.assertEqual(_get_extension_from_filename("photo.webp"), "webp")

    def test_uppercase_extension(self):
        self.assertEqual(_get_extension_from_filename("PHOTO.PNG"), "png")

    def test_mixed_case(self):
        self.assertEqual(_get_extension_from_filename("Photo.JpG"), "jpg")

    def test_invalid_extension(self):
        self.assertIsNone(_get_extension_from_filename("file.gif"))

    def test_bmp_extension_rejected(self):
        self.assertIsNone(_get_extension_from_filename("file.bmp"))

    def test_no_extension(self):
        self.assertIsNone(_get_extension_from_filename("filename"))

    def test_empty_filename(self):
        self.assertIsNone(_get_extension_from_filename(""))

    def test_none_filename(self):
        self.assertIsNone(_get_extension_from_filename(None))


class TestExtensionFromContentType(unittest.TestCase):
    """Tests for content type to extension mapping."""

    def test_image_png(self):
        self.assertEqual(_get_extension_from_content_type("image/png"), "png")

    def test_image_jpeg(self):
        self.assertEqual(_get_extension_from_content_type("image/jpeg"), "jpg")

    def test_image_webp(self):
        self.assertEqual(_get_extension_from_content_type("image/webp"), "webp")

    def test_uppercase_content_type(self):
        self.assertEqual(_get_extension_from_content_type("IMAGE/PNG"), "png")

    def test_invalid_content_type(self):
        self.assertIsNone(_get_extension_from_content_type("image/gif"))

    def test_text_content_type(self):
        self.assertIsNone(_get_extension_from_content_type("text/plain"))

    def test_empty_content_type(self):
        self.assertIsNone(_get_extension_from_content_type(""))

    def test_none_content_type(self):
        self.assertIsNone(_get_extension_from_content_type(None))


class TestUploadConstants(unittest.TestCase):
    """Tests for upload configuration constants."""

    def test_max_file_size_is_5mb(self):
        self.assertEqual(MAX_FILE_SIZE, 5 * 1024 * 1024)
        self.assertEqual(MAX_FILE_SIZE, 5_242_880)

    def test_accepted_content_types(self):
        self.assertIn("image/png", ACCEPTED_CONTENT_TYPES)
        self.assertIn("image/jpeg", ACCEPTED_CONTENT_TYPES)
        self.assertIn("image/webp", ACCEPTED_CONTENT_TYPES)
        self.assertEqual(len(ACCEPTED_CONTENT_TYPES), 3)

    def test_accepted_extensions(self):
        self.assertIn(".png", ACCEPTED_EXTENSIONS)
        self.assertIn(".jpg", ACCEPTED_EXTENSIONS)
        self.assertIn(".jpeg", ACCEPTED_EXTENSIONS)
        self.assertIn(".webp", ACCEPTED_EXTENSIONS)
        self.assertEqual(len(ACCEPTED_EXTENSIONS), 4)


class MockHandler:
    """Mock HTTP handler for testing _handle_post."""

    def __init__(self, body_dict):
        self.body_json = json.dumps(body_dict).encode("utf-8") if body_dict else b""
        self.headers = {"Content-Length": str(len(self.body_json))}
        self.rfile = BytesIO(self.body_json)
        self.response_status = None
        self.response_body = None
        self._headers_sent = []

    def send_response(self, status):
        self.response_status = status

    def send_header(self, key, value):
        self._headers_sent.append((key, value))

    def end_headers(self):
        pass

    @property
    def wfile(self):
        return self._wfile

    @wfile.setter
    def wfile(self, val):
        self._wfile = val

    def __init__(self, body_dict):
        self.body_json = json.dumps(body_dict).encode("utf-8") if body_dict else b""
        self.headers = {"Content-Length": str(len(self.body_json))}
        self.rfile = BytesIO(self.body_json)
        self.response_status = None
        self.response_body = None
        self._headers_sent = []
        self._wfile = BytesIO()

    def get_response(self):
        """Parse the JSON response body."""
        return json.loads(self._wfile.getvalue().decode("utf-8"))


class TestUploadEndpoint(unittest.TestCase):
    """Integration-style tests for the upload POST handler."""

    def setUp(self):
        """Create a temporary uploads directory."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove temporary uploads directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_small_image_data(self, size_bytes=1024):
        """Create fake image data of a given size."""
        return base64.b64encode(b'\x89PNG' + b'\x00' * (size_bytes - 4)).decode('ascii')

    def _call_handler(self, body_dict):
        """Call _handle_post with a mock handler."""
        from api.admin.upload import _handle_post
        mock = MockHandler(body_dict)
        with patch('api.admin.upload.UPLOADS_DIR', self.temp_dir):
            _handle_post(mock)
        return mock

    def test_successful_png_upload(self):
        """Valid PNG upload returns success with image_url."""
        data = base64.b64encode(b'\x89PNG\r\n\x1a\n' + b'\x00' * 100).decode('ascii')
        mock = self._call_handler({
            "filename": "test.png",
            "data": data,
            "content_type": "image/png"
        })
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")
        self.assertTrue(response["data"]["image_url"].startswith("/uploads/"))
        self.assertTrue(response["data"]["image_url"].endswith(".png"))

    def test_successful_jpeg_upload(self):
        """Valid JPEG upload returns success."""
        data = base64.b64encode(b'\xff\xd8\xff\xe0' + b'\x00' * 100).decode('ascii')
        mock = self._call_handler({
            "filename": "test.jpg",
            "data": data,
            "content_type": "image/jpeg"
        })
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")
        self.assertTrue(response["data"]["image_url"].endswith(".jpg"))

    def test_successful_webp_upload(self):
        """Valid WebP upload returns success."""
        data = base64.b64encode(b'RIFF' + b'\x00' * 100).decode('ascii')
        mock = self._call_handler({
            "filename": "test.webp",
            "data": data,
            "content_type": "image/webp"
        })
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")
        self.assertTrue(response["data"]["image_url"].endswith(".webp"))

    def test_file_saved_to_disk(self):
        """Uploaded file is actually saved to the uploads directory."""
        original_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        data = base64.b64encode(original_data).decode('ascii')
        mock = self._call_handler({
            "filename": "save_test.png",
            "data": data,
            "content_type": "image/png"
        })
        self.assertEqual(mock.response_status, 200)
        # Verify file exists on disk
        files = os.listdir(self.temp_dir)
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.temp_dir, files[0]), 'rb') as f:
            saved = f.read()
        self.assertEqual(saved, original_data)

    def test_invalid_format_gif(self):
        """GIF content type is rejected with INVALID_IMAGE."""
        data = base64.b64encode(b'GIF89a' + b'\x00' * 100).decode('ascii')
        mock = self._call_handler({
            "filename": "test.gif",
            "data": data,
            "content_type": "image/gif"
        })
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["status"], "error")
        self.assertEqual(response["code"], "INVALID_IMAGE")

    def test_invalid_format_bmp(self):
        """BMP format is rejected."""
        data = base64.b64encode(b'BM' + b'\x00' * 100).decode('ascii')
        mock = self._call_handler({
            "filename": "test.bmp",
            "data": data,
            "content_type": "image/bmp"
        })
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "INVALID_IMAGE")

    def test_exceeds_5mb_rejected(self):
        """File larger than 5 MB is rejected."""
        large_data = base64.b64encode(b'\x00' * (MAX_FILE_SIZE + 1)).decode('ascii')
        mock = self._call_handler({
            "filename": "large.png",
            "data": large_data,
            "content_type": "image/png"
        })
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "INVALID_IMAGE")
        self.assertEqual(response["message"], "파일 형식 또는 크기가 올바르지 않습니다.")

    def test_exactly_5mb_accepted(self):
        """File of exactly 5 MB is accepted."""
        exact_data = base64.b64encode(b'\x00' * MAX_FILE_SIZE).decode('ascii')
        mock = self._call_handler({
            "filename": "exact.png",
            "data": exact_data,
            "content_type": "image/png"
        })
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")

    def test_empty_body_rejected(self):
        """Empty request body returns INVALID_IMAGE."""
        from api.admin.upload import _handle_post
        mock = MockHandler(None)
        mock.headers = {"Content-Length": "0"}
        with patch('api.admin.upload.UPLOADS_DIR', self.temp_dir):
            _handle_post(mock)
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "INVALID_IMAGE")

    def test_missing_data_field(self):
        """Missing data field returns INVALID_IMAGE."""
        mock = self._call_handler({
            "filename": "test.png",
            "content_type": "image/png"
        })
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "INVALID_IMAGE")

    def test_invalid_base64_rejected(self):
        """Invalid base64 string returns INVALID_IMAGE."""
        mock = self._call_handler({
            "filename": "test.png",
            "data": "not-valid-base64!!!",
            "content_type": "image/png"
        })
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "INVALID_IMAGE")

    def test_content_type_takes_priority(self):
        """Content type is used to determine extension over filename."""
        data = base64.b64encode(b'\x00' * 50).decode('ascii')
        mock = self._call_handler({
            "filename": "test.webp",
            "data": data,
            "content_type": "image/png"
        })
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        # Extension should be from content_type (png), not filename (webp)
        self.assertTrue(response["data"]["image_url"].endswith(".png"))

    def test_filename_fallback_when_no_content_type(self):
        """Filename extension is used when content_type is empty."""
        data = base64.b64encode(b'\x00' * 50).decode('ascii')
        mock = self._call_handler({
            "filename": "test.webp",
            "data": data,
            "content_type": ""
        })
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertTrue(response["data"]["image_url"].endswith(".webp"))

    def test_unique_filenames(self):
        """Multiple uploads produce unique file names."""
        data = base64.b64encode(b'\x00' * 50).decode('ascii')
        urls = set()
        for _ in range(5):
            mock = self._call_handler({
                "filename": "same.png",
                "data": data,
                "content_type": "image/png"
            })
            response = mock.get_response()
            urls.add(response["data"]["image_url"])
        self.assertEqual(len(urls), 5)

    def test_no_existing_image_modified_on_error(self):
        """When upload fails, no files are created in uploads dir."""
        # First, verify directory is empty
        self.assertEqual(len(os.listdir(self.temp_dir)), 0)
        # Submit invalid format
        data = base64.b64encode(b'\x00' * 50).decode('ascii')
        mock = self._call_handler({
            "filename": "test.gif",
            "data": data,
            "content_type": "image/gif"
        })
        self.assertEqual(mock.response_status, 400)
        # Directory should still be empty
        self.assertEqual(len(os.listdir(self.temp_dir)), 0)


class TestStorageAbstraction(unittest.TestCase):
    """Tests for the storage abstraction logic (_upload_file)."""

    def setUp(self):
        """Create a temporary uploads directory."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove temporary uploads directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_local_fallback_when_no_env_vars(self):
        """With no BLOB_READ_WRITE_TOKEN or CLOUDINARY_URL, saves locally."""
        file_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        with patch.dict(os.environ, {}, clear=True), \
             patch('api.admin.upload.UPLOADS_DIR', self.temp_dir):
            url = _upload_file(file_data, "png", "test.png")
        self.assertTrue(url.startswith("/uploads/"))
        self.assertTrue(url.endswith(".png"))
        # Verify file exists on disk
        files = os.listdir(self.temp_dir)
        self.assertEqual(len(files), 1)

    def test_vercel_blob_attempted_first_when_env_set(self):
        """When BLOB_READ_WRITE_TOKEN is set, attempts Vercel Blob first (highest priority)."""
        file_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        with patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "vercel_blob_token"}, clear=True), \
             patch('api.admin.upload._upload_to_vercel_blob', return_value="https://blob.vercel-storage.com/image.png") as mock_blob:
            url = _upload_file(file_data, "png", "test.png")
        mock_blob.assert_called_once_with(file_data, "png", "test.png")
        self.assertEqual(url, "https://blob.vercel-storage.com/image.png")

    def test_cloudinary_attempted_when_env_set(self):
        """When CLOUDINARY_URL is set (no Vercel Blob), attempts Cloudinary."""
        file_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        with patch.dict(os.environ, {"CLOUDINARY_URL": "cloudinary://key:secret@cloud"}, clear=True), \
             patch('api.admin.upload._upload_to_cloudinary', return_value="https://res.cloudinary.com/cloud/image.png") as mock_cloud:
            url = _upload_file(file_data, "png", "test.png")
        mock_cloud.assert_called_once_with(file_data, "png", "test.png")
        self.assertEqual(url, "https://res.cloudinary.com/cloud/image.png")

    def test_vercel_blob_has_priority_over_cloudinary(self):
        """When both BLOB_READ_WRITE_TOKEN and CLOUDINARY_URL are set, Vercel Blob is tried first."""
        file_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        with patch.dict(os.environ, {
            "BLOB_READ_WRITE_TOKEN": "vercel_blob_token",
            "CLOUDINARY_URL": "cloudinary://key:secret@cloud"
        }, clear=True), \
             patch('api.admin.upload._upload_to_vercel_blob', return_value="https://blob.vercel-storage.com/image.png") as mock_blob, \
             patch('api.admin.upload._upload_to_cloudinary') as mock_cloud:
            url = _upload_file(file_data, "png", "test.png")
        mock_blob.assert_called_once()
        mock_cloud.assert_not_called()
        self.assertEqual(url, "https://blob.vercel-storage.com/image.png")

    def test_falls_back_to_cloudinary_on_blob_failure(self):
        """When Vercel Blob fails and CLOUDINARY_URL is set, falls back to Cloudinary."""
        file_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        with patch.dict(os.environ, {
            "BLOB_READ_WRITE_TOKEN": "token",
            "CLOUDINARY_URL": "cloudinary://key:secret@cloud"
        }, clear=True), \
             patch('api.admin.upload._upload_to_vercel_blob', return_value=None), \
             patch('api.admin.upload._upload_to_cloudinary', return_value="https://res.cloudinary.com/cloud/image.png") as mock_cloud:
            url = _upload_file(file_data, "png", "test.png")
        mock_cloud.assert_called_once()
        self.assertEqual(url, "https://res.cloudinary.com/cloud/image.png")

    def test_falls_back_to_local_on_blob_failure(self):
        """When Vercel Blob fails (no Cloudinary), falls back to local storage."""
        file_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        with patch.dict(os.environ, {"BLOB_READ_WRITE_TOKEN": "token"}, clear=True), \
             patch('api.admin.upload._upload_to_vercel_blob', return_value=None), \
             patch('api.admin.upload.UPLOADS_DIR', self.temp_dir):
            url = _upload_file(file_data, "png", "test.png")
        self.assertTrue(url.startswith("/uploads/"))

    def test_save_locally_creates_file(self):
        """_save_locally creates file in UPLOADS_DIR and returns relative path."""
        file_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        with patch('api.admin.upload.UPLOADS_DIR', self.temp_dir):
            url = _save_locally(file_data, "png")
        self.assertTrue(url.startswith("/uploads/"))
        self.assertTrue(url.endswith(".png"))
        files = os.listdir(self.temp_dir)
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.temp_dir, files[0]), 'rb') as f:
            self.assertEqual(f.read(), file_data)


if __name__ == '__main__':
    unittest.main()


class TestMultipartUpload(unittest.TestCase):
    """Tests for multipart form data upload handling."""

    def setUp(self):
        """Create a temporary uploads directory."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Remove temporary uploads directory."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _build_multipart_body(self, file_data, filename, content_type):
        """Build a multipart/form-data body with a file field."""
        boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
        body = (
            f"------WebKitFormBoundary7MA4YWxkTrZu0gW\r\n"
            f"Content-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8") + file_data + b"\r\n------WebKitFormBoundary7MA4YWxkTrZu0gW--\r\n"
        return body, f"multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW"

    def _call_handler_multipart(self, file_data, filename, content_type):
        """Call _handle_post with multipart form data."""
        from api.admin.upload import _handle_post

        body, content_type_header = self._build_multipart_body(file_data, filename, content_type)

        mock = MockHandler(None)
        mock.headers = {
            "Content-Type": content_type_header,
            "Content-Length": str(len(body)),
        }
        mock.rfile = BytesIO(body)

        with patch('api.admin.upload.UPLOADS_DIR', self.temp_dir):
            _handle_post(mock)
        return mock

    def test_multipart_png_upload(self):
        """Valid PNG upload via multipart returns success."""
        file_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock = self._call_handler_multipart(file_data, "test.png", "image/png")
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")
        self.assertIn("image_url", response["data"])

    def test_multipart_jpeg_upload(self):
        """Valid JPEG upload via multipart returns success."""
        file_data = b'\xff\xd8\xff\xe0' + b'\x00' * 100
        mock = self._call_handler_multipart(file_data, "photo.jpg", "image/jpeg")
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")

    def test_multipart_webp_upload(self):
        """Valid WebP upload via multipart returns success."""
        file_data = b'RIFF' + b'\x00' * 100
        mock = self._call_handler_multipart(file_data, "image.webp", "image/webp")
        self.assertEqual(mock.response_status, 200)
        response = mock.get_response()
        self.assertEqual(response["status"], "success")

    def test_multipart_invalid_format_rejected(self):
        """GIF file via multipart is rejected."""
        file_data = b'GIF89a' + b'\x00' * 100
        mock = self._call_handler_multipart(file_data, "anim.gif", "image/gif")
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "INVALID_IMAGE")

    def test_multipart_oversized_rejected(self):
        """File exceeding 5 MB via multipart is rejected."""
        file_data = b'\x00' * (MAX_FILE_SIZE + 1)
        mock = self._call_handler_multipart(file_data, "large.png", "image/png")
        self.assertEqual(mock.response_status, 400)
        response = mock.get_response()
        self.assertEqual(response["code"], "INVALID_IMAGE")
        self.assertEqual(response["message"], "파일 형식 또는 크기가 올바르지 않습니다.")

    def test_multipart_file_saved_to_disk(self):
        """Multipart upload saves file to uploads directory."""
        original_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        mock = self._call_handler_multipart(original_data, "save.png", "image/png")
        self.assertEqual(mock.response_status, 200)
        files = os.listdir(self.temp_dir)
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.temp_dir, files[0]), 'rb') as f:
            saved = f.read()
        self.assertEqual(saved, original_data)


if __name__ == '__main__':
    unittest.main()
