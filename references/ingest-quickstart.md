# 入库快速指南

精简版。完整参考见 `ingest-guide.md`。

---

## 一句话

把 URL / 文件 / 文本 → 结构化知识页（brief + source），自动归域、建索引。

---

## 默认流程（prepare-only，无需 API key）

```powershell
# 1. 抓取 + 生成编译 payload（默认行为）
python scripts/wiki_ingest.py --vault "D:\Vault" "https://..."

# 2. 基于 payload 在对话中生成 JSON，保存为 result.json

# 3. 校验 JSON（推荐）
python scripts/apply_compiled_brief_source.py `
  --vault "D:\Vault" `
  --compiled-json "result.json" `
  --validate-only

# 4. 回写正式页（--raw 可省略，自动从 compile_target.raw_path 提取）
python scripts/apply_compiled_brief_source.py `
  --vault "D:\Vault" `
  --compiled-json "result.json"

# 5. 生成 PDF（入库后 LLM 应主动调用 md-to-pdf）
# brief PDF 会自动生成。如需手动重新生成：
# python D:\AI\Skill\md-to-pdf-v1.0\scripts\md_to_pdf.py <brief.md> <brief.pdf> --title "标题 - 简报"
```

---

## 来源类型 → 处理方式

| 来源 | 命令 |
|------|------|
| 微信 / 网页 URL | `wiki_ingest.py "https://..."` |
| YouTube / B站 / 抖音 | `wiki_ingest.py "https://..."` （自动走视频适配器） |
| 本地文件 | `wiki_ingest.py "D:\path\to\file.pdf"` |
| 粘贴文本 | `wiki_ingest.py --text "内容"` |
| 批量 | `wiki_ingest.py "URL1" "URL2" "URL3"` |

---

## 编译模式选择

| 说… | 用… |
|-----|-----|
| "入库" / "整理这篇" | 默认 prepare-only（无需额外参数） |
| "快速入库" / "不需要 LLM" | `--no-llm-compile` |
| "无人值守" / "批量" | `--api-compile`（需配置 API key） |
| "精读入库" / "全书入库" | `--chunked --chunk-size 500`（长文档分块深度精读） |

---

## 长文档入库（分块编译）

当文档超过 800 行时，系统自动切换为 `chunked-prepare` 模式。也可手动指定：

```powershell
# 手动指定分块精读（chunk-size 默认 500 行）
python scripts/wiki_ingest.py --vault "D:\Vault" --chunked --chunk-size 300 "D:\path\to\book.pdf"
```

### 分块精读流程

1. **自动分块**：`chunk_raw_document()` 将长文档按章节标题→通用标题→固定行数三级策略拆分为 chunks
2. **逐块提取**：LLM 在对话中逐 chunk 处理，保证每段文本都被认真阅读
3. **跨块综合**：所有 chunk 提取完成后，LLM 合成为完整 V2.0 compile JSON
4. **验证 + apply**：与普通入库相同

### 精读 vs 粗读效果对比

精读版 claim 数量是粗读版的 9 倍，且揭示 8+ 个先验知识无法覆盖的关键论点/案例。对于信息密度高的书籍，精读是必要的。

### ASR 来源特异规则

当 `transcript_stage == "asr"` 时（如抖音/B站视频转录）：
- grounding_quote 允许**语义重建**而非精确引用（ASR 转录含同音错字、繁简差异）
- 标注 `[ASR-tolerant match]` 或 `[语义重建]`
- confidence_hint 为 `"low"` 时，claim 置信度默认降一级

---

## 入库后

脚本自动输出影响报告，包含：编译质量、相关来源、跨域联想、开放问题、建议下一步。

### delta 提案

如果有 `delta_outputs`，说明有待审核的页面更新建议。查看：说 "review" 或检查 `wiki/outputs/` 下的文件。

### 入库后自动检查（LLM 应主动执行）

1. **健康评分** → `python scripts/wiki_index_v2.py --vault "D:\Vault" --health`
2. **综合页 freshness** → 检查相关综合页是否需要更新
3. **审核队列积压** → `ls wiki/outputs/delta-*.md | wc -l`
4. **入库里程碑** → 更新 memory 中的入库计数

### 常用操作

- 追问文章论点 → 直接对话
- 深入研究 → 说 "deep research"
- 健康检查 → 说 "lint"
- 查看审核队列 → 说 "review"

---

## 入库完成必选输出

**入库完成后，LLM 必须按以下模板输出完整结果。这是 hard requirement，不可省略任何区块。**

```
## 入库完成：{article.title}

