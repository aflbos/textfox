#!/usr/bin/env bash
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
temp=$(cd -- "${TMPDIR:-/tmp}" && pwd -P)
root=$(mktemp -d "$temp/textfox-profile-test.XXXXXXXX")
root=$(cd -- "$root" && pwd -P)
case "$root" in
  "$temp"/textfox-profile-test.*) trap 'rm -rf -- "$root"' EXIT ;;
  *) printf 'Invalid fixture path: %s\n' "$root" >&2; exit 1 ;;
esac

install() {
  printf '%s\n' "${2:-n}" | bash "$repo/tf-install.sh" "$1" >/dev/null
}

uninstall() {
  bash "$repo/tf-uninstall.sh" "$1" </dev/null >/dev/null
}

check() {
  if ! "$@"; then
    printf 'Assertion failed in %s: %s\n' "$scenario" "$*" >&2
    exit 1
  fi
}

scenario="Install alongside existing chrome assets"
profile="$root/profile [with spaces]"
mkdir -p "$profile/chrome/sine-mods/other"
printf 'custom\n' > "$profile/chrome/custom.css"
printf 'other mod\n' > "$profile/chrome/sine-mods/other/theme.json"
printf 'my preferences\n' > "$profile/user.js"
check install "$profile" y
check grep -qx custom "$profile/chrome/custom.css"
check grep -qx 'other mod' "$profile/chrome/sine-mods/other/theme.json"
check grep -qx 'my preferences' "$profile/user.js"
check grep -Fqx '@import url("textfox/userChrome.css");' "$profile/chrome/userChrome.css"
check grep -Fqx '@import url("textfox/userContent.css");' "$profile/chrome/userContent.css"
check test -f "$profile/chrome/textfox/icons/tab.svg"
printf 'PASS %s\n' "$scenario"

scenario="Update preserves custom configuration and archives the old package"
printf 'my config\n' > "$profile/chrome/textfox/config.css"
printf 'previous package\n' > "$profile/chrome/textfox/old-marker"
check install "$profile"
check grep -qx 'my config' "$profile/chrome/textfox/config.css"
check test ! -e "$profile/chrome/textfox/old-marker"
old_marker=$(find "$profile/chrome/textfox-backups" -name old-marker -type f)
check grep -qx 'previous package' "$old_marker"
printf 'PASS %s\n' "$scenario"

scenario="Uninstall preserves unrelated files and edited entry points"
printf '/* custom rule */\n' >> "$profile/chrome/userChrome.css"
check uninstall "$profile"
check test ! -e "$profile/chrome/textfox"
check test ! -e "$profile/chrome/userContent.css"
check grep -Fqx '/* custom rule */' "$profile/chrome/userChrome.css"
check grep -qx custom "$profile/chrome/custom.css"
check grep -qx 'other mod' "$profile/chrome/sine-mods/other/theme.json"
check grep -qx 'my preferences' "$profile/user.js"
check uninstall "$profile"
printf 'PASS %s\n' "$scenario"

scenario="Abort installation if a current entry point belongs to the user"
profile="$root/personal"
mkdir -p "$profile/chrome"
printf '/* existing stylesheet */\n' > "$profile/chrome/userChrome.css"
if install "$profile" 2>/dev/null; then
  printf 'Unexpected install success on a conflict\n' >&2
  exit 1
fi
check grep -Fqx '/* existing stylesheet */' "$profile/chrome/userChrome.css"
check test ! -e "$profile/chrome/textfox"
check test ! -e "$profile/chrome/userContent.css"
printf 'PASS %s\n' "$scenario"

scenario="Uninstall preserves a legacy profile without ownership records"
profile="$root/legacy"
mkdir -p "$profile/chrome/sine-mods"
cp "$repo/chrome/userChrome.css" "$profile/chrome/userChrome.css"
printf 'other\n' > "$profile/chrome/sine-mods/mods.json"
check uninstall "$profile"
check cmp -s "$repo/chrome/userChrome.css" "$profile/chrome/userChrome.css"
check grep -qx other "$profile/chrome/sine-mods/mods.json"
printf 'PASS %s\n' "$scenario"

scenario="Uninstall removes untouched preferences installed by the script"
profile="$root/owned-prefs"
mkdir -p "$profile"
check install "$profile" y
check cmp -s "$repo/user.js" "$profile/user.js"
check uninstall "$profile"
check test ! -e "$profile/user.js"
printf 'PASS %s\n' "$scenario"

