"""正式 HTML/PDF 导出契约；纯文本降级路径已退役。"""

from html.parser import HTMLParser
from pathlib import Path
import os
import signal
from unittest.mock import Mock, patch

import pytest

from tools.infra.export import pdf_exporter as exporter


@pytest.mark.skipif(os.getenv('PIPF_LIVE_PDF_TEST') != '1', reason='显式启用本机字体/PDF 真实导出检查')
def test_live_pdf_chinese_text_round_trips_without_radicals(tmp_path):
    pdf = pytest.importorskip('pypdf')
    source, output = tmp_path / 'chinese.md', tmp_path / 'chinese.pdf'
    source.write_text('# 子龙\n## 项目经历\n### 门店租赁\n- 用户登记流程', encoding='utf-8')
    exporter.markdown_to_pdf(source, output)
    extracted = ''.join(''.join(page.extract_text() or '' for page in pdf.PdfReader(output).pages).split())
    for original in ('子龙', '项目经历', '门店租赁', '用户登记流程'):
        assert original in extracted


class HtmlContent(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


def test_resume_html_preserves_content_and_escapes_active_markup():
    content = (
        '# 候选人\n13800000000 | a@example.com | 上海\n'
        '当前定位：后端工程师\n求职意向：Java专家\n'
        '## 核心技能\nJava、Redis\n## 项目经历\n### 订单平台（2024-2025）\n'
        '角色：Owner\n- 请求延迟降低 20%\n'
        '## 教育经历\n某大学，计算机专业\n'
        '<script>alert(1)</script><img src="https://example.com/track">\n'
    )
    html = exporter._markdown_to_html(content)
    parsed = HtmlContent()
    parsed.feed(html)
    text = ' '.join(parsed.text)
    for value in ['候选人', 'a@example.com', 'Java', 'Redis', '请求延迟降低', '20%', '某大学，计算机专业']:
        assert value in text
    assert 'script' not in parsed.tags
    assert 'img' not in parsed.tags
    assert 'default-src' in html
    assert text.count('请求延迟降低') == 1


def test_missing_renderer_is_explicit_and_does_not_replace_existing_pdf(tmp_path):
    source = tmp_path / 'resume.md'
    source.write_text('# 候选人', encoding='utf-8')
    destination = tmp_path / 'resume.pdf'
    destination.write_bytes(b'old-pdf')
    with patch.object(exporter, '_find_chromium', return_value=None, create=True), patch.object(exporter, 'WEASYPRINT_AVAILABLE', False):
        assert exporter.is_pdf_export_available() is False
        with pytest.raises(RuntimeError, match='PDF_RENDERER_UNAVAILABLE'):
            exporter.markdown_to_pdf(source, destination)
    assert destination.read_bytes() == b'old-pdf'


def test_export_passes_shared_html_to_renderer_and_writes_html_artifact(tmp_path):
    source = tmp_path / 'resume.md'
    source.write_text('# 候选人\n## 核心技能\nJava', encoding='utf-8')
    destination = tmp_path / 'nested/resume.pdf'
    observed = []

    def render(html_path, pdf_path):
        observed.append(html_path.read_text(encoding='utf-8'))
        pdf_path.write_bytes(b'%PDF-1.7\nrendered\n%%EOF\n')

    with patch.object(exporter, '_render_html_to_pdf', side_effect=render, create=True):
        exporter.markdown_to_pdf(source, destination)
    assert observed == [exporter._markdown_to_html(source.read_text())]
    assert destination.read_bytes().startswith(b'%PDF-')
    assert destination.with_suffix('.html').read_text() == observed[0]


def test_invalid_render_output_does_not_replace_existing_pdf(tmp_path):
    source = tmp_path / 'resume.md'
    source.write_text('# 候选人', encoding='utf-8')
    destination = tmp_path / 'resume.pdf'
    destination.write_bytes(b'old-pdf')
    with patch.object(exporter, '_render_html_to_pdf', side_effect=lambda _, path: path.write_bytes(b'%PDF-partial'), create=True):
        with pytest.raises(RuntimeError, match='PDF_RENDER_INVALID'):
            exporter.markdown_to_pdf(source, destination)
    assert destination.read_bytes() == b'old-pdf'


def test_missing_markdown_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        exporter.markdown_to_pdf(tmp_path / 'missing.md', tmp_path / 'resume.pdf')


@pytest.mark.skipif(os.name != 'posix', reason='POSIX 进程组清理契约')
@pytest.mark.parametrize('completed', [False, True])
def test_renderer_cleans_its_own_process_group_on_completion_or_timeout(tmp_path, completed):
    source, destination = tmp_path / 'source.html', tmp_path / 'out.pdf'
    source.write_text('<html></html>', encoding='utf-8')
    process = Mock(pid=424242)
    process.poll.return_value = None
    process.wait.return_value = 0
    if completed:
        destination.write_bytes(b'%PDF-1.7\nbody\n%%EOF\n')
    with patch.object(exporter.subprocess, 'Popen', return_value=process) as launch, patch.object(exporter.os, 'killpg') as kill, patch.object(exporter.time, 'monotonic', side_effect=[0, 30]):
        if completed:
            exporter._render_with_chromium(Path('/test/browser'), source, destination)
        else:
            with pytest.raises(RuntimeError, match='PDF_RENDER_TIMEOUT'):
                exporter._render_with_chromium(Path('/test/browser'), source, destination)
    assert launch.call_args.kwargs['start_new_session'] is True
    kill.assert_called_once_with(process.pid, signal.SIGTERM)
    process.wait.assert_called_once_with(timeout=1)


def test_weasyprint_fallback_uses_the_bounded_worker(tmp_path):
    source, destination = tmp_path / 'source.html', tmp_path / 'out.pdf'
    source.write_text('<html></html>', encoding='utf-8')
    with patch.object(exporter, '_find_chromium', return_value=None), patch.object(exporter, 'WEASYPRINT_AVAILABLE', True), patch.object(exporter, '_run_renderer_command', create=True) as worker:
        exporter._render_html_to_pdf(source, destination)
    assert worker.called
    assert str(source) in worker.call_args.args[0]
    assert str(destination) in worker.call_args.args[0]


@pytest.mark.skipif(os.name != 'posix', reason='POSIX 进程回收契约')
def test_denied_group_signal_falls_back_to_owned_process_handle():
    process = Mock(pid=424242)
    process.poll.return_value = None
    process.wait.return_value = 0
    with patch.object(exporter.os, 'killpg', side_effect=PermissionError):
        exporter._stop_renderer(process)
    process.terminate.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=1)


