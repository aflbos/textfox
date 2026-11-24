#!/usr/bin/env python3
"""Exercise the AutoConfig installer with Gecko's actual profile file APIs."""

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
STYLESHEETS = ("userChrome.css", "userContent.css")
INSTALLER = (ROOT / "nix/pkgs/install-profile.js").read_text(encoding="utf-8")


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


def package(directory, version):
    directory.mkdir()
    for name in STYLESHEETS:
        body = (f"/* {name}: {version} — " + ("áßπ" * 800) + " */\n").encode()
        checksum = hashlib.sha256(body).hexdigest()
        (directory / name).write_bytes(
            f"/* Textfox Nix SHA-256: {checksum} */\n".encode() + body
        )
    return directory


def installer_script(source):
    return """
const nativeServices = Services;
const messages = [];
let restarts = 0;
((Services) => {
""" + INSTALLER + """
installTextfoxProfile(""" + json.dumps(str(source)) + """);
})({
  dirsvc: nativeServices.dirsvc,
  console: {logStringMessage(message) { messages.push(message); }},
  startup: {quit() { restarts += 1; }}
});
return {messages, restarts, version: nativeServices.appinfo.version};
"""


def check_profile(work, profile, command):
    def install(source):
        return command("WebDriver:ExecuteScript", {
            "script": installer_script(source),
            "args": [], "newSandbox": True, "sandbox": "system",
        })["value"]

    def check_stylesheets(source):
        for name in STYLESHEETS:
            assert (chrome / name).read_bytes() == (source / name).read_bytes(), name

    chrome = profile / "chrome"
    first = package(work / "first", "v1")
    second = package(work / "second", "v2")
    corrupt = package(work / "corrupt", "v3")
    (corrupt / "userContent.css").write_bytes(b"/* bad checksum */\n")

    result = install(first)
    assert result["restarts"] == 1 and not result["messages"], result
    check_stylesheets(first)
    print(f"PASS fresh profile with byte-exact CSS (Gecko {result['version']})")

    unrelated = chrome / "unrelated.css"
    unrelated.write_bytes(b"/* user custom file */\n")
    result = install(second)
    assert result["restarts"] == 1 and not result["messages"], result
    check_stylesheets(second)
    assert unrelated.read_bytes() == b"/* user custom file */\n"
    print("PASS managed upgrade preserves unrelated files")

    result = install(second)
    assert result["restarts"] == 0 and not result["messages"], result
    print("PASS reapplying the same version is a no-op")

    result = install(corrupt)
    assert result["restarts"] == 0 and any(
        "Invalid Nix package stylesheet" in item for item in result["messages"]
    ), result
    check_stylesheets(second)
    print("PASS invalid package leaves both stylesheets intact")

    edited = chrome / "userContent.css"
    content = edited.read_bytes() + b"/* local rule */\n"
    edited.write_bytes(content)
    result = install(first)
    assert result["restarts"] == 0 and any(
        "Keeping userContent.css" in item for item in result["messages"]
    ), result
    assert edited.read_bytes() == content
    assert (chrome / "userChrome.css").read_bytes() == (second / "userChrome.css").read_bytes()
    print("PASS edited CSS blocks changes to both stylesheets")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("browser", type=Path, help="Path to the Firefox or Waterfox executable")
    browser = parser.parse_args().browser.resolve(strict=True)
    if not browser.is_file():
        parser.error("The browser path must point to an executable file.")

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
            "marionette.port": port,
            "browser.shell.checkDefaultBrowser": False,
            "browser.aboutwelcome.enabled": False,
            "datareporting.policy.dataSubmissionEnabled": False,
            "app.update.auto": False,
        }
        (profile / "user.js").write_text(
            "\n".join(f"user_pref({json.dumps(key)}, {json.dumps(value)});"
                      for key, value in prefs.items()) + "\n",
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
                        assert request_id == response_id
                        if error:
                            raise RuntimeError(error)
                        return result

                    command("WebDriver:NewSession", {"capabilities": {"alwaysMatch": {}}})
                    command("Marionette:SetContext", {"value": "chrome"})
                    try:
                        check_profile(work, profile, command)
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


if __name__ == "__main__":
    main()