scenario="Uninstall preserves installed preferences that were edited later"
profile="$root/edited-prefs"
mkdir -p "$profile"
check install "$profile" y
printf '\n// other preference\n' >> "$profile/user.js"
check install "$profile"
check uninstall "$profile"
check grep -Fqx '// other preference' "$profile/user.js"
printf 'PASS %s\n' "$scenario"

scenario="A failed package move restores the previous installation"
profile="$root/rollback"
mkdir -p "$profile"
check install "$profile"
printf 'previous package\n' > "$profile/chrome/textfox/old-marker"

# Fail the first move into the active package path, after the old package moved out.
mock_bin="$root/mock-bin"
mkdir "$mock_bin"
cat > "$mock_bin/mv" <<'EOF'
#!/usr/bin/env bash
source=${@: -2:1}
target=${!#}
if [[ "$target" == */ ]]; then target+="${source##*/}"; fi
if [[ -n "${CONFLICT_TARGET:-}" && "$target" == "$CONFLICT_TARGET" ]]; then
  mkdir -- "$target"
  printf 'other writer\n' > "$target/keep"
fi
if [[ -n "${INTERRUPT_FROM:-}" && "$source" == "$INTERRUPT_FROM" && ! -e "$FAIL_MARKER" ]]; then
  "$REAL_MV" "$@" || exit $?
  printf 'interrupted\n' > "$FAIL_MARKER"
  kill -TERM "$PPID"
  exit 0
fi
if [[ "$target" == "${FAIL_TARGET:-}" && ! -e "$FAIL_MARKER" ]]; then
  printf 'failed\n' > "$FAIL_MARKER"
  exit 1
fi
exec "$REAL_MV" "$@"
EOF
chmod +x "$mock_bin/mv"
if REAL_MV="$(command -v mv)" FAIL_TARGET="$profile/chrome/textfox" FAIL_MARKER="$root/move-failed" \
    PATH="$mock_bin:$PATH" install "$profile"; then
  printf 'Unexpected success despite failed publish\n' >&2
  exit 1
fi
check test -f "$root/move-failed"
check grep -qx 'previous package' "$profile/chrome/textfox/old-marker"
check grep -Fqx '@import url("textfox/userChrome.css");' "$profile/chrome/userChrome.css"
check test ! -e "$profile/chrome/.textfox-profile-lock"
printf 'PASS %s\n' "$scenario"

scenario="An interruption after moving a package out restores the old package"
profile="$root/interrupted"
mkdir -p "$profile"
check install "$profile"
printf 'previous package\n' > "$profile/chrome/textfox/old-marker"
if REAL_MV="$(command -v mv)" INTERRUPT_FROM="$profile/chrome/textfox" FAIL_MARKER="$root/interrupted-marker" \
    PATH="$mock_bin:$PATH" install "$profile"; then
  printf 'Unexpected success despite signal\n' >&2
  exit 1
fi
check test -f "$root/interrupted-marker"
check grep -qx 'previous package' "$profile/chrome/textfox/old-marker"
check test ! -e "$profile/chrome/.textfox-profile-lock"
printf 'PASS %s\n' "$scenario"

scenario="An entry point preset without a managed package stays unowned"
profile="$root/preset"
mkdir -p "$profile/chrome"
printf '/* textfox profile installer */\n@import url("textfox/userChrome.css");\n' > "$profile/chrome/userChrome.css"
if install "$profile" 2>/dev/null; then
  printf 'Unexpected install success on a preexisting entry point\n' >&2
  exit 1
fi
check uninstall "$profile"
check test -f "$profile/chrome/userChrome.css"
check test ! -e "$profile/chrome/textfox"
printf 'PASS %s\n' "$scenario"

scenario="A destination created before mv receives no files"
profile="$root/overlap"
mkdir -p "$profile"
if REAL_MV="$(command -v mv)" CONFLICT_TARGET="$profile/chrome/textfox" \
    PATH="$mock_bin:$PATH" install "$profile"; then
  printf 'Unexpected success on a concurrent destination conflict\n' >&2
  exit 1
fi
check grep -qx 'other writer' "$profile/chrome/textfox/keep"
check test ! -e "$profile/chrome/textfox/textfox"
check test ! -e "$profile/chrome/userChrome.css"
printf 'PASS %s\n' "$scenario"
