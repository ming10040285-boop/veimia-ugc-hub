# VEIMIA UGC Hub — Deployment Guide

This guide covers deploying the VEIMIA UGC Brand Collaboration Hub to Vercel free tier.

## Prerequisites

Before deploying, ensure you have:

1. **Vercel Account** — Sign up at [vercel.com](https://vercel.com). The free Hobby plan is sufficient.
2. **Vercel CLI** (optional) — Install via `npm i -g vercel` for CLI-based deployments.
3. **Google Cloud Service Account** — Required for Google Sheets integration.
4. **Image Storage Account** (one of):
   - Vercel Blob (included with Vercel, recommended)
   - Cloudinary free tier account at [cloudinary.com](https://cloudinary.com)

---

## 1. Google Cloud Service Account Setup

The Registration Service writes data to Google Sheets via a service account.

### Create the Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Navigate to **APIs & Services > Library**
4. Enable the **Google Sheets API** and **Google Drive API**
5. Navigate to **IAM & Admin > Service Accounts**
6. Click **Create Service Account**
   - Name: `veimia-ugc-hub`
   - Role: none required (access is granted per-spreadsheet)
7. Click on the created service account > **Keys** tab
8. Click **Add Key > Create New Key > JSON**
9. Download the JSON key file — this is your `GOOGLE_SHEETS_CREDENTIALS` value

### Prepare the Google Sheet

1. Create a new Google Sheets spreadsheet
2. Copy the spreadsheet ID from the URL:
   `https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit`
3. Share the spreadsheet with the service account email
   (found in the JSON key file as `client_email`) — grant **Editor** access
4. Add header row (optional but recommended):
   `timestamp | campaign_id | product_id | selected_size | selected_color | instagram_id | name | phone | address | postal_code | consent`

---

## 2. Environment Variable Setup

### Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_SHEETS_CREDENTIALS` | Yes | Full JSON string of the service account key file |
| `GOOGLE_SHEETS_ID` | Yes | Spreadsheet ID from the Google Sheets URL |
| `BLOB_READ_WRITE_TOKEN` | Optional* | Vercel Blob storage token for image uploads |
| `CLOUDINARY_URL` | Optional* | Cloudinary connection URL for image uploads |

*At least one image storage option is needed if using the image upload feature.

### Setting Variables in Vercel Dashboard

1. Go to your project in [Vercel Dashboard](https://vercel.com/dashboard)
2. Navigate to **Settings > Environment Variables**
3. Add each variable:
   - For `GOOGLE_SHEETS_CREDENTIALS`: paste the entire JSON key file content as a single-line string
   - For `GOOGLE_SHEETS_ID`: paste just the spreadsheet ID string
   - For `BLOB_READ_WRITE_TOKEN`: generate from Vercel Storage > Blob
   - For `CLOUDINARY_URL`: copy from Cloudinary Dashboard > Account Details
4. Set the environment scope to **Production**, **Preview**, and **Development** as needed

### Setting Variables via CLI

```bash
vercel env add GOOGLE_SHEETS_CREDENTIALS production
# Paste the JSON content when prompted

vercel env add GOOGLE_SHEETS_ID production
# Paste the spreadsheet ID when prompted

vercel env add BLOB_READ_WRITE_TOKEN production
# Paste the Vercel Blob token when prompted
```

### Local Development

For local development, create a `.env.local` file (git-ignored) from the template:

```bash
cp .env.example .env.local
```

Fill in the values. The Vercel CLI (`vercel dev`) will automatically pick up `.env.local`.

---

## 3. Deploy

### Option A: Git-based Deployment (Recommended)

1. Push your code to GitHub/GitLab/Bitbucket
2. In Vercel Dashboard, click **New Project** and import the repository
3. Set the **Root Directory** to `veimia-ugc-hub` (if it's in a subdirectory)
4. Vercel auto-detects the `vercel.json` configuration
5. Click **Deploy**

Subsequent pushes to the main branch trigger automatic production deployments.

### Option B: CLI Deployment

```bash
cd veimia-ugc-hub

# First-time setup (links to Vercel project)
vercel link

# Deploy to preview
vercel

# Deploy to production
vercel --prod
```

### Build Configuration

The project uses `vercel.json` with the following build setup:
- **Python serverless functions**: `api/**/*.py` using `@vercel/python` (Python 3.12, 10s max duration)
- **Static assets**: `public/**` served via Vercel CDN

No build step is required — static files are served as-is and Python functions are bundled automatically.

---

## 4. Custom Domain Setup

### Via Vercel Dashboard

1. Go to **Settings > Domains** in your Vercel project
2. Click **Add Domain**
3. Enter your domain (e.g., `ugc.veimia.com`)
4. Follow the DNS configuration instructions:
   - **CNAME record**: Point your domain to `cname.vercel-dns.com`
   - Or **A record**: Point to `76.76.21.21`
5. Vercel automatically provisions an SSL certificate

### Via CLI

```bash
vercel domains add ugc.veimia.com
```

Then configure DNS at your domain registrar as instructed.

### DNS Propagation

DNS changes can take up to 48 hours to propagate. Vercel provides a verification check in the Dashboard.

---

## 5. Verifying Deployment

### Check HTTPS Access

```bash
# Verify the campaign page loads over HTTPS
curl -sI https://your-project.vercel.app | head -5
# Should return: HTTP/2 200
```

### Check Response Time (<5s requirement)

```bash
# Measure campaign page response time
curl -o /dev/null -s -w "Total time: %{time_total}s\n" https://your-project.vercel.app
# Should be under 5 seconds

# Test from multiple regions if needed
curl -o /dev/null -s -w "DNS: %{time_namelookup}s | Connect: %{time_connect}s | Total: %{time_total}s\n" https://your-project.vercel.app
```

### Check Deployment Size (<100 MB)

```bash
# Check local project size (approximate deployment size)
# On Windows:
powershell -Command "Get-ChildItem -Recurse -File | Where-Object { $_.FullName -notmatch '(node_modules|\.git|__pycache__|\.pytest_cache)' } | Measure-Object -Property Length -Sum | Select-Object @{N='SizeMB';E={[math]::Round($_.Sum/1MB, 2)}}"

# On Linux/Mac:
du -sh --exclude=node_modules --exclude=.git --exclude=__pycache__ .
```

Vercel Dashboard also shows the deployment size under **Deployments > [latest] > Build Logs**.

The deployment should be well under 100 MB since the project uses:
- Static HTML/CSS/JS (minimal)
- JSON config files
- Python serverless functions (bundled with dependencies)

### Verify Serverless Functions

```bash
# Test registration endpoint responds
curl -X POST https://your-project.vercel.app/api/register \
  -H "Content-Type: application/json" \
  -d '{"campaign_id":"test"}' \
  -w "\nHTTP Status: %{http_code}\n"
# Should return 400 with validation error (expected for incomplete data)

# Test admin API responds
curl https://your-project.vercel.app/api/admin/campaigns \
  -w "\nHTTP Status: %{http_code}\n"
```

### Verify Google Sheets Connection

1. Submit a test registration through the campaign page
2. Check the Google Sheet for the new row
3. If it fails, check Vercel function logs: **Dashboard > Deployments > Functions > Logs**

---

## 6. Production Considerations

### Security

- **Never commit `.env.local` or credentials** — the `.gitignore` should exclude these
- **Rotate service account keys** periodically via Google Cloud Console
- **Use Vercel's environment variable encryption** — all values are encrypted at rest
- **CORS**: The `vercel.json` can be extended with headers for CORS if needed

### Monitoring

- **Vercel Analytics**: Enable in Dashboard for page performance metrics
- **Function Logs**: Available in Dashboard under Deployments > Functions
- **Google Sheets quota**: Free tier allows 300 requests per minute per project
  - The retry logic (3 attempts, 5s timeout) handles transient failures
  - Monitor for persistent failures in function logs

### Performance

- Static assets are served via Vercel's global CDN with automatic caching
- Serverless functions have a 10-second timeout configured in `vercel.json`
- Campaign page loads are fast (<5s) since they only require static file serving + 1 JSON fetch
- Consider adding `Cache-Control` headers for JSON config files if they don't change frequently

### Scaling

- Vercel free tier limits:
  - 100 GB bandwidth/month
  - 100,000 serverless function invocations/month
  - 10s function execution time
  - 100 MB deployment size
- For higher traffic, upgrade to Vercel Pro or implement caching strategies

### Backup

- Google Sheets data is automatically backed up by Google
- The Excel sync (`openpyxl`) provides an additional local backup
- Campaign config JSON files are version-controlled in Git

### Troubleshooting

| Issue | Solution |
|-------|----------|
| Function timeout (504) | Check Google Sheets API latency; ensure retry logic works correctly |
| SHEETS_UNAVAILABLE (503) | Verify service account has Editor access to the spreadsheet |
| Image upload fails | Confirm `BLOB_READ_WRITE_TOKEN` or `CLOUDINARY_URL` is set |
| Custom domain not working | Verify DNS records; check Vercel domain verification status |
| Deployment size exceeded | Remove unnecessary files; check `__pycache__` is git-ignored |
