# Windows 环境配置参考

## 目录结构约定

推荐把 skill、上游工具和隔离依赖放在同一个工作区：

```text
<workspace>/
  Claude-obsidian-wiki-skill/
  .tools/wechat-article-for-ai/
  .python-packages/
```

`wiki_ingest_wechat.py` 默认会从当前工作区查找 `.tools/wechat-article-for-ai`。如果上游工具放在别处，使用 `--tool-dir` 或环境变量 `WECHAT_ARTICLE_FOR_AI_DIR`。

当前来源依赖建议理解成三类：

- 微信 URL：`wechat-article-for-ai`
- 通用网页 URL：`baoyu-url-to-markdown`
- YouTube / Bilibili URL：`yt-dlp`，无字幕时再加 `faster-whisper`
- 抖音 URL：`yt-dlp`，cookie 失败时浏览器兜底需 `Node.js` + `playwright`
- 本地文档（DOCX/PPTX/XLSX/EPUB）：`markitdown` + `pandas` + `openpyxl` + `ebooklib` + `beautifulsoup4`

推荐再按”必装 / 按需装”区分：

- 必装
  - `wechat-article-for-ai`
  - `pypdf`
- 网页来源按需装
  - `baoyu-url-to-markdown`
- 视频来源按需装
  - `yt-dlp`
- 无字幕视频按需装
  - `faster-whisper`
- 抖音视频浏览器兜底按需装
  - `Node.js` + `playwright`（npm 包）
- 文档格式归一化按需装
  - `markitdown` + `pandas` + `openpyxl` + `ebooklib` + `beautifulsoup4`

## 前置条件

- Windows + PowerShell
- Python with `pip`
- Git
- Obsidian Desktop 已至少打开/登记过一个 vault
- 网络可访问 GitHub、PyPI、Camoufox release 下载地址和 `mp.weixin.qq.com`

上游 `wechat-article-for-ai` 主要依赖来自其 `requirements.txt`：`camoufox[geoip]`、`markdownify`、`beautifulsoup4`、`httpx`、`mcp`。本 skill 实测建议额外安装 `chardet`，用于避免 Windows 下 `requests` 字符集后备告警。

如果你要启用网页和视频来源，还建议准备：

- `baoyu-url-to-markdown`
- `yt-dlp`
- `faster-whisper`

## 关于 Obsidian “准确性”

这套方案不会天然削弱 Obsidian 对原文的索引能力，因为原始文章仍然完整存放在 `raw/articles/` 中，Obsidian 依然会对它们做全文搜索和图谱管理。

真正新增的是一层 AI 编译结果：

- `wiki/briefs/`：更快浏览，但有损。
- `wiki/sources/`：更适合问答和建立关联，但仍不是最终证据。
- `wiki/syntheses/`：把同一主题域的近期来源先汇总到一个可持续演化的入口页。
- `raw/articles/`：最终证据。

因此收益不是“替代 Obsidian”，而是：

- 降低人和 AI 读取长文的成本
- 把跨文档链接、候选概念和候选实体显式化，同时避免一次性名词直接污染图谱
- 让后续 query/lint 只需先看 `wiki/index.md`

如果你发现 Obsidian 原生全局图里 `index.md`、`log.md`、`sources/`、`briefs/` 太吵，不要直接放弃图谱。这个仓库提供了一个主图谱导出脚本：

```powershell
python Claude-obsidian-wiki-skill\scripts\export_main_graph.py `
  --vault "D:\Obsidian\MyVault"
