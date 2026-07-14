# Data Model — VEIMIA UGC Hub

This document defines all data model interfaces, field constraints, and JSON schema conventions used by the VEIMIA UGC Brand Collaboration Hub.

## Product Library (`/public/config/products/library.json`)

Central product store managed by the Admin API. Products here serve as defaults for campaign assignments.

### Product Fields

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `product_id` | string | Yes | Non-empty, unique identifier |
| `product_name` | string | Yes | Max 200 characters |
| `product_image_url` | string (URI) | Yes | Valid http/https URL, max 2048 characters |
| `product_detail_url` | string \| null | No | Valid http/https URL, max 2048 characters, or null |
| `size_guide_url` | string \| null | No | Valid http/https URL, max 2048 characters, or null |
| `short_description` | string | Yes | Max 500 characters |
| `available_sizes` | string[] | Yes | 1–20 items, each non-empty string |
| `available_colors` | string[] | Yes | 1–30 items, each non-empty string |

---

## Campaign Config (`/public/config/campaigns/{campaign_id}.json`)

Each campaign is stored as a separate JSON file. Created and managed by the Admin API.

### CampaignConfig Fields

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `campaign_id` | string | Yes | UUID v4 format |
| `campaign_name` | string | Yes | Max 200 characters |
| `product_mode` | string | Yes | Enum: `"single"` \| `"multiple"` |
| `market` | string | Yes | Enum: `"ko"` \| `"ja"` \| `"en"` |
| `hero_image_url` | string (URI) | Yes | Valid http/https URL, max 2048 characters |
| `introduction_text` | string | Yes | Max 2000 characters |
| `status` | string | Yes | Enum: `"draft"` \| `"published"` |
| `created_at` | string | Yes | ISO 8601 UTC (e.g. `2025-01-15T09:00:00Z`) |
| `updated_at` | string | Yes | ISO 8601 UTC (e.g. `2025-01-15T09:00:00Z`) |
| `products` | CampaignProduct[] | Yes | 1 item (single mode), 1–50 items (multiple mode) |
| `ugc_gallery` | UGCPost[] | Yes | 0–20 items |

### CampaignProduct Fields

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `product_id` | string | Yes | References Product_Library product_id |
| `product_name` | string | Yes | Max 200 characters |
| `product_image_url` | string (URI) | Yes | Valid http/https URL, max 2048 characters |
| `short_description` | string | Yes | Max 500 characters |
| `product_detail_url` | string \| null | No | Valid http/https URL, max 2048 characters, or null |
| `size_guide_url` | string \| null | No | Valid http/https URL, max 2048 characters, or null |
| `available_sizes` | string[] | Yes | 1–20 items |
| `available_colors` | string[] | Yes | 1–30 items |
| `status` | string | Yes | Enum: `"open"` \| `"closed"` |
| `display_order` | integer | Yes | Range: 1–50 |
| `override_product_image_url` | string \| null | No | Valid http/https URL, max 2048 chars. Null = use library default |
| `override_product_detail_url` | string \| null | No | Valid http/https URL, max 2048 chars. Null = use library default |
| `override_size_guide_url` | string \| null | No | Valid http/https URL, max 2048 chars. Null = use library default |
| `override_short_description` | string \| null | No | Max 500 chars. Null = use library default |

### UGCPost Fields

| Field | Type | Required | Constraints |
|-------|------|----------|-------------|
| `post_id` | string | Yes | UUID v4 format |
| `image_url` | string (URI) | Yes | Valid http/https URL, max 2048 characters |
| `source_url` | string \| null | No | Instagram post URL (https://www.instagram.com/p/...) or null |
| `display_order` | integer | Yes | Range: 1–20 |

---

## Field Constraint Summary

### URL Fields
- **Scheme**: Must be `http` or `https` only
- **Max length**: 2048 characters
- **Validation**: Admin API rejects invalid URLs with `INVALID_URL` error (HTTP 400)
- **Frontend behavior**: Buttons hidden for null, invalid scheme, or URLs exceeding 2048 chars

### Text Fields

| Field | Max Length |
|-------|-----------|
| `campaign_name` | 200 chars |
| `product_name` | 200 chars |
| `introduction_text` | 2000 chars |
| `short_description` | 500 chars |
| `override_short_description` | 500 chars |

### Array Fields

| Field | Min Items | Max Items |
|-------|-----------|-----------|
| `available_sizes` | 1 | 20 |
| `available_colors` | 1 | 30 |
| `products` (single mode) | 1 | 1 |
| `products` (multiple mode) | 1 | 50 |
| `ugc_gallery` | 0 | 20 |

### Enum Fields

| Field | Valid Values |
|-------|-------------|
| `product_mode` | `"single"`, `"multiple"` |
| `market` | `"ko"`, `"ja"`, `"en"` |
| `status` (campaign) | `"draft"`, `"published"` |
| `status` (product) | `"open"`, `"closed"` |

### Numeric Fields

| Field | Min | Max | Type |
|-------|-----|-----|------|
| `display_order` (product) | 1 | 50 | integer |
| `display_order` (UGC post) | 1 | 20 | integer |

### Date/Time Fields
- Format: ISO 8601 UTC (e.g. `2025-01-15T09:00:00Z`)
- Fields: `created_at`, `updated_at`

---

## Override Resolution Logic

When rendering a Campaign_Product on the Campaign_Page, fields are resolved as follows:

```
resolved_value = override_value if override_value is not null
                 else product_library_default_value
```

Override-capable fields:
1. `product_image_url` ← `override_product_image_url`
2. `product_detail_url` ← `override_product_detail_url`
3. `size_guide_url` ← `override_size_guide_url`
4. `short_description` ← `override_short_description`

---

## File Organization

```
/public/config/
├── products/
│   └── library.json          # Product Library (all products, initially empty)
├── campaigns/
│   ├── {campaign_id}.json    # One file per campaign
│   └── sample.json           # Reference example
└── DATA_MODEL.md             # This document
```
