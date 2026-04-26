# Codex / Claude 交互模板

这个文件只回答一件事：安装好 skill 之后，用户应该如何在宿主 Agent 里发指令。

## 推荐主入口

推荐把 Codex 或 Claude Code 当成唯一入口。用户不需要自己手动拼脚本链，只要在对话里给出目标文章链接和意图。

对外表达时，优先把系统解释成：

- 宿主 Agent 对话入口为主
- 脚本入口为辅
- 脚本只是承接 `抓取 / 入库 / 编译 / 应用 / 审核` 五阶段中的具体执行

不要先从脚本命令开始解释，否则用户会误以为这是一个“命令行优先”的 skill。

标准心智模型：

1. 宿主 Agent 先抓取文章到 `raw/`
2. 宿主 Agent 准备 compile payload（推荐加 `--lean` 减少上下文占用）
3. 宿主 Agent 在当前对话里完成语义编译
4. 宿主 Agent 把结构化结果写回 `brief/source`
5. 后续 query、review、apply、archive 继续在同一对话里完成

## 运行模式

→ 模式详细说明见 `references/workflow.md`（正式运行模式 + autoresearch/save 扩展模式）

简要参考：
- `fetch+heuristic`：快速入库，启发式 brief/source
- `fetch+prepare-only`：交互式编译（推荐默认）
- `fetch+api-compile`：无人值守/批处理
- `autoresearch`：广域探索补盲，3 轮递进搜索入库（触发词：autoresearch、自动研究、深入调查、知识库补盲）→ 协议详见 `autoresearch-protocol.md`
- `save`：保存对话讨论为 wiki 页面（触发词：save、保存对话、记录讨论）

## 输入端路由规范

宿主 Agent 收到请求时，先判断“用户想做什么”，再判断“用户给了什么”。

### 用户意图

- `ingest`
- `prepare_compile`
- `apply`
- `review`
- `query`
- `maintenance`

### 输入类型

- 微信 URL
- 通用网页 URL
- 视频 URL（YouTube / Bilibili / Douyin）
- 本地文件（.md / .markdown / .txt / .html / .htm / .pdf）
- 纯文本粘贴
- 本地 `raw/articles/*.md`
- compiled JSON
- `wiki/outputs/*.md` 或 delta 草稿
- 普通问题文本

### 路由规则

1. 用户给微信 URL / 通用网页 URL / 视频 URL
- 默认走 `ingest`
- 如果用户说”先给我 compile payload””不要直接写最终页”，改走 `prepare_compile`

2. 用户给本地文件（.md / .txt / .html / .pdf）或纯文本粘贴
- 默认走 `ingest`
- 当前适配器支持 `.md` / `.markdown` / `.txt` / `.html` / `.htm` / `.pdf` 和 `--text` 纯文本

3. 用户给本地 raw article
- 默认走 `prepare_compile` 或 `apply`
- 不重复 fetch

4. 用户给 compiled JSON
- 直接走 `apply`

5. 用户给 output / delta 草稿
- 直接走 `review`

6. 用户只是提问
- 走 `query`

7. 用户要求对一个主题做深入研究
- 走 `deep-research`
- 触发词："深入研究"、"深度分析"、"deep research"、"系统分析"
- 当用户的问题同时具备：战略重要性 + 依赖外部事实 + 框架风险时，即使未明确说"深入研究"，宿主 Agent 也应建议升级到 deep-research

### 推荐默认决策

1. 不要默认走 API compile
2. 不要给了 compiled JSON 还重新抓取
3. 不要给了 delta/output 还重新编译
4. 不要把脚本名当成第一层用户接口

### 推荐状态词汇

- `ok`
- `skipped_existing`
- `not_configured`
- `browser_not_ready`
- `dependency_missing`
- `platform_blocked`
- `network_failed`
- `runtime_failed`
- `invalid_input`

其中网页来源当前最常见的两类状态是：

- `browser_not_ready`
  - 典型信号：`Chrome debug port not ready`
- `network_failed`
  - 典型信号：`Unable to connect`
- `platform_blocked`
  - 典型信号：平台返回 `HTTP Error 412`、登录/风控拦截
  - 若是视频来源，→ cookie 处理见 `references/video-rules.md`
- `invalid_input`
  - 不要引导用户使用 `--cookies-from-browser`（已废弃）
  - → cookie 安装流程见 `references/video-rules.md`

## 用户可直接说的话

### 1. 单篇 ingest + 编译

```text
用 Claude-obsidian-wiki-skill 抓取并编译这篇微信文章：
https://mp.weixin.qq.com/s/...
要求按交互式主流程处理，生成 raw、brief、source，并更新 index/log。
```

### 2. 只抓取，不立刻编译

```text
先用 Claude-obsidian-wiki-skill 抓取这篇微信文章到 raw，不要直接写最终 brief/source。
先给我 compile payload 和你准备怎么编译。
```

### 3. 首次 Bilibili 抓取但缺 cookie

```text
用 Claude-obsidian-wiki-skill 抓这个 Bilibili 合集。
如果缺登录态，就直接告诉我怎么导出 cookies.txt。
我会自己把它放到 skill 目录里。
如果需要，也可以把本地文件路径给你，由你帮我安装到 skill 目录后再继续跑。
```

### 3. 基于 payload 在当前对话里完成编译

```text
读取刚才的 compile payload，在当前对话里产出符合 schema 的 brief/source JSON。
不要调用外部 API。
```

### 4. 把当前对话里生成的编译结果写回 vault

