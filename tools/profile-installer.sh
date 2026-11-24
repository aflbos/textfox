#!/usr/bin/env bash
set -euo pipefail

repo=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
operation=$1
shift

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

path_exists() {
  [[ -e "$1" || -L "$1" ]]
}

if [[ $# -gt 1 ]]; then
  fail "Provide one browser profile directory."
fi
if [[ $# -eq 1 ]]; then
  selected=$1
else
  read -r -p 'Path to browser profile: ' selected || exit 1
fi
case "$selected" in
  "~") selected=$HOME ;;
  "~/"*) selected=$HOME/${selected:2} ;;
esac
[[ -n "$selected" ]] || fail "The profile path is empty."
profile=$(CDPATH= cd -- "$selected" && pwd -P) || fail "Profile directory not found: $selected"
chrome="$profile/chrome"
package="$chrome/textfox"
marker="textfox profile installer"

if ! path_exists "$chrome"; then
  if [[ "$operation" == uninstall ]]; then
    printf 'No managed textfox package in %s\n' "$profile"
    exit 0
  fi
  mkdir -- "$chrome"
fi
[[ -d "$chrome" && ! -L "$chrome" ]] || fail "Expected a regular chrome directory: $chrome"

lock="$chrome/.textfox-profile-lock"
mkdir -- "$lock" 2>/dev/null || fail "Cannot reserve the profile. Check for another installer or a stale lock at $lock"

archive=""
saved=()
published=()
saved_count=0
published_count=0

active_path() {
  case "$1" in
    user.js) printf '%s\n' "$profile/user.js" ;;
    *) printf '%s\n' "$chrome/$1" ;;
  esac
}

move_without_replace() {
  local source=$1 target=$2
  if path_exists "$target"; then
    printf 'Destination already exists: %s\n' "$target" >&2
    return 1
  fi
  # All moves keep the basename. Passing the parent prevents mv from
  # nesting the source inside a directory that appeared at the target.
  mv -n -- "$source" "${target%/*}/" || return 1
  if path_exists "$source"; then
    printf 'Could not move %s to %s\n' "$source" "$target" >&2
    return 1
  fi
}

finish() {
  local result=$? i name recovery_failed=0
  if [[ -n "$archive" ]]; then
    if (( result != 0 )); then
      for ((i = published_count - 1; i >= 0; i--)); do
        name=${published[i]}
        if ! path_exists "$pending/$name"; then
          move_without_replace "$(active_path "$name")" "$pending/$name" || recovery_failed=1
        fi
      done
      for ((i = saved_count - 1; i >= 0; i--)); do
        name=${saved[i]}
        if path_exists "$previous/$name"; then
          move_without_replace "$previous/$name" "$(active_path "$name")" || recovery_failed=1
        fi
      done
      if (( recovery_failed )); then
        printf 'Automatic recovery was incomplete. Review files in %s\n' "$archive" >&2
      fi
    fi
    rmdir -- "$pending" "$previous" "$archive" 2>/dev/null || true
    if [[ -d "$archive" ]]; then printf 'Files saved in %s\n' "$archive"; fi
  fi
  rmdir -- "$lock" 2>/dev/null || true
  return "$result"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

write_entry_point() {
  printf '/* %s */\n@import url("textfox/%s");\n' "$marker" "$1"
}

is_owned_entry_point() {
  local path="$chrome/$1"
  [[ -f "$path" && ! -L "$path" ]] && cmp -s "$path" <(write_entry_point "$1")
}

managed=false
if path_exists "$package"; then
  if [[ -d "$package" && ! -L "$package" && -f "$package/.textfox-managed" && ! -L "$package/.textfox-managed" ]] &&
      grep -Fqx "$marker" "$package/.textfox-managed"; then
    managed=true
  else
    fail "The package path is already in use: $package"
  fi
fi

if [[ "$operation" == uninstall ]]; then
  if ! $managed; then
    printf 'No managed textfox package in %s. See the README for older installations.\n' "$profile"
    exit 0
  fi
else
  for name in userChrome.css userContent.css; do
    if path_exists "$chrome/$name"; then
      if ! $managed; then
        fail "Existing stylesheet kept: $chrome/$name. See the README before migrating."
      fi
      if ! is_owned_entry_point "$name"; then
        printf 'Keeping the edited stylesheet: %s\n' "$chrome/$name"
      fi
    fi
  done
fi

backups="$chrome/textfox-backups"
if path_exists "$backups" && [[ ! -d "$backups" || -L "$backups" ]]; then
  fail "Expected a regular backup directory: $backups"
fi
mkdir -p -- "$backups"
archive=$(mktemp -d "$backups/$(date +%Y%m%d-%H%M%S).XXXXXXXX")
pending="$archive/pending"
previous="$archive/previous"
mkdir -- "$pending" "$previous"

save_active() {
  local name=$1
  # Record the move before invoking mv, as a signal can arrive as it exits.
  saved[saved_count]=$name
  ((saved_count += 1))
  move_without_replace "$(active_path "$name")" "$previous/$name"
}

publish() {
  local name=$1
  published[published_count]=$name
  ((published_count += 1))
  move_without_replace "$pending/$name" "$(active_path "$name")"
}

if [[ "$operation" == uninstall ]]; then
  for name in userChrome.css userContent.css; do
    if is_owned_entry_point "$name"; then
      save_active "$name"
    elif path_exists "$chrome/$name"; then
      printf 'Keeping the edited stylesheet: %s\n' "$chrome/$name"
    fi
  done
  if [[ -f "$profile/user.js" && ! -L "$profile/user.js" &&
        -f "$package/.textfox-user.js" && ! -L "$package/.textfox-user.js" ]] &&
      cmp -s "$profile/user.js" "$package/.textfox-user.js"; then
    save_active user.js
  fi
  save_active textfox
  printf 'textfox removed from %s\n' "$profile"
  exit 0
fi

cp -R -- "$repo/chrome" "$pending/textfox"
printf '%s\n' "$marker" > "$pending/textfox/.textfox-managed"
if $managed && path_exists "$package/config.css"; then
  cp -P -- "$package/config.css" "$pending/textfox/config.css"
fi

for name in userChrome.css userContent.css; do
  [[ -f "$pending/textfox/$name" ]] || fail "Missing stylesheet: $name"
  if ! path_exists "$chrome/$name"; then
    write_entry_point "$name" > "$pending/$name"
  fi
done

if [[ -f "$package/.textfox-user.js" && ! -L "$package/.textfox-user.js" ]]; then
  cp -- "$package/.textfox-user.js" "$pending/textfox/.textfox-user.js"
fi
if ! path_exists "$profile/user.js"; then
  read -r -p 'Install the textfox user.js file? (y/N): ' answer || answer=n
  if [[ "$answer" == [Yy]* ]]; then
    cp -- "$repo/user.js" "$pending/user.js"
    cp -- "$pending/user.js" "$pending/textfox/.textfox-user.js"
  fi
fi

if $managed; then save_active textfox; fi
publish textfox
for name in userChrome.css userContent.css user.js; do
  if [[ -f "$pending/$name" ]]; then publish "$name"; fi
done
printf 'textfox installed in %s\n' "$profile"
