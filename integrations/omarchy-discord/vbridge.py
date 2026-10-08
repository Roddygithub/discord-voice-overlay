#!/usr/bin/env python3
"""Adapt Vesktop's local voice-control socket to omarchy-discord's JSONL API."""

import json
import os
import select
import socket
import sys
import time

PROTOCOL_HEADER = "VESKTOP_VOICE_CONTROL/1.0"
RECONNECT_DELAY_SEC = 2.0


def socket_path():
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or "/run/user/%d" % os.getuid()
    return os.path.join(runtime_dir, "vesktop-voice-control.sock")


def emit(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def state_from_control(message):
    def number(value, fallback):
        try:
            return round(float(value))
        except (TypeError, ValueError):
            return fallback

    speaking = message.get("speaking")
    return {
        "ok": True,
        "channel": str(message.get("channel") or ""),
        "guild": str(message.get("guild") or ""),
        "mute": message.get("mute") is True,
        "deaf": message.get("deaf") is True,
        "inputVolume": number(message.get("inputVolume"), 100),
        "speaking": speaking if isinstance(speaking, list) else [],
        "error": "",
        "ping": number(message.get("ping"), 0),
        "voiceState": str(message.get("voiceState") or ""),
    }


def read_lines(fd, buffer):
    try:
        chunk = os.read(fd, 4096)
    except (BlockingIOError, InterruptedError):
        return buffer, []
    except OSError:
        chunk = b""
    if not chunk:
        return buffer, None
    buffer += chunk.decode("utf-8", "replace")
    lines = []
    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        line = line.strip()
        if line:
            lines.append(line)
    return buffer, lines


def read_header(conn):
    buffer = ""
    while "\n" not in buffer and len(buffer) <= 256:
        chunk = conn.recv(256)
        if not chunk:
            raise OSError("Vesktop closed before sending protocol header")
        buffer += chunk.decode("utf-8", "replace")
    if len(buffer) > 256 or "\n" not in buffer:
        raise OSError("invalid Vesktop voice-control header")
    header, remainder = buffer.split("\n", 1)
    if header.rstrip("\r") != PROTOCOL_HEADER:
        raise OSError("unexpected Vesktop voice-control header")
    return remainder


def probe():
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.settimeout(5)
    try:
        conn.connect(socket_path())
        remainder = read_header(conn)
        conn.sendall(b'{"cmd":"refresh"}\n')
        buffer = remainder
        while "\n" not in buffer:
            chunk = conn.recv(4096).decode("utf-8", "replace")
            if not chunk:
                raise OSError("Vesktop closed before returning state")
            buffer += chunk
        line = buffer.split("\n", 1)[0].strip()
        print("state: %s" % line)
        return 0
    except OSError as error:
        print("control socket: %s" % error)
        return 1
    finally:
        conn.close()


def main():
    if "--probe" in sys.argv:
        return probe()

    conn = None
    stdin_buffer = ""
    socket_buffer = ""
    while True:
        if conn is None:
            try:
                conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                conn.settimeout(5)
                conn.connect(socket_path())
                socket_buffer = read_header(conn)
                conn.setblocking(False)
                conn.sendall(b'{"cmd":"refresh"}\n')
            except OSError:
                if conn is not None:
                    conn.close()
                conn = None
                time.sleep(RECONNECT_DELAY_SEC)
                continue

        try:
            readable, _, _ = select.select([conn, sys.stdin], [], [], 1.0)
        except InterruptedError:
            continue

        if conn in readable:
            socket_buffer, lines = read_lines(conn.fileno(), socket_buffer)
            if lines is None:
                conn.close()
                conn = None
                continue
            for line in lines:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if message.get("type") == "state":
                    emit(state_from_control(message))

        if sys.stdin in readable:
            stdin_buffer, lines = read_lines(sys.stdin.fileno(), stdin_buffer)
            if lines is None:
                return 0
            for line in lines:
                try:
                    payload = json.loads(line)
                except ValueError:
                    continue
                if conn is not None:
                    try:
                        conn.sendall((json.dumps(payload) + "\n").encode())
                    except OSError:
                        conn.close()
                        conn = None


if __name__ == "__main__":
    sys.exit(main() or 0)
