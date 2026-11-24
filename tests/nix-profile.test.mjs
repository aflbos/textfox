import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { posix as path } from "node:path";
import { test } from "node:test";
import vm from "node:vm";

const script = readFileSync(new URL("../nix/pkgs/install-profile.js", import.meta.url), "utf8");

// Exercise the AutoConfig script with an isolated, in-memory Firefox filesystem.
function profileFixture() {
  const files = new Map();
  const directories = new Set(["/profile", "/profile/chrome"]);
  const links = new Set();
  const messages = [];
  const absent = 1;
  let failWrite;
  let competingFile;
  let restarts = 0;

  function stamped(css) {
    const digest = createHash("sha256").update(css).digest("hex");
    return Buffer.from("/* Textfox Nix SHA-256: " + digest + " */\n" + css);
  }

  class File {
    constructor(name) { this.path = name; }
    get leafName() { return path.basename(this.path); }
    clone() { return new File(this.path); }
    append(name) { this.path = path.join(this.path, name); }
    isDirectory() { return directories.has(this.path); }
    isFile() { return files.has(this.path); }
    isSymlink() {
      if (links.has(this.path)) return true;
      if (this.isDirectory() || this.isFile()) return false;
      throw Object.assign(new Error("missing file"), { result: absent });
    }
    create() { directories.add(this.path); }
  }

  function inputStream() {
    let unread;
    return {
      init(file) { unread = files.get(file.path); },
      available() { return unread.length; },
      read(length) {
        const bytes = unread.subarray(0, length);
        unread = unread.subarray(length);
        return bytes;
      },
      close() {},
    };
  }

  function createCompetingFile(file) {
    if (file.leafName !== competingFile?.name) return;
    files.set(file.path, Buffer.from(competingFile.content));
    competingFile = undefined;
  }

  const factories = {
    "@mozilla.org/network/file-input-stream;1": inputStream,
    "@mozilla.org/network/file-output-stream;1": () => ({
      init(file, flags) {
        createCompetingFile(file);
        assert.ok(flags & 0x80, "expected PR_EXCL for first installation");
        if (file.isFile() || links.has(file.path)) throw new Error("already exists");
        this.path = file.path;
        files.set(this.path, Buffer.alloc(0));
      },
      set bytes(value) { files.set(this.path, value); },
      close() {},
    }),
    "@mozilla.org/binaryinputstream;1": () => ({
      setInputStream(input) { this.input = input; },
      readBytes(length) { return this.input.read(length).toString("latin1"); },
      readByteArray(length) { return Array.from(this.input.read(length)); },
    }),
    "@mozilla.org/binaryoutputstream;1": () => ({
      setOutputStream(output) { this.output = output; },
      writeByteArray(bytes) { this.output.bytes = Buffer.from(bytes); },
    }),
    "@mozilla.org/security/hash;1": () => ({
      initWithString(name) { this.hash = createHash(name); },
      updateFromStream(stream, length) { this.hash.update(stream.read(length)); },
      finish() { return this.hash.digest("latin1"); },
    }),
  };

  const context = {
    ChromeUtils: {
      importESModule() {
        return {
          FileUtils: {
            File,
            PERMS_DIRECTORY: 0o755,
            PERMS_FILE: 0o644,
            MODE_WRONLY: 0x02,
            MODE_CREATE: 0x08,
            openSafeFileOutputStream(file) {
              createCompetingFile(file);
              return {
                QueryInterface() { return this; },
                finish() {
                  if (file.leafName === failWrite) throw new Error("disk full");
                  files.set(file.path, this.bytes);
                },
                close() {},
              };
            },
          },
        };
      },
    },
    Components: {
      classes: Object.fromEntries(Object.entries(factories).map(([name, createInstance]) => [
        name, { createInstance },
      ])),
      interfaces: { nsIFile: {}, nsIAppStartup: { eRestart: 1, eForceQuit: 2 } },
      results: { NS_ERROR_FILE_NOT_FOUND: absent },
    },
    Services: {
      dirsvc: { get(key) { assert.equal(key, "ProfD"); return new File("/profile"); } },
      console: { logStringMessage(message) { messages.push(message); } },
      startup: {
        quit(mode) {
          assert.equal(mode, 3);
          restarts += 1;
        },
      },
    },
  };

  const target = (name) => path.join("/profile/chrome", name);
  return {
    directories,
    links,
    messages,
    target,
    get restarts() { return restarts; },
    failOn(name) { failWrite = name; },
    createBeforeOpen(name, content) { competingFile = { name, content }; },
    set(name, value) { files.set(target(name), Buffer.from(value)); },
    get(name) { return files.get(target(name))?.toString("utf8"); },
    install(version) {
      for (const name of ["userChrome.css", "userContent.css"]) {
        files.set(path.join("/store", name), stamped("/* " + name + " " + version + " ç */\n"));
      }
      vm.runInNewContext(script + '\ninstallTextfoxProfile("/store");', context);
    },
  };
}

