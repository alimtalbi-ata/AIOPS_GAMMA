#!/usr/bin/env python3
"""Fail closed if the loopback TCP ports published by the baseline are occupied."""
import socket
import sys

PORTS = (5173, 8000)


def available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError as exc:
            print(f"Refusing rootless smoke: 127.0.0.1:{port} unavailable ({exc})", file=sys.stderr)
            return False
    return True


def main():
    # Probe every baseline port before Compose startup; not an atomic
    # reservation and not a substitute for a dedicated host.
    return 0 if all(available(port) for port in PORTS) else 2


if __name__ == "__main__":
    sys.exit(main())
