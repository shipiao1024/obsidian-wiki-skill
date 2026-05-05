# PDF 输出规范

> **内部参考**：本文档供 LLM 在执行入库或深度研究任务时加载，不作为用户触发条件。PDF 生成由 pipeline 内部自动完成。

Brief 和 Deep Research 报告的 PDF 生成。底层由 `scripts/md_to_pdf.py`（Playwright + Chrome 渲染）提供，`scripts/pipeline/pdf_utils.py` 封装 Obsidian 语法清理 + 调用。

---

## 调用时机（pipeline 内部自动触发）

| 场景 | 调用方 | 说明 |
|------|--------|------|
| 入库完成后 | `pdf_utils.brief_to_pdf()` | 自动为 brief 生成带封面的 PDF |
| Deep Research 完成后 | `pdf_utils.report_to_pdf()` | 自动为研究报告生成带封面的 PDF |

用户无需手动触发。如果 PDF 生成失败（依赖缺失），静默跳过，不影响主流程。

## 依赖

```
pip install markdown playwright
playwright install chromium
```

未安装时 PDF 生成功能静默跳过，不影响入库/查询主流程。

---

## 主题选择

3 个内置主题，pipeline 默认使用 `academic`：

| 主题 | 主色 | 适合场景 |
|------|------|---------|
| `academic`（学术蓝） | #1a5276 深蓝 | 技术报告、学术论文、行业研究、Brief（默认） |
| `tech`（科技青） | #0d9488 青色 teal | 技术方案、架构文档、工程报告 |
| `warm`（暖色） | #92400e 琥珀棕 | 商业报告、产品分析、管理文档 |

用户明确指定主题时可通过 `vault.conf` 或 `pdf_utils.generate_pdf(theme=...)` 覆盖默认。

---

## 参数参考

`pdf_utils.py` 内部调用 `md_to_pdf.py` 时使用的参数（非用户直接接触）：

| 参数 | 说明 | pdf_utils 默认值 |
|------|------|-----------------|
| `--title` | 报告标题（封面 + 页眉） | 从 Markdown 第一个 h1 提取 |
| `--theme` | 主题 | `academic` |
| `--no-cover` | 不生成封面 | `False`（生成封面） |

---

## 排版规格

以 `academic` 主题为例，所有数值来自 `build_css()` 源码：

### 页面

| 属性 | 值 |
|------|-----|
| 纸张 | A4 |
| 页边距 | 上 25mm / 右 22mm / 下 22mm / 左 22mm |
| 页眉 | 报告标题，8pt 灰色 (#95a5a6)，底边 0.5pt 线 |
| 页脚 | "第 N 页"，8pt 灰色，顶边 0.8pt 主题色线 |
| 首页 | 无页眉页脚（封面页） |

### 字体与字号

| 元素 | 字号 | 颜色 | 备注 |
|------|------|------|------|
| 正文 | 11.5pt | 主题 text 色 | 微软雅黑，行高 1.75，两端对齐 |
| h1 | 20pt | 主题主色 | 加粗，底边 2pt 主题色线，前分页 |
| h2 | 15pt | 主题 secondary 色 | 加粗 |
| h3 | 13pt | 主题 accent 色 | 加粗 |
| h4 | 12pt | 主题 heading4 色 | 加粗 |
| 表格 | 10pt | — | 表头主题色底白字 |
| 代码块 | 9.5pt | 浅色 (#e2e8f0) | 深色背景 (#1e293b)，等宽字体 |
| 行内代码 | 10.5pt | 主题 inline_code_text 色 | 浅色背景高亮 |
| 引用块 | 11pt | 主题 quote_text 色 | 左 3pt 主题色条 + 浅色背景 |

### 封面

- 自动提取 Markdown 第一个 h1 作为标题（提取后从正文移除，避免重复）
- 封面标题 28pt，主题 cover_title 色，字间距 2pt
- 居中排版，padding-top 40%，分隔线装饰
- 作者信息 11pt 灰色（如有）
- 封面后自动分页

### 分页规则

- h1 前自动 `page-break-before: always`
- 封面 `page-break-after: always`
- 表格和代码块 `page-break-inside: avoid`
- 段落 `orphans: 3; widows: 3`（防孤行寡行）

### 粗体

`<strong>` / `<b>` 渲染为主题主色加粗，不只是视觉加粗。

---

## Obsidian 语法清理（pdf_utils.py）

`pdf_utils.py` 在调用 `md_to_pdf.py` 前对 Markdown 做预处理：

| 步骤 | 操作 | 说明 |
|------|------|------|
| 1 | 剥离 YAML frontmatter | `--- ... ---` 整段移除 |
| 2 | 移除首个 h1 | 封面标题替代，避免重复 |
| 3 | 元数据块移至附录 | callout 块 + wikilink 列表移至文档末尾"附录：页面元数据" |
| 4 | 清理 callout 语法 | `> [!warning] ...` → `> ...` |
| 5 | 移除 Mermaid 块 | 替换为"（图谱见 Obsidian 渲染）" |
| 6 | 清理 wikilinks | `[[page\|alias]]` → `alias`，`[[page]]` → `page` |

---

## Emoji 预处理

微软雅黑字体不含 emoji 字形。如果 Markdown 中有 emoji：

```bash
python -c "
import re, sys
with open(sys.argv[1], 'r', encoding='utf-8') as f: t = f.read()
t = re.sub(r'[\U0001F300-\U0001F9FF]', '', t)
t = t.replace('\U0001F7E2', '[A]').replace('\U0001F7E1', '[R]').replace('\U0001F534', '[--]')
with open(sys.argv[1], 'w', encoding='utf-8') as f: f.write(t)
" <input.md>
```

入库流程中的 brief/report 通常不含 emoji（编译阶段已处理），此步骤仅用于手动转换用户原始 Markdown 时。

---

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| PDF 空白 | Playwright 未安装 Chromium | `playwright install chromium` |
| 中文显示为方框 | 系统缺少微软雅黑 | 安装 Windows 字体或用 `--css` 指定其他字体 |
| 表格列太窄 | Markdown 表格列太多 | 用 `--css` 自定义列宽 |
| Emoji 显示为方框 | 微软雅黑不含 emoji | 预处理替换 emoji 为文字标记 |
| 代码块中文乱码 | 代码块字体不含中文 | 已在 CSS 中处理（代码块使用微软雅黑） |
| 转换超时 | Playwright 启动慢或页面过大 | 检查 Chromium 安装；大文档考虑分章节 |