def test_position_and_unknown_pipe_headers_are_not_contact_fields():
    from tools.infra.export.resume_html import parse_resume_markdown
    content = '# 候选人\n13800000000 | a@example.com | 上海\n当前定位：Java Tech Lead | 系统架构师\n偏好：Owner | Technical Lead\n'
    data = parse_resume_markdown(content)
    assert data['contact']['city'] == '上海'
    html = exporter._markdown_to_html(content)
    assert '当前定位：Java Tech Lead | 系统架构师' in html
    assert '偏好：Owner | Technical Lead' in html


def test_document_section_language_is_preserved():
    html = exporter._markdown_to_html('# Candidate\n## Skills\nPython\n## Experience\n### Platform\n- Delivered an API\n')
    assert '<h2>Skills</h2>' in html
    assert '<h2>Experience</h2>' in html


@pytest.mark.skipif(os.name != 'posix', reason='POSIX 遗留 helper 清理契约')
@pytest.mark.parametrize('denied', [False, True])
def test_exited_parent_still_attempts_owned_group_cleanup(denied):
    process = Mock(pid=424242)
    process.poll.return_value = 0
    process.wait.return_value = 0
    with patch.object(exporter.os, 'killpg', side_effect=PermissionError if denied else None) as kill:
        exporter._stop_renderer(process)
    kill.assert_called_once_with(process.pid, signal.SIGTERM)
    process.terminate.assert_not_called()


def test_resume_preserves_section_order_and_renders_markdown_emphasis():
    text='# 候选人\n## 职业概述\n真实概述\n## 工作经历\n### 公司A（2022-2024）\n- **交易系统**：使用 Java\n## 核心技能\nJava\n## 项目经历\n### 项目B\n- 缓存设计\n## 教育经历\n大学\n'
    html=exporter._markdown_to_html(text)
    assert html.index('真实概述')<html.index('公司A')<html.index('核心技能')<html.index('项目B')<html.index('大学')
    assert '<strong>交易系统</strong>' in html
    assert '##' not in html


def test_truncated_emphasis_does_not_leak_markers_or_change_code_facts():
    html=exporter._markdown_to_html('# 候选人\n## 项目经历\n### 性能治理\n- 成果**：查询 **2–3s → 300–400ms**（本机验证）\n- 保留代码 `value ** 2` 和 **完整强调**')
    parsed=HtmlContent();parsed.feed(html);body=' '.join(parsed.text)
    assert '成果：查询 2–3s → 300–400ms（本机验证）' in body
    assert 'value ** 2' in body
    assert '<strong>完整强调</strong>' in html
