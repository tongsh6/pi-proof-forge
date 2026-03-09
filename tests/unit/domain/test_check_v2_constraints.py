import subprocess
import unittest


class CheckV2ConstraintsTests(unittest.TestCase):
    def test_constraints_script_passes_on_repo(self) -> None:
        result = subprocess.run(
            ["python3", "tools/check_v2_constraints.py", "--root", "."],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("PASS v2 constraints", result.stdout)


if __name__ == "__main__":
    _ = unittest.main()
