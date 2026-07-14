"""Image upload API endpoint for VEIMIA UGC Hub Admin.

Timeout: Vercel enforces a 10s maximum execution time via vercel.json maxDuration.
         External uploads (Vercel Blob, Cloudinary) may approach this limit for large files.

Handles POST for image file upload with validation:
- Accepted formats: PNG, JPG/JPEG, WebP
- Maximum file size: 5 MB (5,242,880 bytes)

Supports two upload methods:
1. Multipart form data (standard file upload from HTML forms)
2. JSON body with base64-encoded data (programmatic uploads)

Storage priority:
1. If BLOB_READ_WRITE_TOKEN env var is set → upload to Vercel Blob
2. Fallback: save to local public/uploads/ directory for development
# TODO: Add Cloudinary integration as alternative storage backend
#       Set CLOUDINARY_URL env var in format: cloudinary://api_key:api_secret@cloud_name

Multipart form data format:
  POST /api/admin/upload
  Content-Type: multipart/form-data
  Body: file field named "file"

JSON body format:
{
    "filename": "product.png",
    "data": "base64...",
    "content_type": "image/png"
}

Returns:
- Success: {"status": "success", "data": {"image_url": "https://..."}}
- Error: {"status": "error", "code": "INVALID_IMAGE", "message": "파일 형식 또는 크기가 올바르지 않습니다."}
"""

from http.server import BaseHTTPRequestHandler
import json
import os
import uuid
import base64
import cgi
import io

# Max file size: 5 MB
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5,242,880 bytes

# Accepted content types mapped to file extensions
ACCEPTED_CONTENT_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

# Accepted file extensions (mapped to canonical extension)
ACCEPTED_EXTENSIONS = {
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpg",
    ".webp": "webp",
}

# Content type lookup by extension (for upload APIs)
EXTENSION_TO_CONTENT_TYPE = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
}

# Resolve uploads directory relative to this file (fallback storage)
UPLOADS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "public", "uploads"
)
UPLOADS_DIR = os.path.normpath(UPLOADS_DIR)


def _json_response(handler, status_code, body):
    """Send a JSON response with the given status code and body dict."""
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.end_headers()
    handler.wfile.write(json.dumps(body, ensure_ascii=False).encode("utf-8"))


def _error_response(handler, status_code, code, message):
    """Send a standardized error response."""
    _json_response(handler, status_code, {
        "status": "error",
        "code": code,
        "message": message
    })


def _read_body(handler):
    """Read and parse JSON body from request."""
    content_length = int(handler.headers.get("Content-Length", 0))
    if content_length == 0:
        return None
    raw = handler.rfile.read(content_length)
    return json.loads(raw.decode("utf-8"))


def _parse_multipart(handler):
    """Parse multipart form data from the request.

    Returns (file_data, filename, content_type) tuple or (None, None, None) on failure.
    Expects a file field named 'file' in the form data.
    """
    content_type_header = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type_header:
        return None, None, None

    try:
        # Parse the multipart form data using cgi module
        content_length = int(handler.headers.get("Content-Length", 0))
        if content_length == 0:
            return None, None, None

        # Create environment dict for cgi.FieldStorage
        environ = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type_header,
            "CONTENT_LENGTH": str(content_length),
        }

        # Read the raw body for multipart parsing
        body = handler.rfile.read(content_length)
        body_file = io.BytesIO(body)

        form = cgi.FieldStorage(
            fp=body_file,
            environ=environ,
            headers=handler.headers,
            keep_blank_values=True
        )

        # Look for 'file' field in the form data
        if "file" not in form:
            return None, None, None

        file_item = form["file"]
        if not file_item.file:
            return None, None, None

        file_data = file_item.file.read()
        filename = file_item.filename or ""
        file_content_type = file_item.type or ""

        return file_data, filename, file_content_type
    except Exception:
        return None, None, None


def _get_extension_from_filename(filename):
    """Extract and validate file extension from filename."""
    if not filename:
        return None
    _, ext = os.path.splitext(filename.lower())
    return ACCEPTED_EXTENSIONS.get(ext)


def _get_extension_from_content_type(content_type):
    """Get file extension from content type."""
    if not content_type:
        return None
    return ACCEPTED_CONTENT_TYPES.get(content_type.lower())


def _upload_to_cloudinary(file_data, ext, filename):
    """Upload file to Cloudinary. Returns the image URL or None on failure.

    Requires CLOUDINARY_URL env var in format:
    cloudinary://api_key:api_secret@cloud_name

    TODO: Cloudinary integration as alternative storage backend.
    To enable:
    1. Install cloudinary package: pip install cloudinary
    2. Set CLOUDINARY_URL environment variable
    3. This function will automatically be used as a storage option
    """
    try:
        import cloudinary
        import cloudinary.uploader

        # cloudinary auto-configures from CLOUDINARY_URL env var
        cloudinary_url = os.environ.get("CLOUDINARY_URL", "")
        if not cloudinary_url:
            return None

        # Parse CLOUDINARY_URL and configure
        cloudinary.config(cloudinary_url=cloudinary_url)

        # Upload with a unique public_id
        file_id = str(uuid.uuid4())
        content_type = EXTENSION_TO_CONTENT_TYPE.get(ext, "image/png")

        # Upload using base64 data URI
        data_uri = f"data:{content_type};base64,{base64.b64encode(file_data).decode('ascii')}"
        result = cloudinary.uploader.upload(
            data_uri,
            public_id=f"veimia-ugc/{file_id}",
            resource_type="image"
        )
        return result.get("secure_url") or result.get("url")
    except Exception:
        return None


