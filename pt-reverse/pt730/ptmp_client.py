#!/usr/bin/env python3
"""Minimal Packet Tracer PTMP text-mode probe client.

This is intentionally a protocol probe, not a full Packet Tracer API client.
It verifies the socket-level IPC path used by Packet Tracer 7.3.0:

  TCP -> PTMP negotiation -> authentication -> post-auth application messages

After authentication, Packet Tracer 7.3.0 disconnects unregistered clients with
"Cep Not Registered". That is expected until we can register a valid ExApp/CEP
or install an in-process Script Module bridge.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence, Tuple


NEGOTIATION_REQUEST = 0
NEGOTIATION_RESPONSE = 1
AUTH_REQUEST = 2
AUTH_CHALLENGE = 3
AUTH_RESPONSE = 4
AUTH_STATUS = 5
KEEPALIVE = 6
DISCONNECT = 7


@dataclass(frozen=True)
class PTMPMessage:
    length: int
    msg_type: int
    fields: List[str]


class PTMPClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 39000, timeout: float = 3.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None

    def __enter__(self) -> "PTMPClient":
        self.connect()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def send(self, msg_type: int, fields: Sequence[str] = ()) -> None:
        if self.sock is None:
            raise RuntimeError("not connected")
        value = ("\0".join(fields) + ("\0" if fields else "")).encode("utf-8")
        type_bytes = f"{msg_type}\0".encode("ascii")
        body = type_bytes + value
        packet = f"{len(body)}\0".encode("ascii") + body
        self.sock.sendall(packet)

    def recv(self, timeout: Optional[float] = None) -> Optional[PTMPMessage]:
        if self.sock is None:
            raise RuntimeError("not connected")
        old_timeout = self.sock.gettimeout()
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            length_bytes = self._recv_until_nul()
            if length_bytes is None:
                return None
            length = int(length_bytes.decode("ascii"))
            body = self._recv_exact(length)
            if body is None:
                return None
            parts = [p.decode("utf-8", "replace") for p in body.split(b"\0") if p]
            if not parts:
                return PTMPMessage(length=length, msg_type=-1, fields=[])
            return PTMPMessage(length=length, msg_type=int(parts[0]), fields=parts[1:])
        except socket.timeout:
            return None
        finally:
            if timeout is not None:
                self.sock.settimeout(old_timeout)

    def _recv_until_nul(self) -> Optional[bytes]:
        assert self.sock is not None
        data = bytearray()
        while True:
            chunk = self.sock.recv(1)
            if not chunk:
                return None
            if chunk == b"\0":
                return bytes(data)
            data.extend(chunk)

    def _recv_exact(self, length: int) -> Optional[bytes]:
        assert self.sock is not None
        data = bytearray()
        while len(data) < length:
            chunk = self.sock.recv(length - len(data))
            if not chunk:
                return None
            data.extend(chunk)
        return bytes(data)

    def negotiate(self, client_version: str = ":PTVER7.3.0.0838") -> Optional[PTMPMessage]:
        # PTMP fields from Cisco's spec, text encoding:
        # protocol, version, instance uuid, encoding, encryption, compression,
        # auth, timestamp, keepalive, reserved/client version.
        fields = [
            "PTMP",
            "1",
            "{" + str(uuid.uuid4()).upper() + "}",
            "1",
            "1",
            "1",
            "1",
            time.strftime("%Y%m%d%H%M%S"),
            "0",
            client_version,
        ]
        self.send(NEGOTIATION_REQUEST, fields)
        return self.recv()

    def authenticate(self, username: str = "codex.pt.cli", digest: str = "", custom: str = "") -> List[Optional[PTMPMessage]]:
        self.send(AUTH_REQUEST, [username])
        challenge = self.recv()
        self.send(AUTH_RESPONSE, [username, digest, custom])
        status = self.recv()
        return [challenge, status]


def fmt_message(message: Optional[PTMPMessage]) -> str:
    if message is None:
        return "<no message>"
    return f"type={message.msg_type} length={message.length} fields={message.fields!r}"


def run_probe(args: argparse.Namespace) -> int:
    with PTMPClient(args.host, args.port, args.timeout) as client:
        print("connected")
        negotiation = client.negotiate(args.client_version)
        print("negotiation:", fmt_message(negotiation))
        for label, message in zip(("auth-challenge", "auth-status"), client.authenticate(args.username)):
            print(f"{label}:", fmt_message(message))
        for i in range(args.drain):
            message = client.recv(args.drain_timeout)
            print(f"post-auth[{i}]:", fmt_message(message))
            if message is None:
                break
    return 0


def run_send(args: argparse.Namespace) -> int:
    fields = args.fields or []
    with PTMPClient(args.host, args.port, args.timeout) as client:
        client.negotiate(args.client_version)
        client.authenticate(args.username)
        client.send(args.type, fields)
        for i in range(args.drain):
            print(f"recv[{i}]:", fmt_message(client.recv(args.drain_timeout)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Packet Tracer 7.3.0 PTMP probe")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=39000)
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--client-version", default=":PTVER7.3.0.0838")
    parser.add_argument("--username", default="codex.pt.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)

    probe = sub.add_parser("probe", help="negotiate, authenticate, and read post-auth status")
    probe.add_argument("--drain", type=int, default=2)
    probe.add_argument("--drain-timeout", type=float, default=1.0)
    probe.set_defaults(func=run_probe)

    send = sub.add_parser("send", help="send one raw post-auth text PTMP message")
    send.add_argument("type", type=int)
    send.add_argument("fields", nargs="*")
    send.add_argument("--drain", type=int, default=2)
    send.add_argument("--drain-timeout", type=float, default=1.0)
    send.set_defaults(func=run_send)
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
