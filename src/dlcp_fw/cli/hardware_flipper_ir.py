#!/usr/bin/env python3
"""Send named IR actions to a Flipper Zero over its USB CLI serial port."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
import re
import select
import termios
import time
from typing import Sequence


ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
DEFAULT_BAUD = termios.B115200
DEFAULT_TIMEOUT_S = 2.0
DEFAULT_IDLE_S = 0.2


@dataclasses.dataclass(frozen=True)
class IrActionSpec:
    action: str
    protocol: str
    address: int
    command: int
    aliases: tuple[str, ...] = ()


ACTION_SPECS: tuple[IrActionSpec, ...] = (
    IrActionSpec("F1", "RC5", 0x10, 0x38),
    IrActionSpec("F2", "RC5", 0x10, 0x39),
    IrActionSpec("MUTE", "RC5", 0x10, 0x35),
    IrActionSpec("POWER", "RC5", 0x10, 0x32, aliases=("POWER_TOGGLE", "FLIP")),
    IrActionSpec("STANDBY", "RC5", 0x10, 0x3A, aliases=("STDBY",)),
    IrActionSpec("WAKE", "RC5", 0x10, 0x3B),
    IrActionSpec("VOL_UP", "RC5", 0x10, 0x33, aliases=("VOLUME_UP",)),
    IrActionSpec("VOL_DOWN", "RC5", 0x10, 0x34, aliases=("VOLUME_DOWN",)),
    IrActionSpec("INPUT_UP", "RC5", 0x10, 0x36),
    IrActionSpec("INPUT_DOWN", "RC5", 0x10, 0x37),
)


def _json_dumps(data: object) -> str:
    return json.dumps(data, indent=2, sort_keys=True)


def _normalize_action_name(action: str) -> str:
    return action.strip().upper().replace("-", "_").replace(" ", "_")


def _looks_like_flipper_serial_port(path: Path) -> bool:
    name = path.name.lower()
    return "flipper" in name or "usbmodemflip" in name or "flip_" in name


def discover_flipper_serial_ports() -> list[str]:
    return [
        str(path)
        for path in sorted(Path("/dev").glob("cu.*"))
        if _looks_like_flipper_serial_port(path)
    ]


def resolve_flipper_serial_port(*, port: str | None = None) -> str:
    if port:
        return port
    ports = discover_flipper_serial_ports()
    if not ports:
        raise RuntimeError("no Flipper Zero serial port found")
    if len(ports) > 1:
        raise RuntimeError(
            f"multiple Flipper Zero serial ports found: {ports}; pass --port explicitly"
        )
    return ports[0]


def resolve_action_spec(action: str) -> IrActionSpec:
    key = _normalize_action_name(action)
    for spec in ACTION_SPECS:
        if key == spec.action or key in spec.aliases:
            return spec
    available = sorted(spec.action for spec in ACTION_SPECS)
    raise RuntimeError(f"unknown IR action {action!r}; available actions: {available}")


def _configure_serial_fd(fd: int) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0
    attrs[4] = DEFAULT_BAUD
    attrs[5] = DEFAULT_BAUD
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)


def _read_until_idle(fd: int, *, timeout_s: float, idle_s: float) -> bytes:
    deadline = time.monotonic() + timeout_s
    last_data_at: float | None = None
    chunks: list[bytes] = []
    while True:
        now = time.monotonic()
        if last_data_at is not None and now - last_data_at >= idle_s:
            break
        if now >= deadline:
            break
        wait_s = min(0.2, deadline - now)
        if last_data_at is not None:
            wait_s = min(wait_s, max(0.0, idle_s - (now - last_data_at)))
        readable, _, _ = select.select([fd], [], [], wait_s)
        if not readable:
            continue
        try:
            data = os.read(fd, 4096)
        except BlockingIOError:
            continue
        if not data:
            continue
        chunks.append(data)
        last_data_at = time.monotonic()
    return b"".join(chunks)


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def issue_cli_command(
    port: str,
    command: str,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    idle_s: float = DEFAULT_IDLE_S,
) -> str:
    fd = os.open(port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        _configure_serial_fd(fd)
        os.write(fd, f"{command}\r".encode("utf-8"))
        raw = _read_until_idle(fd, timeout_s=timeout_s, idle_s=idle_s)
    finally:
        os.close(fd)
    return raw.decode("utf-8", errors="replace")


def _response_has_cli_error(clean_text: str) -> bool:
    lowered = clean_text.lower()
    return (
        "unknown command" in lowered
        or "error:" in lowered
        or "failed" in lowered
        or ("usage:" in lowered and "ir tx" in lowered)
    )


def send_ir_action(
    *,
    action: str,
    port: str | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    idle_s: float = DEFAULT_IDLE_S,
) -> dict[str, object]:
    spec = resolve_action_spec(action)
    resolved_port = resolve_flipper_serial_port(port=port)
    cli_command = f"ir tx {spec.protocol} {spec.address:02X} {spec.command:02X}"
    raw_response = issue_cli_command(
        resolved_port,
        cli_command,
        timeout_s=timeout_s,
        idle_s=idle_s,
    )
    clean_response = strip_ansi(raw_response)
    if _response_has_cli_error(clean_response):
        raise RuntimeError(
            f"Flipper CLI rejected command {cli_command!r} on {resolved_port}: {clean_response!r}"
        )
    return {
        "action": _normalize_action_name(action),
        "canonical_action": spec.action,
        "protocol": spec.protocol,
        "address_hex": f"{spec.address:02X}",
        "command_hex": f"{spec.command:02X}",
        "port": resolved_port,
        "cli_command": cli_command,
        "raw_response": raw_response,
        "clean_response": clean_response,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action", help="named IR action, e.g. F1, F2, MUTE, POWER, STANDBY, WAKE")
    parser.add_argument("--port", help="Flipper Zero serial port; auto-detect when omitted")
    parser.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    parser.add_argument("--idle-s", type=float, default=DEFAULT_IDLE_S)
    parser.add_argument("--list-actions", action="store_true", help="print supported logical actions and exit")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_actions:
        payload = [
            {
                "action": spec.action,
                "aliases": list(spec.aliases),
                "protocol": spec.protocol,
                "address_hex": f"{spec.address:02X}",
                "command_hex": f"{spec.command:02X}",
            }
            for spec in ACTION_SPECS
        ]
        print(_json_dumps(payload))
        return 0
    if not args.action:
        raise SystemExit("--action is required unless --list-actions is used")
    payload = send_ir_action(
        action=args.action,
        port=args.port,
        timeout_s=args.timeout_s,
        idle_s=args.idle_s,
    )
    print(_json_dumps(payload))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