test("install and upgrade preserve other profile files and restart only when CSS changes", () => {
  const profile = profileFixture();
  profile.set("config.css", "custom config");
  profile.set("other/theme.css", "another theme");
  profile.install("v1");
  profile.install("v2");
  profile.install("v2");
  assert.match(profile.get("userChrome.css"), /userChrome\.css v2 ç/);
  assert.match(profile.get("userContent.css"), /userContent\.css v2 ç/);
  assert.equal(profile.get("config.css"), "custom config");
  assert.equal(profile.get("other/theme.css"), "another theme");
  assert.equal(profile.restarts, 2);
});

test("install creates the chrome directory in a fresh profile", () => {
  const profile = profileFixture();
  profile.directories.delete("/profile/chrome");
  profile.install("v1");
  assert.ok(profile.directories.has("/profile/chrome"));
  assert.match(profile.get("userChrome.css"), /v1/);
  assert.match(profile.get("userContent.css"), /v1/);
  assert.equal(profile.restarts, 1);
});

test("first installation keeps a stylesheet created between the check and open", () => {
  const profile = profileFixture();
  profile.createBeforeOpen("userChrome.css", "new user CSS");
  profile.install("v1");
  assert.equal(profile.get("userChrome.css"), "new user CSS");
  assert.equal(profile.get("userContent.css"), undefined);
  assert.equal(profile.restarts, 0);
  assert.match(profile.messages.join("\n"), /already exists/);
});

test("a symlinked chrome directory blocks installation", () => {
  const profile = profileFixture();
  profile.links.add("/profile/chrome");
  profile.install("v1");
  assert.equal(profile.get("userContent.css"), undefined);
  assert.equal(profile.get("userChrome.css"), undefined);
  assert.equal(profile.restarts, 0);
  assert.match(profile.messages.join("\n"), /symbolic link/);
});

test("a legacy marker never authorizes replacement of a profile stylesheet", () => {
  const profile = profileFixture();
  profile.set("old-hash-textfox-chrome", "");
  profile.set("userContent.css", "original legacy CSS");
  profile.install("v2");
  assert.equal(profile.get("userContent.css"), "original legacy CSS");
  assert.equal(profile.get("old-hash-textfox-chrome"), "");
  assert.equal(profile.get("userChrome.css"), undefined);
  assert.equal(profile.restarts, 0);
  assert.match(profile.messages.join("\n"), /userContent\.css/);
});

test("a checksum header does not authorize replacing locally edited content", () => {
  const profile = profileFixture();
  profile.install("v1");
  const changed = profile.get("userContent.css") + "/* local edit */\n";
  profile.set("userContent.css", changed);
  profile.install("v2");
  assert.equal(profile.get("userContent.css"), changed);
  assert.match(profile.get("userChrome.css"), /v1/);
  assert.equal(profile.restarts, 1);
});

test("a dangling stylesheet symlink blocks installation", () => {
  const profile = profileFixture();
  profile.links.add(profile.target("userContent.css"));
  profile.install("v1");
  assert.equal(profile.get("userContent.css"), undefined);
  assert.equal(profile.get("userChrome.css"), undefined);
  assert.equal(profile.restarts, 0);
  assert.match(profile.messages.join("\n"), /userContent\.css/);
});

test("retries finish an interrupted update with no ownership marker to repair", () => {
  const profile = profileFixture();
  profile.install("v1");
  profile.failOn("userContent.css");
  profile.install("v2");
  assert.match(profile.get("userChrome.css"), /v2/);
  assert.match(profile.get("userContent.css"), /v1/);
  assert.equal(profile.restarts, 1);
  profile.failOn(undefined);
  profile.install("v2");
  assert.match(profile.get("userContent.css"), /v2/);
  assert.equal(profile.restarts, 2);
});
