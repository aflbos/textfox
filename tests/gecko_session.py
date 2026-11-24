"""Launch an offline Gecko chrome session with a disposable profile."""

import argparse
from contextlib import contextmanager
import itertools
import json
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time


def browser_argument(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("browser", type=Path, help="Path to the Firefox or Waterfox executable")
    browser = parser.parse_args().browser.resolve()
    if not browser.is_file():
        parser.error("The browser path must point to an executable file.")
    return browser


def connect(port, process, log):
    deadline = time.monotonic() + 15
    while process.poll() is None and time.monotonic() < deadline:
        try:
            return socket.create_connection(("127.0.0.1", port), timeout=0.5)
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(
        f"Marionette did not start (exit {process.poll()}).\n"
        f"{log.read_text(encoding='utf-8', errors='replace')}"
    )


def receive(stream):
    length = b""
    while (piece := stream.read(1)) != b":":
        if not piece:
            raise EOFError("Marionette closed the connection.")
        length += piece
    return json.loads(stream.read(int(length)))


@contextmanager
def gecko_profile(browser, *, preferences=None, theme_dir=None):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    temp = Path(tempfile.gettempdir()).resolve()
    with tempfile.TemporaryDirectory(
        prefix="textfox-gecko-", dir=temp, ignore_cleanup_errors=True
    ) as scratch:
        work = Path(scratch)
        profile = work / "profile"
        profile.mkdir()
        prefs = {
            "browser.shell.checkDefaultBrowser": False,
            "browser.aboutwelcome.enabled": False,
            "datareporting.policy.dataSubmissionEnabled": False,
            "app.update.auto": False,
        }
        if preferences:
            prefs.update(preferences)
        prefs["marionette.port"] = port
        seed = ""
        if theme_dir is not None:
            shutil.copytree(theme_dir / "chrome", profile / "chrome")
            seed = (theme_dir / "user.js").read_text(encoding="utf-8") + "\n"
        (profile / "user.js").write_text(
            seed + "\n".join(
                f"user_pref({json.dumps(key)}, {json.dumps(value)});"
                for key, value in prefs.items()
            ) + "\n",
            encoding="utf-8",
        )

        log = work / "browser.log"
        with log.open("wb") as output:
            process = subprocess.Popen(
                [str(browser), "-headless", "-no-remote", "-offline", "-marionette",
                 "-remote-allow-system-access", "-profile", str(profile), "about:blank"],
                stdout=output, stderr=output,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            try:
                with connect(port, process, log) as connection, connection.makefile("rb") as stream:
                    connection.settimeout(15)
                    receive(stream)
                    request_ids = itertools.count(1)

                    def command(name, params=None):
                        request_id = next(request_ids)
                        payload = json.dumps([0, request_id, name, params or {}]).encode()
                        connection.sendall(str(len(payload)).encode() + b":" + payload)
                        _, response_id, error, result = receive(stream)
                        if request_id != response_id:
                            raise RuntimeError(f"Unexpected Marionette response ID {response_id}")
                        if error:
                            raise RuntimeError(error)
                        return result

                    def execute(script, *args):
                        return command("WebDriver:ExecuteScript", {
                            "script": script, "args": args, "newSandbox": True, "sandbox": "system",
                        })["value"]

                    command("WebDriver:NewSession", {"capabilities": {"alwaysMatch": {}}})
                    command("Marionette:SetContext", {"value": "chrome"})
                    try:
                        yield work, profile, execute
                    finally:
                        try:
                            command("Marionette:Quit", {"flags": ["eAttemptQuit"]})
                        except (EOFError, OSError, RuntimeError):
                            pass
            finally:
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=8)
