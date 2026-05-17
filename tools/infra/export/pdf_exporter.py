"""PDF exporter for converting Markdown to PDF."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import markdown

    MARKDOWN_AVAILABLE = True
except ImportError:
    markdown = None
    MARKDOWN_AVAILABLE = False

try:
    from weasyprint import HTML, CSS

    WEASYPRINT_AVAILABLE = True
except ImportError:
    HTML = None
    CSS = None
    WEASYPRINT_AVAILABLE = False

PDF_FALLBACK_AVAILABLE = True
FALLBACK_LINE_WIDTH = 82


def _markdown_to_html(md_content: str) -> str:
    if markdown is None:
        raise RuntimeError("markdown package is required for HTML conversion")
    html_body = markdown.markdown(md_content, extensions=["extra", "nl2br"])
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Resume</title>
</head>
<body>
    {html_body}
</body>
</html>"""


def _get_resume_css() -> str:
    return """
        @page {
            margin: 2cm 2.5cm;
            size: A4;
        }

        body {
            font-family: "Noto Sans CJK SC", "WenQuanYi Micro Hei", "SimHei", "SimSun", sans-serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
        }

        h1 {
            font-size: 20pt;
            font-weight: bold;
            margin: 0 0 12pt 0;
            padding-bottom: 6pt;
            border-bottom: 2pt solid #333;
            color: #000;
        }

        h2 {
            font-size: 14pt;
            font-weight: bold;
            margin: 16pt 0 8pt 0;
            padding-bottom: 4pt;
            border-bottom: 1pt solid #ccc;
            color: #222;
        }

        h3 {
            font-size: 12pt;
            font-weight: bold;
            margin: 12pt 0 6pt 0;
            color: #333;
        }

        p {
            margin: 6pt 0;
            text-align: justify;
        }

        ul, ol {
            margin: 6pt 0;
            padding-left: 20pt;
        }

        li {
            margin: 3pt 0;
        }

        code {
            font-family: "Consolas", "Monaco", monospace;
            background-color: #f5f5f5;
            padding: 1pt 3pt;
            font-size: 10pt;
        }

        pre {
            background-color: #f5f5f5;
            padding: 8pt;
            overflow-x: auto;
            font-size: 9pt;
            line-height: 1.4;
        }

        blockquote {
            margin: 8pt 0;
            padding-left: 12pt;
            border-left: 3pt solid #ccc;
            color: #666;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin: 10pt 0;
        }

        th, td {
            border: 1pt solid #ddd;
            padding: 6pt;
            text-align: left;
        }

        th {
            background-color: #f5f5f5;
            font-weight: bold;
        }

        hr {
            border: none;
            border-top: 1pt solid #ccc;
            margin: 16pt 0;
        }
        h1, h2, h3 {
            page-break-after: avoid;
        }
        p, li {
            page-break-inside: avoid;
        }
    """


def _markdown_to_plain_lines(md_content: str) -> list[str]:
    lines: list[str] = []
    in_fenced_block = False

    for raw_line in md_content.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            in_fenced_block = not in_fenced_block
            continue

        if not stripped:
            lines.append("")
            continue

        if not in_fenced_block:
            stripped = re.sub(r"^#{1,6}\s+", "", stripped)
            stripped = re.sub(r"^[-*+]\s+", "- ", stripped)
            stripped = re.sub(r"^\d+\.\s+", "- ", stripped)
            stripped = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped)
            stripped = re.sub(r"__(.*?)__", r"\1", stripped)
            stripped = re.sub(r"`([^`]*)`", r"\1", stripped)
            stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)
            line = stripped
        else:
            line = f"    {line}"

        lines.extend(_wrap_pdf_line(line))

    return lines or [""]


