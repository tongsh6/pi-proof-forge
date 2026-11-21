"""JD 方向判定：识别"同名不同义"的岗位。

实测教训：猎聘里「中后端负责人」「后端工程师」可能指芯片物理设计
（Floorplan / CTS / Routing / STA / DFT），与互联网 Java 后端完全无关，
只看岗位标题会把芯片岗当成目标岗位。方向判定必须以 JD 正文为准。
"""
from __future__ import annotations

# 芯片/硬件方向的高区分度术语：单个出现可能是巧合（如"综合能力"），
# 两个及以上同时出现即判定为芯片方向。
CHIP_TERMS: tuple[str, ...] = (
    "Floorplan",
    "CTS",
    "Routing",
    "STA",
    "DFT",
    "ATPG",
    "UPF",
    "CPF",
    "PPA",
    "版图",
    "时钟树",
    "物理设计",
    "网表",
    "签核",
    "低功耗检查",
    "时序收敛",
    "mbist",
    "scan chain",
)

MIN_CHIP_HITS = 2


def detect_direction_mismatch(jd_text: str) -> tuple[bool, tuple[str, ...]]:
    """返回（是否方向不符，命中的芯片术语）。只看 JD 正文，不看标题。"""
    text = str(jd_text or "")
    hits = tuple(term for term in CHIP_TERMS if term in text)
    return len(hits) >= MIN_CHIP_HITS, hits
