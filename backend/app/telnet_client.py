"""Minimal Telnet client (stdlib sockets only; `telnetlib` is removed in Python 3.13)."""
import logging
import re
import socket
import time

log = logging.getLogger("olt.telnet")

IAC, DONT, DO, WONT, WILL, SB, SE = 255, 254, 253, 252, 251, 250, 240
PROMPT_RE = re.compile(r"[\w\-./()]+[>#]\s*$")
MORE_RE = re.compile(r"--More--")
# After sending the password: either an error message line or the CLI prompt.
LOGIN_RESULT_RE = re.compile(r"(?i)(%?\s*(login )?(fail|incorrect|invalid|denied)[^\n]*|" + PROMPT_RE.pattern + ")")


class OltError(Exception):
    """Base error for OLT communication problems."""


class OltConnectionError(OltError):
    """Could not connect / authenticate."""


class OltCommandError(OltError):
    """The OLT rejected a command."""


class TelnetSession:
    def __init__(self, host, port, username, password, connect_timeout=8.0, command_timeout=20.0):
        self.host, self.port = host, int(port)
        self.username, self.password = username, password
        self.connect_timeout, self.command_timeout = connect_timeout, command_timeout
        self.sock = None

    # -- lifecycle ---------------------------------------------------------
    def open(self):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=self.connect_timeout)
        except OSError as e:
            log.error("Telnet connect to %s:%s failed: %s", self.host, self.port, e)
            raise OltConnectionError(f"Cannot connect to {self.host}:{self.port}: {e}") from e
        try:
            self._read_until(re.compile(r"(?i)(user ?name|login)\s*:\s*$"), self.connect_timeout)
            self._send(self.username)
            self._read_until(re.compile(r"(?i)password\s*:\s*$"), self.connect_timeout)
            self._send(self.password)
            out = self._read_until(LOGIN_RESULT_RE, self.connect_timeout)
            if re.search(r"(?i)(fail|incorrect|invalid|denied)", out):
                raise OltConnectionError("Authentication failed (check username/password)")
            self.run("terminal length 0", check=False)
        except OltConnectionError:
            self.close()
            raise
        except OltError as e:
            self.close()
            raise OltConnectionError(str(e)) from e
        log.info("Telnet session opened to %s:%s", self.host, self.port)

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    # -- commands ----------------------------------------------------------
    def run(self, command, check=True):
        log.info("OLT> %s", command)
        self._send(command)
        out = self._read_until(PROMPT_RE, self.command_timeout)
        lines = out.splitlines()
        if lines and lines[0].strip() == command.strip():
            lines = lines[1:]
        if lines and PROMPT_RE.search(lines[-1]):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
        if check and re.search(r"(?im)^\s*%?\s*(error|invalid input|incomplete command|unknown command)", text):
            log.error("OLT command failed: %s -> %s", command, text)
            raise OltCommandError(f"Command '{command}' failed: {text}")
        return text

    def run_many(self, commands):
        return [self.run(c) for c in commands]

    # -- low level ---------------------------------------------------------
    def _send(self, text):
        try:
            self.sock.sendall(text.encode("ascii", "ignore") + b"\r\n")
        except OSError as e:
            raise OltError(f"Send failed: {e}") from e

    def _read_until(self, pattern, timeout):
        deadline = time.monotonic() + timeout
        buf = ""
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OltError(f"Timeout waiting for device response (got: {buf[-80:]!r})")
            self.sock.settimeout(remaining)
            try:
                data = self.sock.recv(4096)
            except socket.timeout:
                raise OltError(f"Timeout waiting for device response (got: {buf[-80:]!r})")
            except OSError as e:
                raise OltError(f"Receive failed: {e}") from e
            if not data:
                raise OltError("Connection closed by device")
            buf += self._strip_iac(data)
            if MORE_RE.search(buf):
                buf = MORE_RE.sub("", buf)
                self._raw(b" ")
            if pattern.search(buf):
                return buf.replace("\r", "")

    def _raw(self, b):
        self.sock.sendall(b)

    def _strip_iac(self, data):
        out = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b == IAC and i + 1 < len(data):
                cmd = data[i + 1]
                if cmd in (DO, DONT, WILL, WONT) and i + 2 < len(data):
                    opt = data[i + 2]
                    if cmd == DO:
                        self._raw(bytes([IAC, WONT, opt]))
                    elif cmd == WILL:
                        self._raw(bytes([IAC, DONT, opt]))
                    i += 3
                    continue
                if cmd == SB:
                    end = data.find(bytes([IAC, SE]), i)
                    i = end + 2 if end != -1 else len(data)
                    continue
                i += 2
                continue
            out.append(b)
            i += 1
        return out.decode("ascii", "ignore")
