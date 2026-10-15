"""复用岗位来源正文解析，区分内联正文、文件与仅链接来源。"""
from pathlib import Path


def load_jd_source(source: str, job_path: Path | None) -> tuple[str, Path | None]:
    source = source.strip()
    if not source or source.startswith(("http://", "https://")):
        return "", None
    if source.endswith((".md", ".txt")) and "\n" not in source:
        candidates = ([job_path.parent / source, job_path.parent.parent / source] if job_path else []) + [Path(source)]
        jd_path = next((path for path in candidates if path.is_file()), None)
        return (jd_path.read_text(encoding="utf-8"), jd_path) if jd_path else ("", None)
    return source, None
