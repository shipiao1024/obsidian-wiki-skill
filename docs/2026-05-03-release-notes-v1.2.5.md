# 2026-05-03 Release Notes — V1.2.5

版本：`2026.05.03-pdf-layout-fix-v1.2.5`
基线：`V1.2.4 (Compile Mode Redesign + PDF Fix + Validation Gate)`

本版解决 V1.2.4 实测中发现的 10 个问题（P0-P3），核心改进是 PDF 布局修复、CDP cookies 内置、apply 脚本易用性提升。

## 核心变更

### 1. PDF 布局修复

三个问题一次修：
- **封面标题**：封面页正确显示 `{文章标题} - 简报`
- **元数据移至附录**：callout 块和数据库字段（raw_source、source_page、one_sentence 等）不再出现在正文第2页，移至文档末尾的"附录：页面元数据"
- **正文无重复标题**：文章标题 h1 从正文中移除（封面已替代）

### 2. CDP Cookies 内置

`adapters/video.py` 直接集成 `_try_cdp_cookie_file()`，不再依赖手动 patch。每次版本升级不再丢失 CDP cookies 提取逻辑。

### 3. `--raw` 参数可选

`apply_compiled_brief_source.py` 的 `--raw` 参数改为可选，未提供时自动从 `compile_target.raw_path` 提取。减少用户参数负担。

### 4. 文档和易用性改进

- 新增 `scripts/ingest_report.py` 顶层 stub（解决路径引用问题）
- 移除 `--schema-version 2.0` 不存在参数的引用
- quickstart 新增入库后自动检查4步列表
- quickstart 新增 PDF 生成步骤说明
- `apply_compiled_brief_source.py` 输出新增 `delta_note` 字段

## Bug 修复清单

| # | 严重度 | 问题 | 修复 |
|---|--------|------|------|
| 1 | P0 | PDF 封面标题不正确 | 元数据提取 + h1 移除正则升级 |
| 2 | P0 | PDF 第2页显示数据库元数据 | 移至附录 |
| 3 | P0 | PDF 正文重复 h1 标题 | h1 从正文移除 |
| 4 | P0 | CDP cookies 每次升级丢失 | 内置到 video.py |
| 5 | P1 | `--raw` 参数强制要求 | 改为可选，自动提取 |
| 6 | P1 | `ingest_report.py` 路径错误 | 创建顶层 stub |
| 7 | P1 | `--schema-version 2.0` 不存在 | 从文档移除 |
| 8 | P2 | PDF 不自动生成说明 | quickstart 新增步骤 |
| 9 | P3 | delta outputs 无引导 | 输出新增 delta_note |
| 10 | P3 | 入库后自动检查未执行 | quickstart 新增检查列表 |

## 改动文件

| 文件 | 改动类型 |
|------|---------|
| `scripts/pipeline/pdf_utils.py` | 修改 |
| `md-to-pdf-v1.0/scripts/md_to_pdf.py` | 修改 |
| `scripts/adapters/video.py` | 修改 |
| `scripts/apply_compiled_brief_source.py` | 修改 |
| `scripts/ingest_report.py` | 新增 |
| `references/ingest-quickstart.md` | 修改 |
| `references/pipeline-scripts.md` | 修改 |

## 推荐阅读顺序

1. `README.md`
2. `references/ingest-quickstart.md`（更新版）
3. `SKILL.md`
4. `docs/2026-05-03-version-lock-v1.2.5.md`
