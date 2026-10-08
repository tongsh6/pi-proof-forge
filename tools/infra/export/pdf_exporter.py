"""用统一 HTML 模板输出正式 PDF，不静默降级为纯文本。"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .resume_html import render_resume_html

try:
    from weasyprint import HTML
    WEASYPRINT_AVAILABLE = True
except (ImportError, OSError):
    HTML = None
    WEASYPRINT_AVAILABLE = False

PDF_RENDER_TIMEOUT_SECONDS = 20.0


def _markdown_to_html(md_content: str) -> str:
    return render_resume_html(md_content)


def _find_chromium() -> Path | None:
    override = os.getenv('PIPF_PDF_BROWSER', '').strip()
    if override:
        path = Path(override).expanduser()
        return path if path.is_file() and os.access(path, os.X_OK) else None
    home = Path.home()
    caches = [home / 'Library/Caches/ms-playwright', home / '.cache/ms-playwright']
    if os.getenv('PLAYWRIGHT_BROWSERS_PATH'):
        caches.insert(0, Path(os.environ['PLAYWRIGHT_BROWSERS_PATH']))
    candidates: list[Path] = []
    for cache in caches:
        candidates.extend(sorted(cache.glob('chromium_headless_shell-*/*/chrome-headless-shell'), reverse=True))
        candidates.extend(sorted(cache.glob('chromium_headless_shell-*/*/headless_shell.exe'), reverse=True))
    candidates.extend([
        Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
        Path('/Applications/Chromium.app/Contents/MacOS/Chromium'),
    ])
    for name in ('chrome-headless-shell', 'chromium', 'chromium-browser', 'google-chrome'):
        path = shutil.which(name)
        if path:
            candidates.append(Path(path))
    if sys.platform == 'win32':
        for name in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
            if os.getenv(name):
                candidates.append(Path(os.environ[name]) / 'Google/Chrome/Application/chrome.exe')
    return next((path for path in candidates if path.is_file() and os.access(path, os.X_OK)), None)


def _pdf_complete(path: Path) -> bool:
    try:
        with path.open('rb') as stream:
            if stream.read(5) != b'%PDF-':
                return False
            stream.seek(max(0, path.stat().st_size - 1024))
            return stream.read().rstrip().endswith(b'%%EOF')
    except OSError:
        return False


def _stop_renderer(process: subprocess.Popen) -> None:
    # 仅清理本次 start_new_session 创建的进程组，不触碰用户浏览器。
    parent_exited = process.poll() is not None
    try:
        if os.name == 'posix':
            os.killpg(process.pid, signal.SIGTERM)
        elif not parent_exited:
            process.terminate()
    except ProcessLookupError:
        pass
    except PermissionError:
        # macOS 可能禁止向含受限 helper 的整个组发信号，退回已持有的子进程句柄。
        if not parent_exited:
            process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            if os.name == 'posix':
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
        except ProcessLookupError:
            pass
        except PermissionError:
            process.kill()
        process.wait(timeout=1)


def _render_with_chromium(browser: Path, html_path: Path, pdf_path: Path) -> None:
    command = [
        str(browser), '--headless', '--disable-gpu', '--disable-background-networking',
        '--disable-component-update', '--disable-sync', '--no-first-run',
        '--no-default-browser-check', '--no-pdf-header-footer',
        f'--user-data-dir={html_path.parent / "browser-profile"}',
        f'--print-to-pdf={pdf_path}', html_path.as_uri(),
    ]
    _run_renderer_command(command, html_path, pdf_path)


def _run_renderer_command(command: list[str], html_path: Path, pdf_path: Path) -> None:
    with (html_path.parent / 'renderer.log').open('wb') as log:
        try:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=os.name == 'posix')
        except OSError as exc:
            raise RuntimeError('PDF_RENDER_FAILED: 无法启动本机 PDF 渲染器') from exc
        deadline = time.monotonic() + PDF_RENDER_TIMEOUT_SECONDS
        try:
            while True:
                if _pdf_complete(pdf_path):
                    return
                if process.poll() is not None:
                    raise RuntimeError('PDF_RENDER_FAILED: 渲染器未产生完整 PDF')
                if time.monotonic() >= deadline:
                    raise RuntimeError('PDF_RENDER_TIMEOUT: PDF 渲染超时')
                time.sleep(0.05)
        finally:
            _stop_renderer(process)


def _render_html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    browser = _find_chromium()
    if browser is not None:
        _render_with_chromium(browser, html_path, pdf_path)
    elif WEASYPRINT_AVAILABLE:
        _run_renderer_command([
            sys.executable, '-c',
            'from weasyprint import HTML; import sys; HTML(filename=sys.argv[1]).write_pdf(sys.argv[2])',
            str(html_path), str(pdf_path),
        ], html_path, pdf_path)
    else:
        raise RuntimeError('PDF_RENDERER_UNAVAILABLE: 未找到已安装的 Chromium/Chrome 或 WeasyPrint；HTML 预览仍可使用')


def markdown_to_pdf(md_path: Path, pdf_path: Path) -> None:
    md_path, pdf_path = Path(md_path), Path(pdf_path)
    if not md_path.is_file():
        raise FileNotFoundError(md_path)
    html = _markdown_to_html(md_path.read_text(encoding='utf-8'))
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.pipf-pdf-', dir=pdf_path.parent) as temporary:
        root = Path(temporary).resolve()
        html_path, rendered = root / 'resume.html', root / 'resume.pdf'
        html_path.write_text(html, encoding='utf-8')
        _render_html_to_pdf(html_path, rendered)
        if not _pdf_complete(rendered):
            raise RuntimeError('PDF_RENDER_INVALID: 渲染结果不完整，原 PDF 已保留')
        html_path.replace(pdf_path.with_suffix('.html'))
        rendered.replace(pdf_path)


def is_pdf_export_available() -> bool:
    return _find_chromium() is not None or WEASYPRINT_AVAILABLE
