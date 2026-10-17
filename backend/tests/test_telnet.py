import socket
import threading

import pytest

from app.telnet_client import OltConnectionError, TelnetSession


def serve(password_ok=True):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def run():
        c, _ = srv.accept()
        f = c.makefile("rwb", buffering=0)
        c.sendall(bytes([255, 253, 1]) + b"Username:")
        f.readline()
        c.sendall(b"Password:")
        f.readline()
        if not password_ok:
            c.sendall(b"\r\n% Login failed\r\nUsername:")
            c.close()
            return
        c.sendall(b"\r\nZXAN#")
        while True:
            line = f.readline()
            if not line:
                break
            cmd = line.strip().decode()
            c.sendall(f"{cmd}\r\nout of {cmd}\r\nZXAN#".encode())
    threading.Thread(target=run, daemon=True).start()
    return srv.getsockname()[1]


def test_session_runs_command():
    port = serve()
    with TelnetSession("127.0.0.1", port, "u", "p", 3, 3) as s:
        assert s.run("show x") == "out of show x"


def test_bad_login():
    port = serve(False)
    with pytest.raises(OltConnectionError):
        TelnetSession("127.0.0.1", port, "u", "p", 3, 3).open()


def test_refused():
    with pytest.raises(OltConnectionError):
        TelnetSession("127.0.0.1", 1, "u", "p", 1, 1).open()
