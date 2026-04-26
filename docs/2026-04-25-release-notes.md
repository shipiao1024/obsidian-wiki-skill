# 2026-04-25 Release Notes

版本建议：`2026.04.24-bili-collection-rc2`

这份 release notes 对应当前公开发布的 `Claude-obsidian-wiki-skill` 首个可复用版本。它的目标不是提供一个“单脚本抓取器”，而是提供一套面向 `Codex / Claude + Obsidian` 的多来源知识入库与编译工作流。

## 本版包含内容

- 多来源统一入口
  - 微信公众号 URL
  - 通用网页 URL
  - YouTube / Bilibili 视频 URL
  - Bilibili / YouTube collection / playlist
  - 本地 Markdown / 文本 / HTML / PDF
  - 直接粘贴的纯文本
- `raw/` 与 `wiki/` 双层知识模型
- `fetch+heuristic` / `fetch+prepare-only` / `fetch+api-compile` 三种运行模式
- `wiki/sources`、`wiki/briefs`、`wiki/index.md`、`wiki/log.md`
- 视频 `raw/transcripts` 分层
- Bilibili `danmaku.xml` 不进入正文
- 字幕优先，缺失时 ASR fallback
- collection import-job、断点续跑、小窗口保护、paused / cooldown
- collection 顶层结构化 JSON 输出：
  - `collection_status`
  - `collection_reason`
  - `job_path`
  - `cooldown_until`
- skill 根目录 `cookies.txt` 自动发现与文件安装脚本

## 本版已验证内容

- 主入口顶层 `collections` 输出已接通
- Bilibili `cookies.txt` 默认读取路径已真实验证通过
- Bilibili collection `collection-limit=1` 已真实通过
- Bilibili collection `collection-limit=20` 已真实通过
- paused / cooldown 已完成一次现场演练验证
- 发布仓库测试已通过：
  - `python -m unittest discover tests`

## 当前使用约束

- Windows 优先，默认按 PowerShell 工作流编写
- 依赖本地 Obsidian vault
- 依赖本地 adapter 和文件系统
- Bilibili 能力依赖用户自己维护 skill 根目录 `cookies.txt`
- `raw/` 是证据层，`wiki/` 是编译层；精确事实回溯时应优先读 `raw/articles`

## 不在本版目标内

- 完整反风控系统
  - 代理 / IP 轮换
  - UA / header 轮换
  - 全局平台熔断
  - 自动恢复调度器
- 云端 SaaS 化运行时
- 非 Windows 优先的通用安装体验

## 推荐阅读顺序

1. `README.md`
2. `references/setup.md`
3. `SKILL.md`
4. `docs/2026-04-24-version-lock.md`

## 后续版本建议

- 如需继续发布迭代，优先新增真实平台故障样本与 release note 追加记录
- 不建议在未更新基线和验证记录前修改主入口状态结构、cookie 默认读取规则和 collection 保护参数名
