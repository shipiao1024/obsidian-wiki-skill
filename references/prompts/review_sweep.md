# Review Sweep 约束

对 review queue 中的待处理项进行自动清理判断。你从已过时或已解决的项中筛选出可以自动标记为 resolved 的条目。

## 输入

脚本收集的 JSON，包含：
- `pending_outputs`：所有 lifecycle 为 temporary 或 review-needed 的 output 列表
- `existing_pages`：wiki/ 下所有已存在的页面路径列表
- `batch_info`：当前批次号、批次大小

## 判断流程

### 第一步：规则匹配（你执行）

对每个 pending output，按以下规则判断：

**规则 R1 — missing-page 类型**：
```
条件：output 的 frontmatter 含 mode: insight 或 type: query
逻辑：
  1. 从 output 内容中提取引用的 [[页面名]]
  2. 检查这些页面是否已存在于 wiki/ 中
  3. 如果所有引用页面都已存在 → 标记为 resolved（reason: "all_referenced_pages_exist"）
```

**规则 R2 — 被覆盖的 output**：
```
条件：多个 output 标题相同或高度相似
逻辑：
  1. 按 created 日期排序
  2. 保留最新的，旧的标记为 resolved（reason: "superseded_by_newer"）
```

### 第二步：LLM 语义判断（对规则 R1/R2 剩余项）

对规则匹配后仍为 pending 的项，做语义判断。

**保守策略**：
- contradiction 和 suggestion 类型默认保持 pending，除非有明确证据表明已过时
- 只有信息已被完全吸收或明确失效的项才标记为 resolved

**判断标准**：

| 状态 | 条件 | 操作 |
|------|------|------|
| resolved | 内容已被正式页面完全覆盖，无新增价值 | 标记 resolved |
| pending | 内容仍有独立价值，或与正式页面有差异 | 保持 pending |
| uncertain | 无法确定 | 保持 pending（宁可多留，不可误删） |

## 输出 JSON schema

```json
{
  "sweep_results": [
    {
      "path": "outputs/xxx",
      "status": "resolved|pending",
      "reason": "all_referenced_pages_exist|superseded_by_newer|content_absorbed|still_valuable|uncertain",
      "detail": "具体判断依据"
    }
  ],
  "summary": {
    "total_reviewed": 20,
    "resolved": 8,
    "kept_pending": 10,
    "uncertain": 2
  }
}
```

## 批次控制

- 批次大小：batch = 20
- 最大批次数：max_batches = 3
- 提前终止：某批次 resolved = 0 则停止后续批次
- 每批次独立判断，不依赖前一批次的结果

## 约束

- 保守优先：不确定时保持 pending
- 不删除文件：只修改 lifecycle 字段
- reasoning 不为空：每个 resolved 项必须有明确理由
- 不依赖外部信息：只用输入 JSON 中的数据判断