> [[briefs/{slug}]] | [PDF](file:///{brief_pdf_path})

**一句话**：{one_sentence}

### 骨架
【直接引用 brief.skeleton.generators 每条 narrative 原文，保留因果论证和精确措辞。禁止拆维度、禁止改写/压缩/概括。原文太长则截取核心句而非重写】

### 关键判断
【直接引用 brief.key_points 每条原文。禁止二次抽象——key_points 已是压缩产物，再压缩就丢失信息】

### 知识库关联
【来自 source.knowledge_base_relation + update_proposals，列出已有页面的关联关系。格式：关联页面 + 关联说明。如无则写 "无已有关联"】

### 跨域洞察
【如有 cross_domain_insights，列出 mapped_concept + bridge_logic + migration_conclusion；如无则写 "无跨域发现"】

### 冲突与待验证立场
【整合 contradictions（高置信度矛盾，confidence ≥ Supported）和 stance_impacts + claim_inventory 中 verification_needed=true 的主张。格式：每个条目标注来源类型（矛盾/待验证）和逻辑风险。如无则写 "无明显冲突"】

### 开放问题
【来自 compile JSON 的 open_questions，逐条列出。如无则省略此段】

### 建议下一步
1. {基于内容的具体建议，如 "阅读 [[related_page]] 了解 XX 对比"}
2. {维护建议，如 "该领域综合页需更新"}
3. {如 delta 提案存在，提示审核}
【与开放问题重叠时合并，不重复罗列。开放问题已列出的探索方向，这里只给行动建议而非重述问题】
```

**填写规则（严格执行）**：
- `one_sentence` 必须来自 compiled payload 的 `document_outputs.brief.one_sentence`，不可自行编造
- `骨架` **直接引用** brief.skeleton.generators 的 narrative 原文，逐条列出，保留因果论证和精确措辞。**禁止拆成驱动因子/关键数据/正向循环/负向风险等子维度，禁止二次压缩、改写、概括**。如果原文太长，截取核心句而非重写
- `关键判断` **直接引用** brief.key_points 原文，逐条列出。key_points 已是压缩产物，再压缩就丢失信息
- `知识库关联` 来自 `source.knowledge_base_relation` 和 `update_proposals`，展示新入库内容与已有知识的连接
- `跨域洞察` 来自 `result.cross_domain_insights`，必须包含 bridge_logic 和 migration_conclusion，不可只写摘要
- `冲突与待验证立场` 整合 contradictions 和待验证主张。高置信度矛盾（confidence ≥ Supported）必须展示；低置信度矛盾和 stance_impacts 中 extend/reinforce 类不展示，但 verification_needed=true 的主张需列出并标注逻辑风险
- `开放问题` 来自 compile JSON 的 `open_questions`，与"建议下一步"重叠时后者只给行动建议，不重述问题
- `建议下一步` 由 LLM 基于实际内容生成，必须具体、可执行
- PDF 路径来自 ingest_orchestrator 输出的 `brief_pdf_path` 字段；**必须传 --title 参数**（格式："{article.title} - 简报"），否则 Windows 中文标题提取失败会回退为"报告"

**反二次压缩校验**：骨架和关键判断的每一条必须能在 brief 正文中找到原文对应句。如果 LLM 发现自己在"概括"而非"引用"，必须停下来回到 brief 正本重新提取。
