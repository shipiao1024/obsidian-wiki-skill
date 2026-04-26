# 多来源回归基线

这份文件用于维护当前正式回归样本名单。

使用方式：

1. 先在这里固定 `golden samples`
2. 每次改动入口、adapter、ingest、review、lint 后，按这里的样本重跑
3. 把最近一次回归结果追加到文末“最近回归记录”

配套说明见：

- [acceptance-samples.md](D:/AI/Skill/微信文章归档Obsidian/Claude-obsidian-wiki-skill/references/acceptance-samples.md)

## 当前建议基线

建议先固定 10 个样本。

### 微信 URL

| ID | 类型 | 样本说明 | 输入 | 预期 |
|---|---|---|---|---|
| wechat-01 | wechat_url | 已真实验证过的公众号文章 | `https://mp.weixin.qq.com/s/SILxSkfBJqEzi6LqpCVvMg` | `status=ok`，`raw/source/brief` 齐 |
| wechat-02 | wechat_url | 已真实验证过的公众号文章 | `https://mp.weixin.qq.com/s/Fhr7W29XANl0pRomKdw85Q` | `status=ok`，`index/log` 更新 |

### 通用网页 URL

| ID | 类型 | 样本说明 | 输入 | 预期 |
|---|---|---|---|---|
| web-01 | web_url | 静态公开页面 | `https://example.com` | `status=ok`，标题正确，`quality` 非空 |
| web-02 | web_url | 已真实验证过的公开正文页 | `https://www.iana.org/domains/reserved` | `status=ok`，标题正确，`quality` 非空 |

### 视频 URL

| ID | 类型 | 样本说明 | 输入 | 预期 |
|---|---|---|---|---|
| video-yt-01 | video_url_youtube | 已真实验证过的 YouTube 视频 | `https://www.youtube.com/watch?v=dQw4w9WgXcQ` | transcript 成功，标题来自 metadata |
| video-bi-01 | video_url_bilibili | 已真实验证过的 Bilibili list 样本（cookie + 批量断点续跑） | `https://www.bilibili.com/list/695894135?sid=3074280&desc=1&oid=943994359` | `playlist expand=ok`；曾完成 100 条窗口验证，其中 `99` 条成功进入 `raw/source/brief`，`import-job` 正确记录 `completed=99/remaining=1`；当前工程默认窗口已收紧为 `20`，单条残留样本也已进一步验证可通过 `ASR` 成功入库 |

### 本地文件

| ID | 类型 | 样本说明 | 输入 | 预期 |
|---|---|---|---|---|
| local-md-01 | local_file_md | 仓库内固定 Markdown fixture | `Claude-obsidian-wiki-skill/references/examples/local-md-01.md` | `status=ok`，`raw/source/brief` 齐 |
| local-pdf-01 | local_file_pdf | 仓库内固定正常 PDF fixture | `Claude-obsidian-wiki-skill/references/examples/local-pdf-01.pdf` | `status=ok`，`quality` 非空 |
| local-pdf-low-01 | local_file_pdf | 仓库内固定低质量 PDF fixture | `Claude-obsidian-wiki-skill/references/examples/local-pdf-low-01.pdf` | `status=ok`，`quality=low`，进入 review/lint |

### 纯文本

| ID | 类型 | 样本说明 | 输入 | 预期 |
|---|---|---|---|---|
| text-01 | plain_text | 仓库内固定纯文本 fixture | `Claude-obsidian-wiki-skill/references/examples/text-01.txt` | `status=ok`，主入口可直接 ingest |

## 回归检查清单

每次跑基线时，至少确认这些点：

- `status` 可解释
- `quality` 在 `status=ok` 时存在
- `compile_mode` 可解释
- `raw/articles`、`wiki/sources`、`wiki/briefs` 产物齐
- `wiki/index.md`、`wiki/log.md` 更新正常
- 若 `quality=low`：
  - `review_queue.py --write` 出现 `低质量来源候选`
  - `wiki_lint.py` 输出 `low_quality_sources`

