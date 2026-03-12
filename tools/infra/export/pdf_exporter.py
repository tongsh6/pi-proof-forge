"""PDF exporter for converting Markdown to PDF."""

from __future__ import annotations

from pathlib import Path

try:
    import markdown
    from weasyprint import HTML, CSS

    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False


def _markdown_to_html(md_content: str) -> str:
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


def markdown_to_pdf(md_path: Path, pdf_path: Path) -> None:
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_path}")
    if not WEASYPRINT_AVAILABLE:
        raise RuntimeError(
            "PDF export requires weasyprint and markdown packages. "
            "Install with: pip install weasyprint markdown"
        )
    md_content = md_path.read_text(encoding="utf-8")
    html_content = _markdown_to_html(md_content)
    css = CSS(string=_get_resume_css())
    HTML(string=html_content).write_pdf(str(pdf_path), stylesheets=[css])


def is_pdf_export_available() -> bool:
    return WEASYPRINT_AVAILABLE
