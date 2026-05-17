"""Tests for PDF exporter module."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from tools.infra.export.pdf_exporter import (
    FALLBACK_LINE_WIDTH,
    PDF_FALLBACK_AVAILABLE,
    WEASYPRINT_AVAILABLE,
    _display_width,
    _wrap_pdf_line,
    is_pdf_export_available,
    markdown_to_pdf,
)


class TestPdfExporterAvailability:
    def test_availability_reflects_import_status(self):
        assert is_pdf_export_available() == (
            WEASYPRINT_AVAILABLE or PDF_FALLBACK_AVAILABLE
        )


class TestMarkdownToPdf:
    def test_raises_when_markdown_file_not_found(self):
        with TemporaryDirectory() as tmp:
            nonexistent = Path(tmp) / "nonexistent.md"
            pdf_path = Path(tmp) / "output.pdf"
            try:
                markdown_to_pdf(nonexistent, pdf_path)
                assert False, "Expected FileNotFoundError"
            except FileNotFoundError:
                pass

    def test_converts_without_weasyprint_via_builtin_fallback(self):
        if WEASYPRINT_AVAILABLE:
            return
        with TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "test.md"
            md_path.write_text("# Test", encoding="utf-8")
            pdf_path = Path(tmp) / "output.pdf"
            markdown_to_pdf(md_path, pdf_path)

            assert pdf_path.exists()
            assert pdf_path.read_bytes().startswith(b"%PDF-")
            assert pdf_path.stat().st_size > 0

    def test_fallback_is_used_when_markdown_package_is_missing(self):
        with TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "test.md"
            md_path.write_text("# Test", encoding="utf-8")
            pdf_path = Path(tmp) / "output.pdf"

            with patch("tools.infra.export.pdf_exporter.WEASYPRINT_AVAILABLE", True):
                with patch(
                    "tools.infra.export.pdf_exporter.MARKDOWN_AVAILABLE", False
                ):
                    markdown_to_pdf(md_path, pdf_path)

            assert pdf_path.exists()
            assert pdf_path.read_bytes().startswith(b"%PDF-")

    def test_converts_markdown_to_pdf(self):
        with TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "resume.md"
            pdf_path = Path(tmp) / "resume.pdf"
            md_content = """# Zhang San

## Contact
- Email: zhangsan@example.com
- Phone: 13800138000

## Experience
### Senior Engineer at ABC Corp (2020-2024)
- Led team of 5 developers
- Improved performance by 40%

### Developer at XYZ Inc (2018-2020)
- Built core platform features
- Collaborated with product team

## Skills
- Python, JavaScript, Go
- Kubernetes, Docker
- System Design
"""
            md_path.write_text(md_content, encoding="utf-8")
            markdown_to_pdf(md_path, pdf_path)
            assert pdf_path.exists()
            assert pdf_path.read_bytes().startswith(b"%PDF-")
            assert pdf_path.stat().st_size > 0

    def test_converts_with_chinese_characters(self):
        with TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "resume_cn.md"
            pdf_path = Path(tmp) / "resume_cn.pdf"
            md_content = """# 张三

## 联系方式
- 邮箱: zhangsan@example.com
- 电话: 13800138000

## 工作经历
### ABC公司 高级工程师 (2020-2024)
- 带领5人开发团队
- 提升系统性能40%

## 技能
- Python, JavaScript
- 系统架构设计
"""
            md_path.write_text(md_content, encoding="utf-8")
            markdown_to_pdf(md_path, pdf_path)
            assert pdf_path.exists()
            assert pdf_path.read_bytes().startswith(b"%PDF-")
            assert pdf_path.stat().st_size > 0

    def test_fallback_wraps_continuous_chinese_by_display_width(self):
        line = "- " + "主导低代码平台性能治理和稳定性建设" * 8

        wrapped = _wrap_pdf_line(line)

        assert len(wrapped) > 1
        assert all(_display_width(item) <= FALLBACK_LINE_WIDTH for item in wrapped)
