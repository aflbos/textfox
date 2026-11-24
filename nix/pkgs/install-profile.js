/* global ChromeUtils, Components, Services */

function installTextfoxProfile(storePath) {
  const { classes: Cc, interfaces: Ci, results: Cr } = Components;
  const names = ["userChrome.css", "userContent.css"];
  const header = /^\/\* Textfox Nix SHA-256: ([a-f0-9]{64}) \*\/\n$/;
  const headerLength = "/* Textfox Nix SHA-256: ".length + 64 + " */\n".length;

  function fileType(file, isExpectedType) {
    try {
      return !file.isSymlink() && isExpectedType(file) ? "expected" : "conflict";
    } catch (error) {
      if (error.result === Cr.NS_ERROR_FILE_NOT_FOUND) return "missing";
      throw error;
    }
  }

  function read(file, consume) {
    const input = Cc["@mozilla.org/network/file-input-stream;1"].createInstance(Ci.nsIFileInputStream);
    input.init(file, -1, -1, 0);
    try {
      const binary = Cc["@mozilla.org/binaryinputstream;1"].createInstance(Ci.nsIBinaryInputStream);
      binary.setInputStream(input);
      return consume(input, binary);
    } finally {
      input.close();
    }
  }

  function managedDigest(file) {
    return read(file, (input, binary) => {
      if (input.available() < headerLength) return null;
      const match = header.exec(binary.readBytes(headerLength));
      if (!match) return null;
      const hash = Cc["@mozilla.org/security/hash;1"].createInstance(Ci.nsICryptoHash);
      hash.initWithString("sha256");
      hash.updateFromStream(input, 0xffffffff);
      const digest = Array.from(hash.finish(false), (byte) =>
        byte.charCodeAt(0).toString(16).padStart(2, "0")
      ).join("");
      return digest === match[1] ? digest : null;
    });
  }

  function write(output, bytes, replace) {
    try {
      const binary = Cc["@mozilla.org/binaryoutputstream;1"].createInstance(Ci.nsIBinaryOutputStream);
      binary.setOutputStream(output);
      binary.writeByteArray(bytes);
      if (replace) {
        output.QueryInterface(Ci.nsISafeOutputStream).finish();
      } else {
        output.close();
      }
    } catch (error) {
      output.close();
      throw error;
    }
  }

  function warn(message) {
    Services.console.logStringMessage("Textfox Nix: " + message);
  }

  try {
    const { FileUtils } = ChromeUtils.importESModule("resource://gre/modules/FileUtils.sys.mjs");
    const chrome = Services.dirsvc.get("ProfD", Ci.nsIFile);
    chrome.append("chrome");
    const directoryType = fileType(chrome, (file) => file.isDirectory());
    if (directoryType === "conflict") {
      warn("The profile chrome path is a symbolic link or is not a directory. Skipping installation.");
      return;
    }

    // Verify both destinations before touching either one. Legacy hash markers
    // did not verify the stylesheets and cannot authorize their replacement.
    const updates = [];
    for (const name of names) {
      const destination = chrome.clone();
      destination.append(name);
      const type = fileType(destination, (file) => file.isFile());
      const previous = type === "expected" ? managedDigest(destination) : null;
      if (type !== "missing" && previous === null) {
        warn("Keeping " + name + ". Back it up and move it aside to let Textfox manage that path.");
        return;
      }

      const source = new FileUtils.File(storePath + "/" + name);
      const next = managedDigest(source);
      if (!next) throw new Error("Invalid Nix package stylesheet " + name);
      if (previous !== next) {
        const bytes = read(source, (input, binary) =>
          binary.readByteArray(input.available())
        );
        updates.push({ destination, previous, bytes });
      }
    }

    if (updates.length === 0) return;
    if (directoryType === "missing") {
      chrome.create(Ci.nsIFile.DIRECTORY_TYPE, FileUtils.PERMS_DIRECTORY);
    }
    for (const { destination, previous, bytes } of updates) {
      // Check again immediately before opening the output stream in case an
      // editor changed the file since the profile was inspected.
      if (fileType(chrome, (file) => file.isDirectory()) !== "expected") {
        throw new Error("Profile chrome directory changed during installation");
      }
      const type = fileType(destination, (file) => file.isFile());
      const unchanged = previous === null
        ? type === "missing"
        : type === "expected" && managedDigest(destination) === previous;
      if (!unchanged) {
        throw new Error("Profile stylesheet changed during installation: " + destination.leafName);
      }
      if (previous === null) {
        const output = Cc["@mozilla.org/network/file-output-stream;1"].createInstance(Ci.nsIFileOutputStream);
        const PR_EXCL = 0x80;
        // Gecko's safe output stream can replace a file that appears just after the check.
        output.init(destination, FileUtils.MODE_WRONLY | FileUtils.MODE_CREATE | PR_EXCL, FileUtils.PERMS_FILE, 0);
        write(output, bytes, false);
      } else {
        write(FileUtils.openSafeFileOutputStream(destination), bytes, true);
      }
    }
    Services.startup.quit(Ci.nsIAppStartup.eForceQuit | Ci.nsIAppStartup.eRestart);
  } catch (error) {
    warn("Could not install stylesheets: " + error);
  }
}
