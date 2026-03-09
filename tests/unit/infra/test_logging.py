import json
import unittest
from contextlib import redirect_stdout
from io import StringIO

from tools.infra.logging import make_logger


class StructuredLoggingTests(unittest.TestCase):
    def test_logger_emits_json_line(self) -> None:
        logger = make_logger(run_id="run-001")
        buf = StringIO()

        with redirect_stdout(buf):
            logger.info("state_change", state="DISCOVER", round=0)

        payload = json.loads(buf.getvalue().strip())
        self.assertEqual(payload["run_id"], "run-001")
        self.assertEqual(payload["event"], "state_change")
        self.assertEqual(payload["state"], "DISCOVER")
        self.assertEqual(payload["round"], 0)


if __name__ == "__main__":
    _ = unittest.main()
