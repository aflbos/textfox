#!/usr/bin/env python3
"""Exercise the AutoConfig installer with Gecko's actual profile file APIs."""

import hashlib
import json
from pathlib import Path

from gecko_session import browser_argument, gecko_profile


ROOT = Path(__file__).resolve().parents[1]
STYLESHEETS = ("userChrome.css", "userContent.css")
INSTALLER = (ROOT / "nix/pkgs/install-profile.js").read_text(encoding="utf-8")


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


def check_profile(work, profile, execute):
    def install(source):
        return execute(installer_script(source))

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
    with gecko_profile(browser_argument(__doc__)) as (work, profile, execute):
        check_profile(work, profile, execute)


if __name__ == "__main__":
    main()