```

运行后会生成 `wiki/graph-view.md`。建议先在 Obsidian 里打开这个页面，把它当作“项目主图谱入口”；需要更强交互时，再按页面里给出的过滤规则打开 Obsidian 原生图谱。

风险只会在一种情况下出现：如果查询时只看 `briefs/` 而不回看 `raw`。所以需要遵守 `AGENTS.md` 里的 query rules。

## Obsidian Vault 自动发现

Windows 下默认读取：

```text
%APPDATA%\obsidian\obsidian.json
```

发现规则：

1. 优先使用唯一一个 `open: true` 且路径存在的 vault。
2. 如果没有打开中的 vault，但只有一个已登记且存在的 vault，则使用它。
3. 如果存在多个候选或无法读取配置，必须传 `--vault`。

### 多 Vault 注册与域优先自动路由

`~/.claude/obsidian-wiki/vaults.json` 是多 vault 注册表，替代了旧的单行 `vault.conf`：

```json
[
  {"path": "D:\\Wiki\\ObsidianVault", "name": "ObsidianVault", "default": true},
  {"path": "D:\\Wiki\\社科Vault", "name": "社科Vault", "default": false}
]
```

Vault 选择的优先链：

1. 显式 `--vault <path>` 参数（最高）
2. **域优先自动路由**：`resolve_vault(article_domains=...)` 匹配内容域与各 vault `purpose.md` 关注领域，选择重叠度最高的 vault
3. `vaults.json` 中标记 `"default": true` 的条目
4. 旧版 `vault.conf` 单行路径（向后兼容）
5. Obsidian `obsidian.json` 自动发现（兜底）

当内容被自动路由到非默认 vault 时，`wiki_ingest.py` 输出 `Auto-routed to vault: <path> (matched domains: ...)` 到 stderr，你应据此选择后续操作的目标 vault。

手动覆盖示例：

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_ingest.py `
  --vault "D:\Wiki\社科Vault" `
  "https://www.bilibili.com/video/BV1vE411e7R3/"
```

### purpose.md 域路由配置

每个 vault 可以在根目录放一个 `purpose.md`，声明该 vault 的关注领域和排除范围。`resolve_vault(article_domains=...)` 会匹配文章域与各 vault 的关注领域，选择重叠度最高的 vault。

`purpose.md` 格式：

```markdown
---
type: "purpose"
---

# Vault 用途

## 关注领域
- 自动驾驶
- 机器人
- 端到端学习

## 排除范围
- 金融投资
- 娱乐
```

- `## 关注领域` 下的条目用于域匹配：文章的 `detect_domains()` 结果与这些条目做子串双向匹配
- `## 排除范围` 下的条目当前仅作文档用途，不参与路由决策
- 如果某个 vault 没有 `purpose.md`，该 vault 不参与域路由（但仍是 default vault 候选）

### 注册新 Vault

1. 创建 `~/.claude/obsidian-wiki/vaults.json`（如不存在）：
   ```powershell
   if (!(Test-Path "$env:USERPROFILE\.claude\obsidian-wiki")) { mkdir "$env:USERPROFILE\.claude\obsidian-wiki" }
   ```
2. 添加新 vault 条目到 JSON 数组：
   ```json
   [
     {"path": "D:\\Wiki\\ObsidianVault", "name": "ObsidianVault", "default": true},
     {"path": "D:\\Wiki\\社科Vault", "name": "社科Vault", "default": false}
   ]
   ```
3. （可选）在新 vault 根目录创建 `purpose.md`，声明关注领域
4. 验证：`python scripts/wiki_ingest.py --help` 确认无报错

### 从 vault.conf 迁移

如果已有旧版 `~/.claude/obsidian-wiki/vault.conf`（单行路径文件），`load_vault_registry()` 会自动读取并转为 vaults.json 格式。迁移后可删除 vault.conf。

## 依赖安装

推荐使用工作区隔离安装，避免污染全局 Python。

### 自动检查与安装（推荐）

```powershell
# 仅检查依赖状态
python scripts/check_deps.py

# 检查 + 自动安装缺失依赖
python scripts/check_deps.py --install

# 中国无 VPN 环境：使用镜像安装
python scripts/check_deps.py --install --china

# 仅安装特定组的依赖
python scripts/check_deps.py --install --group=wechat
python scripts/check_deps.py --install --group=video
```