def _upload_to_vercel_blob(file_data, ext, filename):
    """Upload file to Vercel Blob storage. Returns the image URL or None on failure.

    Requires BLOB_READ_WRITE_TOKEN env var.
    Uses the Vercel Blob REST API.
    """
    try:
        import urllib.request
        import urllib.error

        token = os.environ.get("BLOB_READ_WRITE_TOKEN", "")
        if not token:
            return None

        file_id = str(uuid.uuid4())
        blob_filename = f"{file_id}.{ext}"
        content_type = EXTENSION_TO_CONTENT_TYPE.get(ext, "image/png")

        # Vercel Blob PUT API
        url = f"https://blob.vercel-storage.com/{blob_filename}"
        req = urllib.request.Request(
            url,
            data=file_data,
            method="PUT",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type,
                "x-api-version": "7",
                "x-content-type": content_type,
            }
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("url")
    except Exception:
        return None


def _save_locally(file_data, ext):
    """Save file to local public/uploads/ directory. Returns the relative URL."""
    file_id = str(uuid.uuid4())
    output_filename = f"{file_id}.{ext}"

    # Ensure uploads directory exists
    os.makedirs(UPLOADS_DIR, exist_ok=True)

    # Save file
    output_path = os.path.join(UPLOADS_DIR, output_filename)
    with open(output_path, "wb") as f:
        f.write(file_data)

    return f"/uploads/{output_filename}"


def _upload_file(file_data, ext, filename):
    """Upload file using the appropriate storage backend.

    Priority:
    1. Vercel Blob (if BLOB_READ_WRITE_TOKEN is set)
    2. Cloudinary (if CLOUDINARY_URL is set)
       # TODO: Enable Cloudinary as alternative when package is installed
    3. Local filesystem (fallback for development)

    Returns the image URL string.
    """
    # Try Vercel Blob first (primary cloud storage)
    if os.environ.get("BLOB_READ_WRITE_TOKEN"):
        url = _upload_to_vercel_blob(file_data, ext, filename)
        if url:
            return url

    # TODO: Try Cloudinary as alternative cloud storage
    # Uncomment when cloudinary package is installed and configured
    if os.environ.get("CLOUDINARY_URL"):
        url = _upload_to_cloudinary(file_data, ext, filename)
        if url:
            return url

    # Fallback to local storage (development mode)
    return _save_locally(file_data, ext)


def _handle_post(handler):
    """Handle POST - Upload an image file.

    Supports two upload methods:
    1. Multipart form data (Content-Type: multipart/form-data) with a 'file' field
    2. JSON body with base64-encoded data (Content-Type: application/json)
    """
    content_type_header = handler.headers.get("Content-Type", "")

    # Determine upload method based on Content-Type header
    if "multipart/form-data" in content_type_header:
        # Parse multipart form data
        file_data, filename, content_type = _parse_multipart(handler)
        if file_data is None:
            _error_response(handler, 400, "INVALID_IMAGE",
                            "파일 형식 또는 크기가 올바르지 않습니다.")
            return

        # Determine file extension from content_type or filename
        ext = _get_extension_from_content_type(content_type)
        if not ext:
            ext = _get_extension_from_filename(filename)

        # If neither content_type nor filename gives a valid format, reject
        if not ext:
            _error_response(handler, 400, "INVALID_IMAGE",
                            "파일 형식 또는 크기가 올바르지 않습니다.")
            return

        # Validate file size (max 5 MB)
        if len(file_data) > MAX_FILE_SIZE:
            _error_response(handler, 400, "INVALID_IMAGE",
                            "파일 형식 또는 크기가 올바르지 않습니다.")
            return

        # Upload to appropriate storage
        image_url = _upload_file(file_data, ext, filename)
        _json_response(handler, 200, {
            "status": "success",
            "data": {"image_url": image_url}
        })
    else:
        # JSON body with base64-encoded data
        body = _read_body(handler)
        if not body:
            _error_response(handler, 400, "INVALID_IMAGE",
                            "파일 형식 또는 크기가 올바르지 않습니다.")
            return

        filename = body.get("filename", "")
        data_b64 = body.get("data", "")
        content_type = body.get("content_type", "")

        # Validate that data is provided
        if not data_b64:
            _error_response(handler, 400, "INVALID_IMAGE",
                            "파일 형식 또는 크기가 올바르지 않습니다.")
            return

        # Determine file extension from content_type or filename
        ext = _get_extension_from_content_type(content_type)
        if not ext:
            ext = _get_extension_from_filename(filename)

        # If neither content_type nor filename gives a valid format, reject
        if not ext:
            _error_response(handler, 400, "INVALID_IMAGE",
                            "파일 형식 또는 크기가 올바르지 않습니다.")
            return

        # Decode base64 data
        try:
            file_data = base64.b64decode(data_b64)
        except Exception:
            _error_response(handler, 400, "INVALID_IMAGE",
                            "파일 형식 또는 크기가 올바르지 않습니다.")
            return

        # Validate file size (max 5 MB)
        if len(file_data) > MAX_FILE_SIZE:
            _error_response(handler, 400, "INVALID_IMAGE",
                            "파일 형식 또는 크기가 올바르지 않습니다.")
            return

        # Upload to appropriate storage
        image_url = _upload_file(file_data, ext, filename)

        _json_response(handler, 200, {
            "status": "success",
            "data": {"image_url": image_url}
        })


class handler(BaseHTTPRequestHandler):
    """Vercel serverless function handler for image upload."""

    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        _handle_post(self)
