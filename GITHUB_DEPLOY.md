# 通过 GitHub 部署到 Vercel（让 Python API 工作）

## 为什么需要 GitHub 部署？

拖拽部署只支持静态文件，**不支持 Python Serverless Functions**。
通过 GitHub 连接 Vercel，API 端点（`/api/register` 等）才能正常工作。

## 操作步骤

### 1. 创建 GitHub 仓库

```bash
# 在工作区目录下执行
cd "C:\Users\Administrator\Desktop\抓取粉丝数\veimia-ugc-hub"

git init
git add .
git commit -m "Initial commit: VEIMIA UGC Hub with API"
```

然后在 GitHub 网站创建一个新仓库（例如 `veimia-ugc-hub`），然后：

```bash
git remote add origin https://github.com/你的用户名/veimia-ugc-hub.git
git branch -M main
git push -u origin main
```

### 2. 在 Vercel 连接 GitHub 仓库

1. 打开 https://vercel.com/dashboard
2. 点击 "Add New..." → "Project"
3. 选择 "Import Git Repository"
4. 选择你刚推送的 `veimia-ugc-hub` 仓库
5. **Framework Preset**: 选 "Other"
6. **Root Directory**: 保持默认（项目根目录）
7. 点击 "Deploy"

### 3. 配置环境变量（Google Sheets 连接）

在 Vercel 项目的 Settings → Environment Variables 中添加：

| Key | Value |
|-----|-------|
| `GOOGLE_SHEETS_CREDENTIALS` | Google Service Account JSON（完整内容，一行） |
| `GOOGLE_SHEETS_ID` | Google Sheets 的 spreadsheet ID |

#### 获取 Google Sheets 凭据：

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建项目或选择已有项目
3. 启用 Google Sheets API 和 Google Drive API
4. 创建 Service Account → 下载 JSON 密钥
5. 把 JSON 文件内容粘贴到 `GOOGLE_SHEETS_CREDENTIALS` 环境变量
6. 创建一个 Google Sheets 表格
7. 把 Service Account 的 email（在 JSON 的 `client_email` 字段）添加为表格的编辑者
8. 从表格 URL 中获取 ID：`https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`

### 4. 部署完成后

- 线上地址保持不变：`https://veimia-ugc-hub.vercel.app/`
- API 端点现在可以工作：`https://veimia-ugc-hub.vercel.app/api/register`
- 每次 push 到 main 分支会自动部署

### 5. 后续更新流程

```bash
# 修改代码后
git add .
git commit -m "你的更新说明"
git push
# Vercel 会自动部署
```

## 项目结构（Vercel 需要）

```
veimia-ugc-hub/
├── api/                  ← Python Serverless Functions
│   ├── register.py       ← POST /api/register
│   ├── admin/            ← Admin API endpoints
│   └── utils/            ← Shared utilities
├── public/               ← 静态文件（前端）
│   ├── index.html        ← 主页
│   ├── css/
│   ├── js/
│   ├── i18n/
│   ├── config/           ← Campaign JSON configs
│   └── admin/            ← Admin 后台
├── vercel.json           ← Vercel 路由和构建配置
├── requirements.txt      ← Python 依赖
└── .gitignore
```

## 注意事项

- `vercel.json` 已经配置好了 Python 3.12 runtime 和路由规则
- `requirements.txt` 已经包含 `gspread`、`google-auth`、`openpyxl` 依赖
- API 函数超时限制为 10 秒（Vercel 免费版）
- 数据保存到 Google Sheets，不需要数据库