依赖分组：`core`（Python/Git）、`wechat`（微信公众号）、`video`（视频）、`video_asr`（无字幕 ASR）、`pdf`（本地 PDF）、`format_normalization`（DOCX/PPTX/XLSX/EPUB 格式归一化）、`web`（通用网页）、`test`（测试套件）。

单独安装 Camoufox 浏览器（中国网络可能需要单独处理）：

```powershell
# 标准路径（自动从 GitHub 下载）
python scripts/check_deps.py --install-camoufox

# 中国镜像路径（通过 ghfast.top 下载）
python scripts/check_deps.py --install-camoufox --china
```

### 手动安装：标准路径 vs 中国镜像

以下按来源类型分组，给出标准路径和中国镜像路径两种安装命令。

镜像地址汇总：

| 镜像服务 | 用途 | 地址 |
|---------|------|------|
| 清华 PyPI | pip 包 | `https://pypi.tuna.tsinghua.edu.cn/simple` |
| npmmirror | npm 包 | `https://registry.npmmirror.com` |
| ghfast.top | GitHub Release / 仓库 | `https://ghfast.top/` |
| hf-mirror | Hugging Face 模型 | `https://hf-mirror.com` |

用法：在原始 GitHub URL 前加 `https://ghfast.top/` 前缀。例如：
- 原始：`https://github.com/daijro/camoufox/releases/download/v135.0.1-beta.24/camoufox-135.0.1-beta.24-win.x86_64.zip`
- 镜像：`https://ghfast.top/https://github.com/daijro/camoufox/releases/download/v135.0.1-beta.24/camoufox-135.0.1-beta.24-win.x86_64.zip`

#### 微信公众号来源（必装）

| 步骤 | 标准路径 | 中国镜像路径 |
|------|---------|------------|
| 克隆工具 | `git clone --depth 1 https://github.com/bzd6661/wechat-article-for-ai.git .tools\wechat-article-for-ai` | `git clone --depth 1 https://ghfast.top/https://github.com/bzd6661/wechat-article-for-ai.git .tools\wechat-article-for-ai` |
| 安装 pip 依赖 | `pip install -r .tools\wechat-article-for-ai\requirements.txt --target .python-packages` | `pip install -r .tools\wechat-article-for-ai\requirements.txt --target .python-packages -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 安装 chardet | `pip install chardet --target .python-packages` | `pip install chardet --target .python-packages -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 安装 Camoufox 浏览器 | `python -m camoufox fetch` | `python scripts/check_deps.py --install-camoufox --china` |

**Camoufox 浏览器安装说明**：

标准路径下，`pip install camoufox[geoip]` 安装的是 Python 包，浏览器二进制 (~530MB) 首次运行时从 GitHub Releases 自动下载。如有 VPN 或直连 GitHub 顺畅，此路径最简单。

中国无 VPN 环境，Camoufox 浏览器和 UBO addon 均无法直接从 GitHub / Mozilla 下载，需要通过 ghfast.top 镜像手动安装。`check_deps.py --install-camoufox --china` 已内置此流程：

1. 通过 `https://ghfast.top/` 前缀下载 Camoufox 浏览器 zip (~530MB)
2. 解压到 `%LOCALAPPDATA%\camoufox\camoufox\Cache\`
3. 写入 `version.json`
4. 通过 `https://ghfast.top/` + GitHub 下载 uBlock Origin XPI addon
5. 解压 XPI 到 `Cache\addons\UBO\`

**重要**：UBO addon 必须在 Camoufox 首次启动前安装完成，否则 Camoufox 检测到 addon 缺失后会清空 Cache 并重新从 GitHub 下载（中国网络下会超时失败）。

如自动安装失败，可手动执行：

```powershell
# 1. 下载浏览器
curl -L -o "%LOCALAPPDATA%\camoufox\camoufox.zip" "https://ghfast.top/https://github.com/daijro/camoufox/releases/download/v135.0.1-beta.24/camoufox-135.0.1-beta.24-win.x86_64.zip"

