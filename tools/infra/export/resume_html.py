"""简历预览与 PDF 共用的安全 HTML 排版。"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from typing import Any


def parse_resume_markdown(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    name = ""
    contact = {"phone": "", "email": "", "city": ""}
    summary_lines: list[str] = []
    skills: list[str] = []
    experience: list[dict[str, Any]] = []
    current_section = ""
    current_experience: dict[str, Any] | None = None
    extra_sections: list[dict[str, Any]] = []
    current_extra: dict[str, Any] | None = None
    header_notes: list[str] = []
    section_titles: dict[str, str] = {}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") and not name:
            name = stripped[2:].strip()
            continue
        if stripped.startswith("Generated at:") or stripped.startswith(
            "Source report:"
        ):
            continue
        if stripped.startswith("## "):
            current_section = stripped[3:].strip().lower()
            current_section = {
                "项目经历": "experience", "工作经历": "experience",
                "核心技能": "skills", "技能": "skills", "联系方式": "contact",
            }.get(current_section, current_section)
            section_titles[current_section] = stripped[3:].strip()
            if current_section != "experience" and current_experience is not None:
                experience.append(current_experience)
                current_experience = None
            current_extra = None
            if current_section not in {"experience", "skills", "contact", "10-second summary"}:
                current_extra = {"title": stripped[3:].strip(), "lines": []}
                extra_sections.append(current_extra)
            continue
        if current_extra is not None:
            current_extra["lines"].append(stripped)
            continue
        if stripped.startswith(("当前定位：", "求职意向：")):
            summary_lines.append(stripped)
            continue
        if not current_section and " | " in stripped:
            parts = stripped.split(" | ")
            emails = [part for part in parts if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", part)]
            phones = [part for part in parts if re.fullmatch(r"\+?[\d -]{7,20}", part)]
            if not emails and not phones:
                header_notes.append(stripped)
                continue
            if emails:
                contact['email'] = emails[0]
            if phones:
                contact['phone'] = phones[0]
            remainder = ' | '.join(part for part in parts if part not in emails and part not in phones)
            if remainder and not contact['city']:
                contact['city'] = remainder
            elif remainder and remainder != contact['city']:
                header_notes.append(remainder)
            continue
        if current_section == "skills":
            skills.extend(item.strip() for item in re.split(r"[、,，|]", stripped.removeprefix('- ')) if item.strip())
            continue
        if current_section == "contact":
            value = stripped.removeprefix('- ')
            parts = re.split(r"[:：]", value, maxsplit=1)
            key = {"email": "email", "邮箱": "email", "phone": "phone", "电话": "phone", "city": "city", "城市": "city"}.get(parts[0].strip().lower())
            if key and len(parts) == 2:
                contact[key] = parts[1].strip()
            else:
                header_notes.append(value)
            continue
        if current_section == "experience" and stripped.startswith("角色：") and current_experience is not None:
            current_experience["title"] = stripped.removeprefix("角色：").strip()
            continue
        if current_section == "10-second summary" and stripped.startswith("- "):
            value = stripped[2:].strip()
            summary_lines.append(value)
            if value.startswith("核心技术栈："):
                stack_line = value.removeprefix("核心技术栈：").strip()
                skills.extend(
                    item.strip() for item in stack_line.split(",") if item.strip()
                )
            continue
        if current_section == "experience" and stripped.startswith("### "):
            if current_experience is not None:
                experience.append(current_experience)
            heading = stripped[4:].strip()
            company = heading
            period = ""
            if "（" in heading and heading.endswith("）"):
                company, period = heading[:-1].split("（", 1)
                company = company.strip()
                period = period.strip()
            current_experience = {
                "company": company,
                "title": "",
                "period": period,
                "bullets": [],
            }
            continue
        if current_section == "experience" and stripped.startswith("- "):
            if current_experience is None:
                header_notes.append(stripped)
                continue
            bullet = stripped[2:].strip()
            if bullet.startswith("角色与范围："):
                current_experience["title"] = bullet.removeprefix(
                    "角色与范围："
                ).strip()
            else:
                current_experience["bullets"].append(bullet)
            continue
        if current_section == "experience" and current_experience is not None:
            current_experience["bullets"].append(stripped)
        else:
            header_notes.append(stripped)

    if current_experience is not None:
        experience.append(current_experience)

    return {
        "name": name,
        "contact": contact,
        "summary": " ".join(summary_lines).strip(),
        "experience": experience,
        "skills": skills,
        "summary_lines": summary_lines,
        "header_notes": header_notes,
        "extra_sections": extra_sections,
        "section_titles": section_titles,
    }


def _inline_text(value: str) -> str:
    value = escape(value)
    # 原材料片段可能截断加粗标记；只清理格式，不吞掉代码中的 ** 运算符。
    marker='\x00'
    while marker in value:marker+='\x00'
    codes=[]
    def code(match):
        token=f'{marker}{len(codes)}{marker}'
        codes.append((token,'<code>'+match[1]+'</code>'))
        return token
    value = re.sub(r'`([^`]+)`', code, value)
    if value.count('**') % 2:value=value.replace('**','')
    value = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', value)
    for token,html in codes:value=value.replace(token,html)
    return value


def _section_body(lines: list[str], *, experience: bool) -> str:
    body: list[str] = []
    in_list = in_article = False
    for line in lines:
        value = line.strip()
        if not value:
            continue
        if not value.startswith('- ') and in_list:
            body.append('</ul>'); in_list = False
        if value.startswith('### '):
            if in_article: body.append('</article>')
            if experience: body.append('<article class="experience">'); in_article = True
            title = value[4:]; period = ''
            match = re.match(r'^(.*?)（([^（）]*\d{4}[^（）]*)）$', title)
            if match: title, period = match.groups()
            body.append('<div class="experience-heading"><h3>'+_inline_text(title)+'</h3>'+
                        ('<time>'+escape(period)+'</time>' if period else '')+'</div>')
        elif value.startswith('- '):
            if not in_list: body.append('<ul>'); in_list = True
            body.append('<li>'+_inline_text(value[2:])+'</li>')
        else:
            cls = 'role' if value.startswith(('角色：','角色与范围：')) else 'context' if value.startswith('场景：') else 'paragraph'
            body.append('<p class="'+cls+'">'+_inline_text(value)+'</p>')
    if in_list: body.append('</ul>')
    if in_article: body.append('</article>')
    return ''.join(body)


def render_resume_html(markdown_text: str) -> str:
    """按原文章节顺序展示，模板只排版和转义，不替换正文事实。"""
    blocks = re.split(r'^## ([^\n]+)\n?', markdown_text, flags=re.MULTILINE)
    data = parse_resume_markdown(blocks[0])
    css = Path(__file__).with_name('resume.css').read_text(encoding='utf-8')
    contact = ''.join('<span>'+escape(data['contact'][key])+'</span>' for key in ('phone','email','city') if data['contact'][key])
    intro = ''.join('<p class="intro">'+_inline_text(line)+'</p>' for line in [*data['summary_lines'], *data['header_notes']])
    sections = []
    for index in range(1,len(blocks),2):
        title, source = blocks[index].strip(), blocks[index+1]
        if title.lower() in {'核心技能','技能','skills'}:
            items = parse_resume_markdown('## '+title+'\n'+source)['skills']
            body = '<div class="skills">'+''.join('<span class="skill">'+_inline_text(item)+'</span>' for item in items)+'</div>'
        else:
            body = _section_body(source.splitlines(), experience=title.lower() in {'项目经历','工作经历','experience'})
        sections.append('<section><h2>'+escape(title)+'</h2>'+body+'</section>')
    name = escape(data['name'] or '个人简历')
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\';">'
        '<title>'+name+' · 简历</title><style>'+css+'</style></head><body>'
        '<main class="sheet"><header class="header"><h1>'+name+'</h1><div class="contact">'+contact+
        '</div>'+intro+'</header>'+''.join(sections)+'</main></body></html>'
    )
