# 2026-04-26 Version Lock — v2 (spec-sync + domain-routing)

版本名：`2026.04.26-cross-domain-patch-v2`
基线版本：`2026.04.26-cross-domain-patch`

## 本版新增内容（相对于上一备份点）

### 域优先自动路由（interaction.md + script-reference.md）

- `wiki_ingest.py` 新增域优先自动路由：抓取完成后调用 `detect_domains()`，再 `resolve_vault(article_domains=...)` 扫描所有 vault 的 `purpose.md`，自动选择域重叠最高的 vault
- `resolve_vault()` 返回匹配 vault 路径 + 匹配域列表
- 非默认 vault 时 stderr 输出 `Auto-routed to vault: <path> (matched domains: ...)`
- 只在内容域与所有 vault 都不匹配时才提示用户创建新 vault
- `export_main_graph.py` 必须传 `--vault <path>` 参数，确保图谱生成在内容实际落盘的 vault 里

### 视频 URL 路由规则（interaction.md）

- 单条视频 URL 只走 video adapter（yt-dlp），不走网页抓取（baoyu-url-to-markdown）
- 合集/播放列表 URL 的 web fallback 是 pipeline 内置备用路径，host agent 不需要主动触发
- `--cookies-from-browser` 已废弃，不再引导用户使用
- 只支持 `KWIKI_VIDEO_COOKIES_FILE` 环境变量或 skill 目录默认 `cookies.txt`

## 全量改动文件清单

| 文件 | 改动类型 |
|------|---------|
| `references/prompts/ingest_compile_prompt_v2.md` | 新增规则 10 + JSON skeleton 加 `cross_domain_insights` |
| `references/examples/compile_mock_response_v2.json` | 加 `cross_domain_insights: []` |
| `scripts/pipeline/validate_compile.py` | 校验 `cross_domain_insights` 结构 |
| `scripts/llm_compile_ingest.py` | `normalize_cross_domain_insights()` + `normalize_result_v2()` 扩展 |
| `scripts/pipeline/ingest_report.py` | LLM 数据优先 + cross_domain_insights 消费 + 领域不匹配重构 |
| `references/script-reference.md` | v2 schema 字段补全 + impact report + 域优先自动路由描述 |
| `references/workflow.md` | v2 产出字段表 + cross_domain_insights 说明 + 影响报告结构 |
| `references/interaction.md` | 不推荐行为新增 + 域优先自动路由 + 视频 URL 路由规则 + 废弃 cookies-from-browser |
| `SKILL.md` | cross_domain_insights 功能描述 + 运行模式区分 |

## 测试结果

- **86 passed, 11 pre-existing failures**（adapter 环境依赖 8 + argparse 泄漏 2 + web adapter 1，与本次改动无关）

## 当前使用约束

- 跨域联想仅在 LLM 编译路径可用
- 启发式入库 impact 报告标注 compile_quality: raw-extract
- 域优先自动路由需要多 vault 环境下各 vault `purpose.md` 正确填写关注领域
- 视频抓取依赖 skill 目录 `cookies.txt`