def _wrap_pdf_line(line: str) -> list[str]:
    if not line:
        return [""]

    if _display_width(line) <= FALLBACK_LINE_WIDTH:
        return [line]

    subsequent_indent = "  " if line.startswith("- ") else ""
    wrapped: list[str] = []
    current = ""
    current_width = 0
    max_width = FALLBACK_LINE_WIDTH

    for char in line:
        char_width = _char_display_width(char)
        if current and current_width + char_width > max_width:
            wrapped.append(current.rstrip())
            current = subsequent_indent if subsequent_indent else ""
            current_width = _display_width(current)
        current += char
        current_width += char_width

    if current:
        wrapped.append(current.rstrip())
    return wrapped or [line]


def _display_width(text: str) -> int:
    return sum(_char_display_width(char) for char in text)


def _char_display_width(char: str) -> int:
    return 2 if ord(char) > 127 else 1


def _pdf_hex_text(text: str) -> str:
    return (b"\xfe\xff" + text.encode("utf-16-be", errors="replace")).hex().upper()


def _build_basic_pdf(lines: list[str]) -> bytes:
    page_width = 595
    page_height = 842
    margin_x = 50
    top_y = 790
    line_height = 16
    lines_per_page = 46
    pages = [
        lines[index : index + lines_per_page]
        for index in range(0, len(lines), lines_per_page)
    ] or [[""]]

    objects: list[bytes] = []

    def add_object(body: str | bytes) -> int:
        objects.append(body.encode("utf-8") if isinstance(body, str) else body)
        return len(objects)

    catalog_id = add_object("PLACEHOLDER")
    pages_id = add_object("PLACEHOLDER")
    font_id = add_object("PLACEHOLDER")
    cid_font_id = add_object("PLACEHOLDER")
    descriptor_id = add_object("PLACEHOLDER")

    page_ids: list[int] = []
    content_ids: list[int] = []

    for page_lines in pages:
        commands = [
            "BT",
            f"/F1 11 Tf {line_height} TL",
            f"1 0 0 1 {margin_x} {top_y} Tm",
        ]
        for line_index, text in enumerate(page_lines):
            if line_index:
                commands.append("T*")
            commands.append(f"<{_pdf_hex_text(text)}> Tj")
        commands.append("ET")
        stream = "\n".join(commands).encode("utf-8")
        content_id = add_object(
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n"
            + stream
            + b"\nendstream"
        )
        page_id = add_object("PLACEHOLDER")
        content_ids.append(content_id)
        page_ids.append(page_id)

    objects[catalog_id - 1] = f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode(
        "utf-8"
    )
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[pages_id - 1] = (
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("utf-8")
    )
    objects[font_id - 1] = (
        f"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light "
        f"/Encoding /UniGB-UCS2-H /DescendantFonts [{cid_font_id} 0 R] >>"
    ).encode("utf-8")
    objects[cid_font_id - 1] = (
        f"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 2 >> "
        f"/FontDescriptor {descriptor_id} 0 R >>"
    ).encode("utf-8")
    objects[descriptor_id - 1] = (
        "<< /Type /FontDescriptor /FontName /STSong-Light /Flags 6 "
        "/FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 880 "
        "/Descent -120 /CapHeight 700 /StemV 80 >>"
    ).encode("utf-8")

    for page_id, content_id in zip(page_ids, content_ids):
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent {pages_id} 0 R "
            f"/MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("utf-8")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(output)


def _write_basic_pdf(md_content: str, pdf_path: Path) -> None:
    pdf_path.write_bytes(_build_basic_pdf(_markdown_to_plain_lines(md_content)))


def markdown_to_pdf(md_path: Path, pdf_path: Path) -> None:
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_path}")
    md_content = md_path.read_text(encoding="utf-8")
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if WEASYPRINT_AVAILABLE and MARKDOWN_AVAILABLE:
        html_content = _markdown_to_html(md_content)
        css = CSS(string=_get_resume_css())
        HTML(string=html_content).write_pdf(str(pdf_path), stylesheets=[css])
        return
    _write_basic_pdf(md_content, pdf_path)


def is_pdf_export_available() -> bool:
    return WEASYPRINT_AVAILABLE or PDF_FALLBACK_AVAILABLE
