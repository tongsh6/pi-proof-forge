import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.cli.entrypoints import main


class CliEntrypointsTests(unittest.TestCase):
    def test_unknown_command_returns_2(self) -> None:
        code = main(["unknown"])
        self.assertEqual(code, 2)

    def test_agent_command_runs_and_writes_run_log(self) -> None:
        with TemporaryDirectory() as tmp:
            policy = Path(tmp) / "policy.yaml"
            policy.write_text(
                """n_pass_required: 1
matching_threshold: 0.6
evaluation_threshold: 0.6
max_rounds: 2
gate_mode: strict
delivery_mode: auto
batch_review: false
excluded_companies: []
excluded_legal_entities: []
""",
                encoding="utf-8",
            )
            output_dir = Path(tmp) / "agent_runs"
            code = main(
                [
                    "agent",
                    "--policy",
                    str(policy),
                    "--dry-run",
                    "--run-id",
                    "run-cli-1",
                    "--output-dir",
                    str(output_dir),
                ]
            )
            self.assertEqual(code, 0)
            self.assertTrue((output_dir / "run-cli-1" / "run_log.json").exists())


def test_retired_batch_approval_cannot_modify_unreviewed_evidence(tmp_path, monkeypatch):
    import json
    from tools.infra.material_documents import split_material_documents

    material_id = "mat_synthetic"
    card_id = "ec_batch_synthetic"
    materials = tmp_path / "materials"
    cards = tmp_path / "evidence_cards"
    progress = tmp_path / "outputs" / "batch_extract"
    for directory in (materials, cards, progress):
        directory.mkdir(parents=True)
    text = "# Source: 合成项目/验收记录.md\n合成接口回归验证通过。\n"
    (materials / (material_id + ".txt")).write_text(text, encoding="utf-8")
    (materials / (material_id + ".meta.yaml")).write_text(
        f'material_id: "{material_id}"\nfilename: "{material_id}.txt"\nextension: ".txt"\n',
        encoding="utf-8",
    )
    document, = split_material_documents(text, material_id + ".txt")
    reference = {"material_id": material_id, **{key: document[key] for key in ("document_id", "sha256", "label")}}
    scalars = {"id": card_id, "title": "合成待审核证据", "status": "draft",
               "candidate_pool_eligible": "false", "review_decision": "pending",
               "source_documents_json": json.dumps([reference], ensure_ascii=False)}
    lines = [f"{key}: {json.dumps(value)}" for key, value in scalars.items()]
    for key, values in {"results": ["合成接口回归验证通过。"], "artifacts": [material_id],
                        "source_material_ids": [material_id]}.items():
        lines.extend([key + ":", *["  - " + json.dumps(value) for value in values]])
    (cards / (card_id + ".yaml")).write_text("\n".join(lines) + "\n", encoding="utf-8")
    (progress / (material_id + ".json")).write_text(
        json.dumps({"clusters": {"合成项目": {"status": "done", "cards": [card_id]}}}),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    before = {str(path.relative_to(tmp_path)): path.read_bytes()
              for path in tmp_path.rglob("*") if path.is_file()}
    code = main(["extract-batch", "--material-id", material_id, "--approve-batch"])
    after = {str(path.relative_to(tmp_path)): path.read_bytes()
             for path in tmp_path.rglob("*") if path.is_file()}
    assert after == before
    assert code == 2


if __name__ == "__main__":
    _ = unittest.main()
