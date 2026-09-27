import os
import socket
import subprocess
import sys
import time

import httpx
import pytest


@pytest.fixture(scope="session")
def serving_process(tmp_path_factory):
    path = tmp_path_factory.mktemp("integration")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {**os.environ, "OBSERVATORY_EXPORT": "false", "OBSERVATORY_PORT": str(port),
           "OBSERVATORY_SERVING_URL": f"http://127.0.0.1:{port}/v1",
           "OBSERVATORY_CAPTURE_TRACES": "true"}
    with (path / "server.log").open("w") as log:
        process = subprocess.Popen([sys.executable, "-m", "observatory.cli", "serve"],
                                   cwd=path, env=env, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    pytest.fail((path / "server.log").read_text())
                try:
                    if httpx.get(f"http://127.0.0.1:{port}/health", timeout=.5).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.1)
            else:
                pytest.fail("Serving process failed to become ready")
            yield path, env, port
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