# 2. 解压到 Cache 目录（删掉 zip 内的 camoufox/ 前缀）
#    目标目录: %LOCALAPPDATA%\camoufox\camoufox\Cache\
#    zip 内结构: camoufox/camoufox.exe, camoufox/xul.dll, ...

# 3. 写入 version.json
#    内容: {"release": "135.0.1", "version": "135.0.1-beta.24"}

# 4. 下载 UBO addon
curl -L -o "%LOCALAPPDATA%\camoufox\ublock-origin.xpi" "https://ghfast.top/https://github.com/gorhill/uBlock/releases/latest/download/uBlock0_1.70.0.firefox.signed.xpi"
#    解压 XPI (本质是 zip) 到 Cache\addons\UBO\

# 5. 验证
python scripts/check_deps.py
```

#### 通用网页来源（按需安装）

两种安装方式：

**方式 1：npm 全局安装**
| 步骤 | 标准路径 | 中国镜像路径 |
|------|---------|------------|
| 安装 baoyu-url-to-markdown | `npm install -g baoyu-url-to-markdown` | `npm install -g baoyu-url-to-markdown --registry=https://registry.npmmirror.com` |

**方式 2：bun 本地运行（推荐，已作为 Claude skill 安装）**

如果 baoyu-url-to-markdown skill 已在 `~/.claude/skills/` 中安装，可直接用 bun 运行：
```powershell
# 检测 bun 是否可用
bun --version

# 验证 baoyu skill 是否存在
bun "$env:USERPROFILE\.claude\skills\baoyu-url-to-markdown\scripts\main.ts" --help

# 设置环境变量让 obsidian-wiki 使用 bun 方式
$env:KWIKI_WEB_ADAPTER_BIN = "bun $env:USERPROFILE\.claude\skills\baoyu-url-to-markdown\scripts\main.ts"
```

#### 视频来源（按需安装）

| 步骤 | 标准路径 | 中国镜像路径 |
|------|---------|------------|
| 安装 yt-dlp | `pip install -U yt-dlp` | `pip install -U yt-dlp -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 安装 ASR | `pip install faster-whisper` | `pip install faster-whisper -i https://pypi.tuna.tsinghua.edu.cn/simple` |

⚠ **faster-whisper 模型权重**首次使用时从 Hugging Face 下载。中国镜像：
```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```

#### 抖音浏览器兜底（按需安装）

当 `yt-dlp` 对抖音 URL 返回 cookie/登录/fresh cookies 类错误时，自动切换到 Playwright 浏览器捕获模式。需要：

| 步骤 | 标准路径 | 中国镜像路径 |
|------|---------|------------|
| 安装 Node.js | https://nodejs.org/ | https://npmmirror.com/mirrors/node/ |
| 安装 Playwright npm 包 | `cd <skill-root> && npm install` | `cd <skill-root> && npm install --registry=https://registry.npmmirror.com` |
| 安装 Chromium 浏览器 | `npx playwright install chromium` | `npx playwright install chromium` |

环境变量（可选）：

```powershell
# 抖音浏览器是否无头模式（默认无头）
$env:KWIKI_DOUYIN_HEADLESS = "0"   # 设为 0 表示有头模式，方便调试

# 自定义 User-Agent
$env:KWIKI_DOUYIN_USER_AGENT = "Mozilla/5.0 ..."

# 自定义 Node.js 路径（如果不在 PATH 中）
$env:KWIKI_NODE_BIN = "D:\node\node.exe"
```

未安装 Node.js / Playwright 时，抖音视频的 `yt-dlp` 仍然可用——浏览器兜底仅在 `yt-dlp` 报 cookie 类错误时触发。

#### 本地 PDF 来源（按需安装）

| 步骤 | 标准路径 | 中国镜像路径 |
|------|---------|------------|
| 安装 pypdf | `pip install pypdf` | `pip install pypdf -i https://pypi.tuna.tsinghua.edu.cn/simple` |

