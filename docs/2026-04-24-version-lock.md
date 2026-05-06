# 2026-04-24 Version Lock

## 建议冻结版本

- 版本名：`2026.04.24-bili-collection-rc2`
- 冻结范围：
  - collection 主入口结构化状态输出
  - Bilibili collection 的错误分类修正
  - skill 目录 `cookies.txt` 自动发现
  - browser cookie 失败时回退 `cookies.txt`
  - cookie 安装脚本与安全提示文档

## 本次锁版结论

- `P0` 已收口：
  - 主入口 JSON 已稳定输出顶层 `collections`
  - 已包含：
    - `collection_status`
    - `collection_reason`
    - `job_path`
    - `cooldown_until`
- `P1` 已收口到“诊断明确、默认路径可用”：
  - `WinError 10013` 已确认是当前 Codex 沙箱网络限制，不应再写成“主机环境波动”
  - 在沙箱外真实运行时：
    - 无 cookie 时，Bilibili 单视频会命中 `HTTP 412 Precondition Failed`
    - 使用 skill 目录 `cookies.txt` 时，Bilibili collection 可成功 ingest
  - 当前默认行为已改为优先自动读取 `Claude-obsidian-wiki-skill/cookies.txt`
- `rc2` 追加收口：
  - 真实 `20` 条窗口基线已通过
  - paused/cooldown 已完成一次现场演练验证

## 已验证证据

- 单元测试：
  - `python -m unittest Claude-obsidian-wiki-skill.tests.test_install_video_cookies Claude-obsidian-wiki-skill.tests.test_source_adapters Claude-obsidian-wiki-skill.tests.test_wiki_ingest_wechat_v2`
  - 结果：`Ran 78 tests ... OK`
- 真实 Bilibili 回归：
  - 输入：
    - `https://www.bilibili.com/list/695894135?sid=3074280&desc=1&oid=943994359`
  - 条件：
    - `--collection-limit 1`
    - `--no-llm-compile`
    - 不显式设置 cookie 环境变量
    - 仅依赖 skill 目录 `cookies.txt`
  - 结果：
    - `ingested = 1`
    - `collection_status = completed`
    - `quality = high`
- 真实 `20` 条窗口基线回归：
  - 输入：
    - `https://www.bilibili.com/list/695894135?sid=3074280&desc=1&oid=943994359`
  - 条件：
    - `--collection-limit 20`
    - `--collection-delay-seconds 1`
    - `--collection-backoff-seconds 5`
    - `--collection-jitter-seconds 0.5`
    - `--collection-failure-threshold 3`
    - `--collection-platform-cooldown-seconds 1800`
    - `--no-llm-compile`
    - 不显式设置 cookie 环境变量
    - 仅依赖 skill 目录 `cookies.txt`
  - 结果：
    - `ingested = 20`
    - `collection_status = completed`
    - 20 条全部为 `quality = high`
- paused/cooldown 现场演练：
  - 条件：
    - 真实主入口
    - 真实 Bilibili collection 展开
    - 受控单视频失败注入
    - `collection_failure_threshold = 2`
    - `collection_platform_cooldown_seconds = 600`
  - 结果：
    - 第一次运行：`collection_status = paused`
    - 写入 `cooldown_until`
    - 第二次运行：主入口直接返回“冷却中，直到 ...”，未继续处理视频项

## 当前冻结建议

- 可以把 `2026.04.24-bili-collection-rc2` 作为当前可交付冻结点
- 对外说明口径应固定为：
  - Bilibili 需要登录态
  - 默认从 skill 目录 `cookies.txt` 读取
  - 用户应自行维护该文件
  - 若浏览器 cookie 无法直接读取，再用本地 `cookies.txt` 安装脚本落盘

## 未关闭项

- 尚未完成一次“非 drill、由平台真实故障触发”的 paused/cooldown 现场样本
- 仍未实现更完整的反风控能力：
  - 代理/IP 轮换
  - UA/header 轮换
  - 全局平台熔断
  - 自动恢复调度器

## 锁版后建议动作

1. 不再继续改动主入口状态结构、cookie 默认读取规则、collection 保护参数名
2. 下一轮只做：
   - 更真实的风控样本采集
   - 非 drill 的 paused/cooldown 证据补强
3. 若要进入下一个冻结点，建议版本名：
   - `2026.04.24-bili-collection-rc3`

