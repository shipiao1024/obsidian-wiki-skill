# 2026-05-03 Version Lock — V1.2.5 (PDF Layout Fix + CDP Cookies + Apply Script Improvements)

版本名：`2026.05.03-pdf-layout-fix-v1.2.5`
基线版本：`V1.2.4 (Compile Mode Redesign + PDF Fix + Validation Gate)`

## 本版核心变更

### 1. PDF 布局修复

**问题**：PDF 输出存在三个布局问题：
1. 封面页标题不正确（显示固定的"报告"而非文章标题）
2. 数据库元数据出现在第2页（应移至附录）
3. 文章标题 h1 在正文第3页重复出现（封面已替代）

**修复**：
- `scripts/pipeline/pdf_utils.py`：`clean_obsidian_syntax()` 新增元数据块提取逻辑，将开头的 callout 和数据库字段（raw_source、source_page、one_sentence 等）移至文档末尾的 `## 附录：页面元数据` 章节
- `md-to-pdf-v1.0/scripts/md_to_pdf.py`：`md_to_html()` 中 h1 移除正则升级为 `<h1\b[^>]*>.*?</h1>`（支持带属性的 h1 标签），并添加 `re.S` flag

**PDF 输出结构**：
- 封面页：`{文章标题} - 简报`
- 正文页：骨架、数据、推演、失效信号、关键判断等内容章节
- 末页：`---` 分隔线 + `## 附录：页面元数据`（callout + 数据库字段）

### 2. CDP Cookies 内置到 video.py

**问题**：`adapters/video.py` 中的 CDP cookies 提取逻辑（`_try_cdp_cookie_file()`）在每次版本升级时被覆盖，已发生3次。

**修复**：
- `scripts/adapters/video.py`：直接内置 `_try_cdp_cookie_file()` 函数和 CDP fallback 分支
- `resolve_video_cookie_arg_variants()` 不再 `del source_id`，改为用于 CDP domain 过滤
- CDP fallback 排在 cookies.txt 之后、空变体之前
- CDP 使用 `launch=False`（只从已运行的浏览器提取）

### 3. `--raw` 参数改为可选

**问题**：`apply_compiled_brief_source.py` 强制要求 `--raw` 参数，但 compiled JSON 中已有 `compile_target.raw_path`。

**修复**：
- `--raw` 参数改为 `default=None`
- `main()` 中：未提供 `--raw` 时自动从 `compile_target.raw_path` 提取
- 支持相对路径（尝试 vault 相对路径）

### 4. 其他修复

| 问题 | 修复 |
|------|------|
| `ingest_report.py` 路径已移至 pipeline/ | 创建 `scripts/ingest_report.py` stub 转发到 pipeline 版本 |
| `--schema-version 2.0` 参数不存在 | 从 pipeline-scripts.md 示例中移除 |
| delta outputs 无引导 | `apply_compiled_brief_source.py` 输出新增 `delta_note` 字段 |
| 入库后自动检查未执行 | quickstart 新增"入库后自动检查"4步列表 |
| PDF 不自动生成 | quickstart 新增 PDF 生成步骤说明 |

## 全量改动文件清单

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `scripts/pipeline/pdf_utils.py` | **修改** | 元数据块提取 + 附录生成 |
| `D:\AI\Skill\md-to-pdf-v1.0\scripts\md_to_pdf.py` | 修改 | h1 移除正则升级 |
| `scripts/adapters/video.py` | **修改** | CDP cookies 内置 |
| `scripts/apply_compiled_brief_source.py` | 修改 | `--raw` 可选 + delta_note |
| `scripts/ingest_report.py` | **新增** | 顶层 stub 转发 |
| `references/ingest-quickstart.md` | 修改 | PDF 步骤 + 入库后检查 + --raw 更新 |
| `references/pipeline-scripts.md` | 修改 | 移除 --schema-version 引用 |

## 验收标准

- [x] PDF 封面页显示 `{文章标题} - 简报`
- [x] PDF 正文无数据库元数据（移至附录）
- [x] PDF 正文无重复 h1 标题
- [x] CDP cookies 内置到 video.py，不再依赖手动 patch
- [x] `--raw` 可省略，自动从 compile_target 提取
- [x] `ingest_report.py` 顶层路径可用
- [x] pipeline-scripts.md 无 `--schema-version` 引用
- [x] delta outputs 有引导说明
- [x] quickstart 包含入库后自动检查步骤
- [x] quickstart 包含 PDF 生成说明

## 与上一版本的兼容性

- `--raw` 参数仍然支持（优先级高于自动提取）
- `_try_cdp_cookie_file()` 是新增函数，不影响现有调用
- `ingest_report.py` stub 向后兼容旧路径引用
