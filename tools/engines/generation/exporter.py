from __future__ import annotations

from pathlib import Path

from tools.domain.models import ResumeOutput


class ResumeExporter:
    def export_markdown(self, resume: ResumeOutput, output_dir: str) -> Path:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"resume_{resume.version}.md"
        path.write_text(resume.content, encoding="utf-8")
        return path