#### 格式归一化（按需安装）

DOCX / PPTX / XLSX / EPUB 文件入库需要以下依赖。未安装时，这些格式的文件将无法入库。

| 步骤 | 标准路径 | 中国镜像路径 |
|------|---------|------------|
| 安装全部格式归一化依赖 | `pip install markitdown pandas openpyxl ebooklib beautifulsoup4` | `pip install markitdown pandas openpyxl ebooklib beautifulsoup4 -i https://pypi.tuna.tsinghua.edu.cn/simple` |

各包用途：
- `markitdown`：DOCX/PPTX → Markdown（Microsoft 出品）
- `pandas` + `openpyxl`：XLSX/XLS 表格 → Markdown
- `ebooklib` + `beautifulsoup4`：EPUB 电子书 → Markdown

快速安装（使用 check_deps.py）：

```powershell
python scripts/check_deps.py --install --group=format_normalization
python scripts/check_deps.py --install --group=format_normalization --china
```

### PDF 生成（Brief / Deep Research 报告导出）

Brief 和 Deep Research 报告的 PDF 导出功能由 `scripts/md_to_pdf.py` 提供（Playwright + Chrome 渲染），由 `scripts/pipeline/pdf_utils.py` 内部调用。用户无需直接接触该脚本。

| 步骤 | 标准路径 | 中国镜像路径 |
|------|---------|------------|
| 安装 Python 包 | `pip install markdown playwright` | `pip install markdown playwright -i https://pypi.tuna.tsinghua.edu.cn/simple` |
| 安装 Chromium | `playwright install chromium` | `playwright install chromium` |

> **注意**：这里的 `playwright` 是 Python 包（PDF 渲染），与抖音视频浏览器兜底使用的 Node.js `playwright` 是两个独立依赖。

### 环境变量设置

安装完成后，设置运行时环境变量：

```powershell
$env:PYTHONPATH = (Resolve-Path ".python-packages").Path
$env:WECHAT_ARTICLE_FOR_AI_DIR = (Resolve-Path ".tools\wechat-article-for-ai").Path
$env:WECHAT_ARTICLE_PYTHONPATH = (Resolve-Path ".python-packages").Path
```

### 快速验证

```powershell
Get-Command python, git, yt-dlp, baoyu-url-to-markdown -ErrorAction SilentlyContinue | Select-Object Name, Source
```

这里只看到部分命令时，不代表工程损坏，只表示对应来源尚未配置。

### 排障

如果网页 adapter 不在 PATH，可显式指定：

```powershell
$env:WECHAT_WIKI_WEB_ADAPTER_BIN = "baoyu-url-to-markdown"
```

如果你要复用当前工作区里 bundled 的 `baoyu-url-to-markdown`，也可以直接指定带参数命令：

```powershell
$env:WECHAT_WIKI_WEB_ADAPTER_BIN = "bun D:\AI\Skill\微信文章归档Obsidian\llm-wiki-skill-main\deps\baoyu-url-to-markdown\scripts\main.ts"
```

如果视频 adapter 不在 PATH，可显式指定：

```powershell
$env:WECHAT_WIKI_VIDEO_ADAPTER_BIN = "yt-dlp"
```

如果 Bilibili / YouTube 需要浏览器态或 cookie，可再配置其中一种：

```powershell
$env:WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER = "chrome"
```

或：

```powershell
$env:WECHAT_WIKI_VIDEO_COOKIES_FILE = "D:\cookies.txt"
```

说明：

- `WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER`
  - 传给 `yt-dlp --cookies-from-browser`
  - 适合直接复用本机已登录浏览器状态
- `WECHAT_WIKI_VIDEO_COOKIES_FILE`
  - 传给 `yt-dlp --cookies`
  - 适合用外部导出的 cookie 文件
