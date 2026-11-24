#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
temp_dir=$(cd "${TMPDIR:-/tmp}" && pwd -P)
fixture=$(mktemp -d "$temp_dir/textfox-nix-test.XXXXXX")
[[ $(cd "$fixture" && pwd -P) == "$temp_dir"/textfox-nix-test.* ]]
trap 'rm -rf -- "$fixture"' EXIT

printf ':root { --tf-font-size: 21px; }\n' > "$fixture/config.css"
printf '/* extra chrome */\n' > "$fixture/extra-chrome.css"
printf '/* extra content */\n' > "$fixture/extra-content.css"
bash nix/pkgs/bundle-stylesheets.sh chrome "$fixture/out" "$fixture/config.css" \
    "$fixture/extra-chrome.css" "$fixture/extra-content.css"

chrome="$fixture/out/userChrome.css"
content="$fixture/out/userContent.css"

for stylesheet in "$chrome" "$content"; do
    if grep -Eq '^[[:space:]]*@import' "$stylesheet"; then
        printf 'Unexpected CSS import in %s\n' "$stylesheet" >&2
        exit 1
    fi
    digest=$(tail -n +2 "$stylesheet" | sha256sum)
    IFS= read -r header < "$stylesheet"
    [[ $header == "/* Textfox Nix SHA-256: ${digest%% *} */" ]]
done

line_number() {
    local result
    result=$(grep -nm1 -F -- "$1" "$2") || return 1
    printf '%s\n' "${result%%:*}"
}

waterfox=$(line_number 'ajustes para elementos que' "$chrome")
animations=$(line_number 'animações e transições da interface' "$chrome")
defaults=$(line_number '  --tf-font-size: 14px;' "$chrome")
config=$(line_number '--tf-font-size: 21px;' "$chrome")
extra=$(line_number '/* extra chrome */' "$chrome")
(( waterfox < animations && animations < defaults && defaults < config && config < extra ))

about=$(line_number '@-moz-document url-prefix(about:)' "$content")
newtab=$(line_number '@-moz-document url("about:home")' "$content")
config=$(line_number '--tf-font-size: 21px;' "$content")
extra=$(line_number '/* extra content */' "$content")
(( about < newtab && newtab < config && config < extra ))

test -f "$fixture/out/icons/book.svg"
grep -Fq "url(\"file://$fixture/out/icons/book.svg\")" "$chrome"
printf 'Nix CSS bundle checks passed.\n'