```text
把你刚才生成的 compile JSON 回写到正式 brief/source 页面，并刷新 taxonomy、synthesis、index、log。
```

### 5. 围绕文章继续追问

```text
基于这篇文章继续回答：AIDV 为什么会逼迫 EEA 走向更集中的计算架构？
如果答案值得沉淀，写入 outputs。
```

### 6. 把高价值 outputs 回归正式知识页

```text
把这个 output 吸收到正式知识页里。
优先更新对应 synthesis；如果它是 delta-source，就同步更新 source/brief。
```

### 7. 做日常维护

```text
运行这个知识库的日常维护流：lint、review queue、archive duplicate outputs。
只汇报需要我决策的项。
```

## 宿主 Agent 的执行约定

宿主 Agent 收到这类请求后，推荐行为是：

1. 自动发现当前打开的 Obsidian vault
2. **域优先自动路由**：抓取完成后，先检测内容域，再根据各 vault purpose.md 的关注领域自动选择匹配的 vault。不需要反复询问用户应该落盘到哪个 vault。只有当内容域与所有已有 vault 都不匹配时，才建议创建新 vault。
3. 优先走交互式 compile 主路径，不默认走 API。使用 `--prepare-only --lean` 生成精简 payload（移除宿主 Agent 不需要的 system_prompt/user_prompt，过滤乱码 synthesis excerpt，上下文占用减少 ~80%）
4. 在写正式页前，先把编译结果对象化成 JSON
5. 保留 `raw/articles` 作为最终证据层
6. 如果用户没有要求，避免把一次性 query 直接升格成正式页
7. **知识图谱重建必须针对内容实际落盘的 vault**：运行 `export_main_graph.py` 时必须传 `--vault <path>`，确保图谱生成在正确的 vault 里。不要依赖 vault.conf 默认值——当内容被自动路由到非默认 vault 时，默认值指向错误的 vault。

### 8. 自主研究一个主题

```text
用 autoresearch 模式深入研究"端到端自动驾驶的争议"。
做三轮搜索，每轮聚焦不同角度，把结果入库。
```

### 9. 对现有问题补充研究

```text
对知识库里的开放问题"BEV vs 端到端哪个更适合量产？"做 autoresearch。
重点搜索能回答这个问题的最新材料。
```

### 10. 保存对话讨论为知识页

```text
把刚才关于"BEV 架构演进"的讨论保存为综合分析页。
```

### 11. 保存决策记录

```text
save this as a decision: 我们决定优先关注端到端路线，因为量产时间窗口更近。
```

### 12. 保存会话摘要

```text
保存这次会话的核心讨论点到 wiki。
```

### 13. 深度研究一个主题

```text
用 deep-research 模式系统研究"端到端自动驾驶的量产可行性"。
先基于知识库已有材料形成假说，再做针对性搜索验证。
```

### 14. 对开放问题做深度研究

```text
知识库里有个开放问题"纯视觉方案在极端天气下的可靠性"，用 deep-research 模式寻找最新证据。
```

## 入库后标准引导模板

每次入库完成后，宿主 Agent 必须按以下模板展示结果，而不是只返回"写入完成"。

### 普通入库

当编译结果无跨域联想、无战略级开放问题时：

```text
入库完成：{标题} → {vault 名称}
快读入口：[[briefs/{slug}]]
编译质量：{structured | raw-extract}
新增：{N 个概念候选, N 个实体候选, N 个开放问题}

可以继续：
- 追问这篇文章的具体论点
- 查看入库影响报告
- 运行日常维护
```

### 高信号入库

当编译结果包含跨域联想或战略级开放问题时：

```text
入库完成：{标题} → {vault 名称}
快读入口：[[briefs/{slug}]]
编译质量：structured
跨域联想：{概念 → 领域映射, bridge_logic}
开放问题：{问题列表}

可以继续：
- 围绕开放问题追问
- 运行日常维护
```

### Deep-research 引导时机

入库后引导**不要**主动推荐 deep-research。deep-research 的触发时机是在追问场景中：

- 用户围绕内容追问时，如果问题同时具备：战略重要性 + 依赖外部事实验证 + 框架风险
- 这时宿主 Agent 可以建议："这个问题涉及外部验证，适合用 deep-research 深入"
- 用户主动说"深入研究"/"深度分析"/"deep research"

例外：高信号入库的开放问题如果明确涉及战略判断（如"XX 技术路线是否值得投入"），可以加一行提示："此问题涉及外部验证，追问时可升级到 deep-research"

## 不推荐的行为

- 不要要求用户手动先分类文章
- 不要把 `brief` 当作最终证据
- 不要默认直连外部 API，除非用户明确要无人值守或批处理
- 不要把单次提到的名词直接升格成 `concept/entity` 正式节点
- 不要入库完成后只返回"写入完成"——必须展示影响报告和下一步建议
- 不要入库后主动推荐 deep-research——那是追问场景的触发点，不是入库后的默认引导
- 不要对单条视频URL（YouTube/Bilibili/Douyin）调用网页抓取（baoyu-url-to-markdown）——视频URL只走video adapter（yt-dlp），网页抓取无法获取字幕且浪费时间
- 合集/播放列表URL的web fallback是pipeline内置的备用路径，host agent不需要主动触发
- 不要每次域不匹配都询问用户选哪个vault——`resolve_vault(article_domains=...)` 会自动根据 purpose.md 匹配。→ 详细路由机制见 `references/workflow.md`

## 域优先自动路由

→ 详细路由机制和 multi-vault 配置见 `references/workflow.md`