- 两者同时设置时，优先使用 `WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER`
- 如果两者都没配，当前工程会默认读取 skill 目录下的 `Claude-obsidian-wiki-skill/cookies.txt`
- 出于信息安全考虑，推荐用户自己维护这个 skill 目录文件，而不是把原始 cookie 文本直接贴到聊天里

如果 `yt-dlp` 报：

- `Could not copy Chrome cookie database`

说明当前进程拿不到 Chromium 的 cookie 数据库，这时不要继续依赖 `WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER`。应改为：

1. 手动导出 Netscape 格式 `cookies.txt`
2. 优先把它放到 `Claude-obsidian-wiki-skill/cookies.txt`
3. 再次运行主入口

如果你不想手动复制，也可以在确认本地文件路径无误后，用安装脚本把外部文件复制到 skill 目录：

```powershell
python Claude-obsidian-wiki-skill\scripts\install_video_cookies.py `
  --source-file "D:\path\to\cookies.txt"
```

当前工程已把这类失败明确提示为优先检查 skill 目录 `cookies.txt`，必要时再改用显式文件安装流程，避免和平台风控或普通网络错误混淆。

如果你只是把 skill 安装进 Codex 或 Claude Code，并通过交互界面使用，那么推荐主路径不是“脚本直连 API”，而是：

1. 先抓取并写入 `raw`
2. 运行 `llm_compile_ingest.py --prepare-only --lean` 生成精简编译上下文（推荐；不加 `--lean` 则输出完整 payload，适合管道到外部 API）
3. 让当前 Codex/Claude 会话基于该上下文生成结构化 JSON
4. 用 `apply_compiled_brief_source.py` 回写 `brief/source`

建议把第 3 步生成的 JSON 形状对齐到：

`Claude-obsidian-wiki-skill\references\examples\agent_interactive_compiled_result.json`

这份示例文件适合在首次安装、调 prompt、或验证回写链路时作为基准。

如果你想把 `--prepare-only --lean` 输出保存到文件，PowerShell 下建议显式写 UTF-8，而不是直接用 `>`：

```powershell
python Claude-obsidian-wiki-skill\scripts\llm_compile_ingest.py `
  --vault "D:\Obsidian\MyVault" `
  --raw "D:\Obsidian\MyVault\raw\articles\<slug>.md" `
  --title "文章标题" `
  --prepare-only --lean | Out-File -LiteralPath ".runtime\compile-payload.json" -Encoding utf8