## 最近回归记录

按这个格式追加：

```text
YYYY-MM-DD | sample-id | source-kind | status | quality | compile-mode | note
```

示例：

```text
2026-04-24 | web-01 | web_url | ok | acceptable | heuristic | Example Domain 正常
2026-04-24 | local-pdf-low-01 | local_file_pdf | ok | low | heuristic | 已进入 review_queue / wiki_lint
```

最近一次真实回归结果：

```text
2026-04-24 | local-md-01 | local_file_md | ok | (empty) | heuristic | 主入口成功生成 raw/source/brief
2026-04-24 | text-01 | plain_text | ok | (empty) | heuristic | 主入口成功生成 raw/source/brief
2026-04-24 | local-pdf-01 | local_file_pdf | ok | acceptable | heuristic | 正常 PDF 已达到 acceptable
2026-04-24 | local-pdf-low-01 | local_file_pdf | ok | low | heuristic | 已进入 review_queue / wiki_lint
2026-04-24 | web-02 | web_url | ok | high | heuristic | IANA 正文页主入口验证通过
2026-04-24 | video-bi-01 | video_url_bilibili | partial | low/acceptable mixed | heuristic | Bilibili list 真实验证通过；cookie 生效后曾完成 100 条窗口验证，其中 99 条已写入 raw/source/brief，import-job 记录 completed=99/remaining=1；当前默认窗口已调整为 20，残留样本后续已通过音频 ASR 成功入库
2026-04-24 | video-bi-01-residual | video_url_bilibili | ok | acceptable | heuristic | `BV1zo4y1i7DW` 已验证：`danmaku.xml` 不再进入正文，视频改写入 `raw/transcripts/*--asr.md`，`raw/articles` 只保留来源总页
2026-04-24 | video-bi-01-v3 | video_url_bilibili | partial | (n/a) | heuristic | 已复核旧结论：`WinError 10013` 出现在 Codex 沙箱内，不代表主机网络本身异常；在沙箱外复跑时，合集展开可成功，但首条单视频抓取命中 `HTTP 412 Precondition Failed`，当前真实阻塞点是 Bilibili 平台侧鉴权/风控，而不是“环境波动”
2026-04-24 | video-bi-01-cookie-autodiscover | video_url_bilibili | ok | high | heuristic | 已真实验证：当 skill 目录存在 `Claude-obsidian-wiki-skill/cookies.txt` 时，即使不显式设置 cookie 环境变量，Bilibili collection 也可自动读取该文件并成功 ingest（`collection-limit=1`）
2026-04-24 | video-bi-01-window20 | video_url_bilibili | ok | high | heuristic | 已真实验证：按当前默认 20 条窗口、skill 目录 `cookies.txt` 自动发现、启用 delay/backoff/jitter/failure-threshold/cooldown 参数时，20/20 成功进入 `raw/source/brief`，`collection_status=completed`
2026-04-24 | video-collection-protection-e2e | video_collection | ok | (n/a) | heuristic | 已完成现场演练：使用真实主入口 + 真实 Bilibili collection 展开 + 受控单视频失败注入，验证了“连续失败 -> 自动 paused -> 写入 cooldown_until -> 下次运行冷却跳过”整条链
2026-04-24 | video-collection-protection | video_collection | ok | (n/a) | heuristic | 批量视频保护层已接入：支持 `delay/backoff/jitter/failure-threshold/cooldown`，并会把 `paused/last_failure_reason/cooldown_until` 写入 `import-job`
```

当前已真实验证过的正式基线样本：

- `wechat-01`
- `wechat-02`
- `web-01`
- `web-02`
- `video-yt-01`
- `video-bi-01 (historical 99/100 window verified, current default window=20, resumable)`
- `local-md-01`
- `text-01`
- `local-pdf-01`
- `local-pdf-low-01`

下一步优先补齐：

- 在需要更高信心时，补一次非 drill 的真实平台连续失败演练样本

