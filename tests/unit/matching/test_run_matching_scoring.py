import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.run_matching_scoring import main


class RunMatchingScoringExclusionTests(unittest.TestCase):
    def test_returns_2_when_company_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            _ = policy_path.write_text(
                "\n".join(
                    [
                        "exclusion_list:",
                        "  - 'contains:Outsource'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            job_profile = Path(tmp_dir) / "jp-001.yaml"
            _ = job_profile.write_text(
                "\n".join(
                    [
                        "target_role: 'Backend Engineer'",
                        "company: 'Outsource Labs'",
                        "source_jd: 'https://example.com/jd'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            evidence_dir = Path(tmp_dir) / "evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            output_path = Path(tmp_dir) / "mr-001.yaml"
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                argv = [
                    "run_matching_scoring.py",
                    "--job-profile",
                    str(job_profile),
                    "--evidence-dir",
                    str(evidence_dir),
                    "--output",
                    str(output_path),
                ]
                with mock.patch("sys.argv", argv):
                    code = main()
            log_path = output_path.parent / "run_log.json"
            log_text = log_path.read_text(encoding="utf-8")
        self.assertEqual(code, 2)
        self.assertIn("excluded_by_policy", log_text)

    def test_returns_2_when_legal_entity_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            policy_path = Path(tmp_dir) / "policy.yaml"
            _ = policy_path.write_text(
                "\n".join(
                    [
                        "excluded_legal_entities:",
                        "  - 'Acme Holdings Ltd'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            job_profile = Path(tmp_dir) / "jp-002.yaml"
            _ = job_profile.write_text(
                "\n".join(
                    [
                        "target_role: 'Backend Engineer'",
                        "company: 'Acme Staffing'",
                        "legal_entity: 'Acme Holdings Ltd'",
                        "source_jd: 'https://example.com/jd/2'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            evidence_dir = Path(tmp_dir) / "evidence"
            evidence_dir.mkdir(parents=True, exist_ok=True)
            output_path = Path(tmp_dir) / "mr-002.yaml"
            with mock.patch.dict(os.environ, {"PPF_POLICY_PATH": str(policy_path)}):
                argv = [
                    "run_matching_scoring.py",
                    "--job-profile",
                    str(job_profile),
                    "--evidence-dir",
                    str(evidence_dir),
                    "--output",
                    str(output_path),
                ]
                with mock.patch("sys.argv", argv):
                    code = main()
        self.assertEqual(code, 2)


if __name__ == "__main__":
    _ = unittest.main()


def test_llm_candidate_prefilter_keeps_rule_ranked_top_cards(tmp_path):
    """证据池超过上限时只把规则分最高的卡交给模型；不超过上限时原样返回。"""
    from tools.run_matching_scoring import rank_cards_by_rule, select_llm_candidate_files

    profile = tmp_path / "jp.yaml"
    profile.write_text('target_role: "Java"\nkeywords:\n  - "Java"\n  - "MongoDB"\n', encoding="utf-8")
    cards = tmp_path / "cards"
    cards.mkdir()
    (cards / "ec_low.yaml").write_text('title: "前端页面"\nrole_scope: ""\nresults:\n  - "完成"\nartifacts:\n  - "a"\n', encoding="utf-8")
    (cards / "ec_mid.yaml").write_text('title: "Java 服务"\nrole_scope: ""\nresults:\n  - "QPS 提升 30%"\nartifacts:\n  - "a"\n', encoding="utf-8")
    (cards / "ec_top.yaml").write_text('title: "Java MongoDB 改造"\nrole_scope: "总体技术负责人"\nresults:\n  - "耗时从 38s 降到 5.8s"\n  - "往返 201208 次降至 508 次"\nartifacts:\n  - "a"\n  - "b"\n', encoding="utf-8")
    files = sorted(cards.glob("*.yaml"))
    ranked = rank_cards_by_rule(str(profile), files)
    assert [path.stem for path, _ in ranked] == ["ec_top", "ec_mid", "ec_low"]
    assert ranked[0][1] == 2 * 3 + 2 * 2 + 2 + 2
    assert [p.stem for p in select_llm_candidate_files(str(profile), files, 2)] == ["ec_top", "ec_mid"]
    assert select_llm_candidate_files(str(profile), files, 3) == files
    assert select_llm_candidate_files(str(profile), files, 0) == files
