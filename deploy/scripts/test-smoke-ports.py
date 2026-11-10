"""Offline tests for the rootless smoke loopback port collision guard."""
import importlib.util
import pathlib
import socket
import unittest
from unittest.mock import patch

SCRIPT = pathlib.Path(__file__).with_name("check-smoke-ports.py")
spec = importlib.util.spec_from_file_location("check_smoke_ports", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PortGuardTests(unittest.TestCase):
    def test_checks_only_baseline_loopback_ports(self):
        self.assertEqual(module.PORTS, (5173, 8000))

    def test_unavailable_port_is_rejected(self):
        with patch.object(module.socket, "socket") as mock_socket:
            mock_socket.return_value.__enter__.return_value.bind.side_effect = OSError("in use")
            self.assertFalse(module.available(5173))

    def test_free_port_is_accepted(self):
        with patch.object(module.socket, "socket") as mock_socket:
            self.assertTrue(module.available(8000))
            mock_socket.return_value.__enter__.return_value.bind.assert_called_once_with(("127.0.0.1", 8000))

    def test_main_fails_closed_if_first_port_unavailable(self):
        with patch.object(module, "available", side_effect=[False]) as mock_available:
            self.assertEqual(module.main(), 2)
            mock_available.assert_called_once_with(5173)

    def test_main_succeeds_only_if_both_ports_available(self):
        with patch.object(module, "available", side_effect=[True, True]) as mock_available:
            self.assertEqual(module.main(), 0)
            self.assertEqual(mock_available.call_count, 2)


if __name__ == "__main__":
    unittest.main()