```

只有在你需要无人值守批处理时，才推荐启用脚本直连的 OpenAI-compatible 接口：

```powershell
$env:WECHAT_WIKI_API_KEY = "你的 API Key"
$env:WECHAT_WIKI_COMPILE_MODEL = "gpt-4.1-mini"
$env:WECHAT_WIKI_API_BASE = "https://api.openai.com/v1"
```

说明：

- 未配置上述变量时，ingest 会自动回退到当前启发式模式。
- 如果你想强制关闭 LLM 编译，可传 `--no-llm-compile`。
- 对于 Codex/Claude 交互式使用，不必配置这些变量。
- 如果你希望整理完正式知识层后刷新主图谱页面，可以在 `apply_compiled_brief_source.py`、`apply_approved_delta.py` 之后手动运行一次 `export_main_graph.py`。

网页来源排障时，当前推荐把失败状态理解成：

- `browser_not_ready`
  - 典型含义：`baoyu-url-to-markdown` 没等到 Chrome CDP 可用
  - 典型信号：`Chrome debug port not ready`
- `network_failed`
  - 典型含义：网页本身不可访问，或 `defuddle.md` fallback 无法连通
  - 典型信号：`Unable to connect`
- `runtime_failed`
  - 典型含义：网页 adapter 执行失败，但不属于上面两类明确问题

视频来源排障时，当前推荐额外关注：

- `platform_blocked`
  - 典型含义：平台侧风控或前置校验拦截了抓取
  - 当前真实样例：Bilibili `HTTP Error 412: Precondition Failed`
  - 这通常意味着需要额外浏览器态、cookie，或平台特定 header，而不是主入口/playlist 路由坏了
  - 当前优先解法是配置：
    - `WECHAT_WIKI_VIDEO_COOKIES_FROM_BROWSER`
    - 或 `WECHAT_WIKI_VIDEO_COOKIES_FILE`

当前来源质量判断建议也遵循两层：

- 第一层：`status`
  - 决定来源是否可进入主链
- 第二层：`quality`
  - 只在 `status == ok` 时使用
  - 推荐使用：
    - `low`
    - `acceptable`
    - `high`

如果只是搭环境或排障，先看 `status`；如果来源已经成功进入 vault，再看 `quality` 是否需要人工复核。

当前实现里，`quality = low` 的来源不会被静默吞掉：

- `review_queue.py --write` 会把它们列到 `低质量来源候选`
- `wiki_lint.py` 会在结果里输出 `low_quality_sources`

这意味着来源虽然可以成功入库，但后续维护流程会把它们主动推回复核视野。

视频来源的当前实现补充说明：

- 视频完整文稿会单独写到 `raw/transcripts/`
- `raw/articles/<slug>.md` 对视频只作为来源总页，链接对应 transcript 页
- Bilibili `danmaku.xml` 不再直接当正文使用
- 当只有弹幕、没有真实字幕时，会优先尝试音频下载 + `faster-whisper` ASR
- `transcript_source = asr` 的来源即使文本较长，当前默认最高只评到 `acceptable`

**抖音浏览器兜底排障**：

如果抖音视频入库失败并返回 `dependency_missing`（"Node.js is required"）：

1. 确认 Node.js 在 PATH 中：`node --version`
2. 安装 Playwright：`cd <skill-root> && npm install && npx playwright install chromium`
3. 确认脚本存在：`<skill-root>/scripts/douyin_browser_capture.js`

如果浏览器捕获成功但 ASR 失败（"ASR dependency missing: faster-whisper"）：

1. 安装 faster-whisper（见上方视频来源安装）
2. 确认 curl 在 PATH 中：`curl --version`

如果浏览器捕获返回 `empty_result`（"found no playable video response"）：

1. 尝试有头模式调试：`$env:KWIKI_DOUYIN_HEADLESS = "0"`
2. 检查是否有 cookies：在 `<skill-root>/scripts/cookies.txt` 放入 Netscape 格式 cookies

如果当前环境没有可用 API，但你想先验证 LLM 编译分支是否走通，可以用 mock 文件：

```powershell
$env:WECHAT_WIKI_COMPILE_MOCK_FILE = (Resolve-Path "Claude-obsidian-wiki-skill\references\examples\compile_mock_response.json").Path
```

说明：

- 设置后，`llm_compile_ingest.py` 会直接读取该 JSON，跳过远程模型调用。
- 这只用于本地链路验证，不代表真实模型质量。

也可以不用环境变量，直接传：

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_ingest_wechat.py `
  --tool-dir ".tools\wechat-article-for-ai" `
  --deps-dir ".python-packages" `
  "https://mp.weixin.qq.com/s/..."
```

当前默认脚本入口已可直接处理：

- 微信 URL
- 通用网页 URL
- YouTube URL
- Bilibili URL
- 本地 Markdown / 文本 / HTML / PDF
- 纯文本粘贴（`--text`）

例如：

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_ingest_wechat.py `
  "D:\notes\sample.md"

python Claude-obsidian-wiki-skill\scripts\wiki_ingest_wechat.py `
  --text "这是直接粘贴进入主入口的文本。"
```

如果你要跑 playlist / 合集 / channel videos 页，当前推荐显式使用保护参数，例如：

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_ingest_wechat.py `
  --vault "D:\Obsidian\MyVault" `
  --collection-limit 5 `
  --collection-delay-seconds 1 `
  --collection-backoff-seconds 5 `
  --collection-jitter-seconds 0.5 `
  --collection-failure-threshold 3 `
  --collection-platform-cooldown-seconds 1800 `
  --no-llm-compile `
  "https://www.youtube.com/playlist?list=..."
```

