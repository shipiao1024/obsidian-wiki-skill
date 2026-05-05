#!/usr/bin/env python3
"""
Markdown → PDF 转换脚本 (Playwright + Chrome 渲染)
用法: python md_to_pdf.py input.md output.pdf [--title TITLE] [--author AUTHOR] [--theme THEME] [--no-cover] [--css CSS_PATH]

依赖: pip install markdown playwright && playwright install chromium
"""

import sys
import os
import re
import argparse
import markdown

# ──────────────────────────────────────────
# 主题 CSS 模板
# ──────────────────────────────────────────

THEMES = {
    "academic": {
        "primary": "#1a5276",
        "primary_light": "#d4e6f1",
        "secondary": "#1e8449",
        "accent": "#2e86c1",
        "heading4": "#5b2c6f",
        "text": "#2c3e50",
        "cover_title": "#1a5276",
        "table_header_bg": "#1a5276",
        "table_header_text": "#ffffff",
        "table_even_bg": "#f8f9fa",
        "quote_border": "#1a5276",
        "quote_bg": "#f8f9fa",
        "quote_text": "#5d6d7e",
        "code_bg": "#1e293b",
        "code_text": "#e2e8f0",
        "inline_code_bg": "#fdf2e9",
        "inline_code_text": "#c0392b",
        "page_border_top": "#1a5276",
        "divider": "#ecf0f1",
    },
    "tech": {
        "primary": "#0d9488",
        "primary_light": "#ccfbf1",
        "secondary": "#134e4a",
        "accent": "#0f766e",
        "heading4": "#115e59",
        "text": "#1e293b",
        "cover_title": "#134e4a",
        "table_header_bg": "#0d9488",
        "table_header_text": "#ffffff",
        "table_even_bg": "#f0fdfa",
        "quote_border": "#0d9488",
        "quote_bg": "#f0fdfa",
        "quote_text": "#5d6d7e",
        "code_bg": "#0f172a",
        "code_text": "#e2e8f0",
        "inline_code_bg": "#f0fdfa",
        "inline_code_text": "#0f766e",
        "page_border_top": "#0d9488",
        "divider": "#e2e8f0",
    },
    "warm": {
        "primary": "#92400e",
        "primary_light": "#fef3c7",
        "secondary": "#78350f",
        "accent": "#b45309",
        "heading4": "#7c2d12",
        "text": "#1c1917",
        "cover_title": "#92400e",
        "table_header_bg": "#92400e",
        "table_header_text": "#ffffff",
        "table_even_bg": "#fefce8",
        "quote_border": "#92400e",
        "quote_bg": "#fefce8",
        "quote_text": "#78350f",
        "code_bg": "#1c1917",
        "code_text": "#e7e5e4",
        "inline_code_bg": "#fefce8",
        "inline_code_text": "#b45309",
        "page_border_top": "#92400e",
        "divider": "#e7e5e4",
    },
}


def build_css(theme_name="academic"):
    """根据主题名称生成完整CSS"""
    t = THEMES.get(theme_name, THEMES["academic"])

    return f"""
@page {{
    size: A4;
    margin: 25mm 22mm 22mm 22mm;

    @top-center {{
        content: "HEADER_PLACEHOLDER";
        font-family: "Microsoft YaHei", "SimSun", sans-serif;
        font-size: 8pt;
        color: #95a5a6;
        border-bottom: 0.5pt solid #ecf0f1;
        padding-bottom: 3mm;
    }}

    @bottom-center {{
        content: "第 " counter(page) " 页";
        font-family: "Microsoft YaHei", "SimSun", sans-serif;
        font-size: 8pt;
        color: #95a5a6;
        border-top: 0.8pt solid {t['page_border_top']};
        padding-top: 2mm;
    }}
}}

@page :first {{
    @top-center {{ content: none; }}
    @bottom-center {{ content: none; }}
}}

body {{
    font-family: "Microsoft YaHei", "SimSun", "Noto Sans SC", sans-serif;
    font-size: 11.5pt;
    line-height: 1.75;
    color: {t['text']};
    text-align: justify;
}}

/* ── 封面 ── */
.cover {{
    page-break-after: always;
    text-align: center;
    padding-top: 40%;
}}
.cover h1 {{
    font-size: 28pt;
    color: {t['cover_title']};
    margin-bottom: 8mm;
    font-weight: bold;
    letter-spacing: 2pt;
    border: none;
    page-break-before: avoid;
}}
.cover .subtitle {{
    font-size: 14pt;
    color: #95a5a6;
    margin-bottom: 6mm;
}}
.cover .meta {{
    font-size: 11pt;
    color: #95a5a6;
    margin-bottom: 4mm;
}}
.cover .divider {{
    width: 60%;
    margin: 8mm auto;
    border: none;
    border-top: 1.5pt solid {t['primary']};
}}

/* ── 标题 ── */
h1 {{
    font-size: 20pt;
    color: {t['primary']};
    margin-top: 16mm;
    margin-bottom: 6mm;
    padding-bottom: 3mm;
    border-bottom: 2pt solid {t['primary']};
    page-break-before: always;
    font-weight: bold;
}}

h2 {{
    font-size: 15pt;
    color: {t['secondary']};
    margin-top: 10mm;
    margin-bottom: 5mm;
    font-weight: bold;
}}

h3 {{
    font-size: 13pt;
    color: {t['accent']};
    margin-top: 6mm;
    margin-bottom: 3mm;
    font-weight: bold;
}}

h4 {{
    font-size: 12pt;
    color: {t['heading4']};
    margin-top: 5mm;
    margin-bottom: 2mm;
    font-weight: bold;
}}

/* ── 段落 ── */
p {{
    margin-top: 1.5mm;
    margin-bottom: 1.5mm;
    orphans: 3;
    widows: 3;
}}

/* ── 粗体 ── */
strong, b {{
    font-weight: bold;
    color: {t['primary']};
}}

/* ── 引用块 ── */
blockquote {{
    margin: 4mm 0;
    padding: 4mm 4mm 4mm 10mm;
    background: {t['quote_bg']};
    border-left: 3pt solid {t['quote_border']};
    color: {t['quote_text']};
    font-size: 11pt;
}}
blockquote p {{
    margin: 1mm 0;
}}

/* ── 行内代码 ── */
code {{
    font-family: "Microsoft YaHei", "Consolas", "Courier New", monospace;
    background: {t['inline_code_bg']};
    color: {t['inline_code_text']};
    padding: 0.5mm 1.5mm;
    border-radius: 2pt;
    font-size: 10.5pt;
}}

/* ── 代码块 ── */
pre {{
    background: {t['code_bg']};
    color: {t['code_text']};
    padding: 4mm 5mm;
    border-radius: 4pt;
    font-size: 9.5pt;
    line-height: 1.5;
    overflow-x: auto;
    page-break-inside: avoid;
    margin: 4mm 0;
}}
pre code {{
    background: none;
    color: {t['code_text']};
    padding: 0;
    font-family: "Microsoft YaHei", "Consolas", monospace;
    font-size: 9.5pt;
}}

/* ── 表格 ── */
table {{
    width: 100%;
    border-collapse: collapse;
    margin: 4mm 0;
    font-size: 10pt;
    page-break-inside: avoid;
}}
thead th {{
    background: {t['table_header_bg']};
    color: {t['table_header_text']};
    padding: 3mm;
    text-align: left;
    font-weight: bold;
    font-size: 10pt;
}}
tbody td {{
    padding: 2.5mm 3mm;
    border-bottom: 0.5pt solid #bdc3c7;
    font-size: 10pt;
}}
tbody tr:nth-child(even) {{
    background: {t['table_even_bg']};
}}
tbody tr:hover {{
    background: {t['primary_light']};
}}

/* ── 分隔线 ── */
hr {{
    border: none;
    border-top: 0.5pt solid {t['divider']};
    margin: 4mm 0;
}}

/* ── 列表 ── */
ul, ol {{
    margin: 2mm 0;
    padding-left: 8mm;
}}
li {{
    margin-bottom: 1mm;
}}

/* ── 链接 ── */
a {{
    color: {t['accent']};
    text-decoration: none;
}}
"""


