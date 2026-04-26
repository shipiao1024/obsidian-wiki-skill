"""Core data types and constants for the obsidian-wiki pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


WIKI_DIRS = [
    "raw/inbox",
    "raw/articles",
    "raw/assets",
    "raw/transcripts",
    "wiki/sources",
    "wiki/briefs",
    "wiki/concepts",
    "wiki/entities",
    "wiki/domains",
    "wiki/syntheses",
    "wiki/questions",
    "wiki/stances",
    "wiki/comparisons",
    "wiki/outputs",
]

DEFAULT_DOMAINS = {
    "自动驾驶": ["自动驾驶", "智驾", "AIDV", "FSD", "L2", "L3", "EEA", "端到端", "BEV"],
    "AI 工程": ["Claude", "Codex", "LLM", "RAG", "Agent", "模型", "推理", "Transformer"],
    "机器人": ["机器人", "具身", "机械臂"],
    "商业分析": ["公司", "市场", "竞争", "商业", "投资", "融资"],
    "认知科学": ["认知", "记忆", "注意力", "工作记忆", "认知负荷", "心智", "表征", "心理表征", "晶体智力", "流体智力"],
    "学习方法论": ["刻意练习", "意义学习", "元认知", "学习策略", "反馈", "对比反馈", "知识焦虑", "学习效率"],
    "社会批判": ["文化资本", "符号暴力", "阶层", "围观", "倒错", "间人", "直人", "自反", "自恋", "贴现", "商品价值", "异化"],
    "知识社会学": ["知识生产", "学术场域", "话语权", "布迪厄", "场域"],
}
DOMAIN_MIN_SCORE = {
    "自动驾驶": 4,
    "AI 工程": 4,
    "机器人": 4,
    "商业分析": 3,
    "认知科学": 3,
    "学习方法论": 3,
    "社会批判": 3,
    "知识社会学": 3,
}
CONCEPT_PAGE_THRESHOLD = 2
ENTITY_PAGE_THRESHOLD = 2

VALID_PAGE_STATUS = ("seed", "developing", "mature", "evergreen", "draft")
STATUS_UPGRADE_THRESHOLDS = {
    "seed": 1,
    "developing": 3,
    "mature": 6,
}

DOMAIN_EXCLUDE_LINES = ("作者", "原始链接", "来源", "公众号", "快读页", "原文页")
GENERIC_ENTITY_STOPWORDS = {
    "AI",
    "AIDV",
    "BEV",
    "EEA",
    "FSD",
    "L2",
    "L3",
    "LLM",
    "SDV",
    "VAD",
    "VIT",
}

ENGLISH_ENTITY_STOPWORDS: set[str] = {
    "The", "And", "This", "That", "They", "What", "How", "When", "Where",
    "Who", "Why", "Which", "Then", "Than", "These", "Those", "There",
    "Their", "Here", "Each", "Every", "Some", "Any", "All", "Not",
    "But", "Or", "Nor", "Yet", "So", "For", "With", "From", "Into",
    "Also", "Just", "Very", "Much", "More", "Most", "Such", "Only",
    "Can", "May", "Will", "Would", "Could", "Should", "Must", "Shall",
    "Call", "Like", "Make", "Take", "Come", "Know", "Look", "Think",
    "Good", "Right", "Well", "Going", "Thing", "Give", "Tell", "Say",
    "See", "Get", "Go", "Do", "Did", "Does", "Done", "Been", "Being",
    "Want", "Need", "Try", "Use", "Find", "Keep", "Let", "Put",
    "Set", "Turn", "Run", "Ask", "Show", "Play", "Work", "Help",
    "APP", "API", "URL", "HTTP", "HTML", "SQL", "JSON", "OK", "Yes",
    "No", "Hi", "Hey", "Oh", "Wow", "Hey", "Um", "Uh", "Ah",
    "It", "He", "She", "We", "Me", "My", "His", "Her", "Us",
    "Its", "Our", "You", "Your", "They", "Them", "Him",
}

CONCEPT_STOPWORDS: set[str] = {
    "这是", "什么", "怎么", "为什么", "因为", "所以", "然后", "但是",
    "而且", "或者", "如果", "虽然", "不过", "其实", "就是", "那个",
    "这个", "我们", "他们", "你们", "自己", "一些", "很多", "非常",
    "然后", "可以", "能够", "已经", "还要", "不是", "没有", "的话",
    "时候", "地方", "东西", "问题", "方面", "情况", "关系", "方式",
    "意义", "特点", "结果", "过程", "道理", "时候", "一样", "不同",
    "出来", "下去", "起来", "过来", "回去", "知道", "觉得", "认为",
    "看看", "说说", "想想", "做到", "完成", "开始", "结束", "出现",
    "发生", "产生", "形成", "变化", "发展", "增长", "提高", "降低",
    "今天", "昨天", "明天", "现在", "以前", "以后", "一直", "每次",
}


@dataclass
class Article:
    title: str
    author: str
    date: str
    source: str
    body: str
    src_dir: Path
    md_path: Path
    quality: str = ""
    transcript_stage: str = ""
    transcript_source: str = ""
    transcript_language: str = ""
    transcript_confidence_hint: str = ""
    transcript_body: str = ""
    transcript_subtitle_asset: str = ""
    transcript_audio_asset: str = ""
    collection_source_kind: str = ""
    collection_source_url: str = ""
    collection_video_id: str = ""
    confidence: str = ""