这些参数的意义是：

- `--collection-limit`
  - 收窄单次处理数量
- `--collection-delay-seconds`
  - 成功项之间的固定等待
- `--collection-backoff-seconds`
  - 失败后的基础退避
- `--collection-jitter-seconds`
  - 在退避基础上增加随机抖动
- `--collection-failure-threshold`
  - 连续失败达到阈值后暂停 job
- `--collection-platform-cooldown-seconds`
  - 暂停后写入冷却截止时间

当批量视频任务被暂停时，`wiki/import-jobs/*.md` 里会出现：

- `status: "paused"`
- `last_failure_reason`
- `cooldown_until`

在 `cooldown_until` 之前再次运行，会直接跳过这个 collection。

## 首次运行

首次真实抓取通常会下载 Camoufox 浏览器资产，体积较大，可能需要数分钟。下载位置由 Camoufox 管理，通常在用户本地缓存目录。

如果 Playwright/Camoufox 子进程被沙箱或权限限制拦截，需要在允许启动子进程和访问网络的环境中运行。

## 常见 Windows 问题

### `python -m venv` / `ensurepip` 失败

如果临时目录权限导致 `ensurepip` 失败，不要依赖 venv，改用：

```powershell
python -m pip install -r .tools\wechat-article-for-ai\requirements.txt --target .python-packages
```

### `.python-packages` 内文件无法读取或 DLL 无法加载

如果 pip 以提权方式安装后普通进程无法读取依赖，修复当前工作区依赖目录权限：

```powershell
icacls .python-packages /grant "Users:(OI)(CI)M" /T
```

### 系统 Temp 权限问题

脚本默认使用工作区 `.runtime-fetch` 作为暂存目录，避免落到 `%TEMP%`。如仍需指定：

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_ingest_wechat.py `
  --work-dir ".runtime-fetch" `
  "https://mp.weixin.qq.com/s/..."
```

### 微信验证码

使用可见浏览器：

```powershell
python Claude-obsidian-wiki-skill\scripts\wiki_ingest_wechat.py --no-headless "https://mp.weixin.qq.com/s/..."
```

### 多个 Obsidian Vault

如果 Obsidian 配置里多个 vault 同时被标记为打开，脚本会停止。此时传 `--vault` 明确目标。

## 验证命令

```powershell
$env:PYTHONPATH = (Resolve-Path ".python-packages").Path
python .tools\wechat-article-for-ai\main.py --help
python Claude-obsidian-wiki-skill\scripts\wiki_ingest_wechat.py --help
python Claude-obsidian-wiki-skill\scripts\llm_compile_ingest.py --help
python Claude-obsidian-wiki-skill\scripts\apply_compiled_brief_source.py --help
python Claude-obsidian-wiki-skill\scripts\export_main_graph.py --vault "D:\Obsidian\MyVault"
python Claude-obsidian-wiki-skill\scripts\wiki_lint.py --vault "D:\Obsidian\MyVault"
python Claude-obsidian-wiki-skill\scripts\wiki_query.py "这篇文章如何看待 AIDV 对 EEA 的冲击？"
python Claude-obsidian-wiki-skill\scripts\wiki_size_report.py --vault "D:\Obsidian\MyVault"
python Claude-obsidian-wiki-skill\scripts\stale_report.py --vault "D:\Obsidian\MyVault"
python Claude-obsidian-wiki-skill\scripts\delta_compile.py --vault "D:\Obsidian\MyVault"
python Claude-obsidian-wiki-skill\scripts\refresh_synthesis.py --vault "D:\Obsidian\MyVault"
```

Skill 校验：

```powershell
$env:PYTHONUTF8 = "1"
python "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" `
  .\Claude-obsidian-wiki-skill
```

