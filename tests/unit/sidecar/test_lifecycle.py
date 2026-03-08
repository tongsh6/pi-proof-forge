import unittest

from tools.sidecar.lifecycle import handle_handshake, handle_ping, handle_shutdown


class HandshakeTests(unittest.TestCase):
    def test_handshake_returns_accepted_version(self) -> None:
        params = {
            "meta": {"correlation_id": "corr_001"},
            "ui_version": "0.1.0",
            "protocol_version": "1.0.0",
            "capabilities": ["events", "file-preview", "pdf-export"],
        }
        result = handle_handshake(params)
        self.assertEqual(result["meta"]["correlation_id"], "corr_001")
        self.assertEqual(result["accepted_protocol_version"], "1.0.0")
        self.assertIn("sidecar_version", result)
        self.assertIsInstance(result["capabilities"], list)
        self.assertIsInstance(result["deprecations"], list)

    def test_handshake_unsupported_version(self) -> None:
        params = {
            "meta": {"correlation_id": "corr_002"},
            "ui_version": "0.1.0",
            "protocol_version": "99.0.0",
            "capabilities": [],
        }
        with self.assertRaises(ValueError) as ctx:
            handle_handshake(params)
        self.assertIn("UNSUPPORTED_VERSION", str(ctx.exception))


class PingTests(unittest.TestCase):
    def test_ping_returns_state_and_timestamp(self) -> None:
        params = {"meta": {"correlation_id": "corr_003"}}
        result = handle_ping(params)
        self.assertEqual(result["meta"]["correlation_id"], "corr_003")
        self.assertIn(result["state"], ("starting", "ready", "degraded", "reconnecting", "disconnected", "stopped"))
        self.assertIn("timestamp", result)


class ShutdownTests(unittest.TestCase):
    def test_shutdown_accepted(self) -> None:
        params = {
            "meta": {"correlation_id": "corr_004"},
            "graceful": True,
        }
        result = handle_shutdown(params)
        self.assertEqual(result["meta"]["correlation_id"], "corr_004")
        self.assertTrue(result["accepted"])


if __name__ == "__main__":
    unittest.main()