def md_to_html(md_text, title=None, author=None, theme="academic",
               no_cover=False, css_path=None):
    """将Markdown转为带封面/页眉的完整HTML"""

    # 用 markdown 库转换正文
    html_body = markdown.markdown(
        md_text,
        extensions=['tables', 'fenced_code', 'toc', 'nl2br', 'sane_lists'],
        output_format='html5'
    )

    # 提取第一个 h1 作为标题
    if not title:
        first_h1 = re.search(r'<h1>(.*?)</h1>', html_body)
        if first_h1:
            title = first_h1.group(1)
        else:
            title = "文档"

    # 如果生成封面，从正文移除第一个h1（避免重复）
    if not no_cover:
        first_h1 = re.search(r'<h1\b[^>]*>.*?</h1>', html_body, flags=re.S)
        if first_h1:
            html_body = html_body.replace(first_h1.group(0), '', 1)

    # 生成CSS
    if css_path:
        with open(css_path, 'r', encoding='utf-8') as f:
            css = f.read()
    else:
        css = build_css(theme)

    # 替换页眉占位符
    css = css.replace("HEADER_PLACEHOLDER", f"{title}")

    # 生成封面HTML
    cover_html = ""
    if not no_cover:
        author_line = f'<div class="meta">作者: {author}</div>' if author else ''
        cover_html = f"""
        <div class="cover">
            <h1 style="page-break-before: avoid; border: none;">{title}</h1>
            <hr class="divider">
            {author_line}
        </div>
        """

    # 组装完整HTML
    full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <style>{css}</style>
</head>
<body>
{cover_html}
{html_body}
</body>
</html>"""

    return full_html


def html_to_pdf(html_content, output_path):
    """使用Playwright将HTML转为PDF"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # 设置HTML内容
        page.set_content(html_content, wait_until="networkidle")

        # 导出PDF
        page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            margin={
                "top": "25mm",
                "right": "22mm",
                "bottom": "22mm",
                "left": "22mm",
            },
        )

        browser.close()


def main():
    parser = argparse.ArgumentParser(description="Markdown → PDF (Playwright)")
    parser.add_argument("input", help="输入Markdown文件路径")
    parser.add_argument("output", help="输出PDF文件路径")
    parser.add_argument("--title", default=None, help="报告标题（默认从h1提取）")
    parser.add_argument("--author", default="石瓢1024", help="作者名（默认: 石瓢1024）")
    parser.add_argument("--theme", default="academic",
                        choices=["academic", "tech", "warm"],
                        help="主题: academic/tech/warm")
    parser.add_argument("--no-cover", action="store_true", help="不生成封面")
    parser.add_argument("--css", default=None, help="自定义CSS文件路径")

    args = parser.parse_args()

    # 读取Markdown
    with open(args.input, "r", encoding="utf-8") as f:
        md_text = f.read()

    # 转为HTML
    html = md_to_html(
        md_text,
        title=args.title,
        author=args.author,
        theme=args.theme,
        no_cover=args.no_cover,
        css_path=args.css,
    )

    # 保存中间HTML（便于调试）
    html_path = args.output.replace('.pdf', '.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"[OK] HTML: {html_path}")

    # 转为PDF
    html_to_pdf(html, args.output)

    size_kb = os.path.getsize(args.output) / 1024
    print(f"[OK] PDF: {args.output} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
