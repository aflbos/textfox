#!/usr/bin/env bash
set -euo pipefail

source_dir=$1
output_dir=$2
config_css=$3
extra_chrome=$4
extra_content=$5

mkdir -p "$output_dir"
cp -r "$source_dir/icons" "$output_dir/icons"

bundle() {
    local name=$1 extra_css=$2
    local import_pattern='^[[:space:]]*@import[[:space:]]+url\("([^"]+)"\);[[:space:]]*$'
    local line import_path digest
    local body="$output_dir/$name.body"

    {
        # The entry points define the order of the cascade in every installer.
        while IFS= read -r line || [[ -n $line ]]; do
            if [[ $line =~ $import_pattern ]]; then
                import_path=${BASH_REMATCH[1]}
                case "$import_path" in
                    config.css) cat "$config_css" ;;
                    icons.css) sed "s|url(\"\./icons/|url(\"file://$output_dir/icons/|g" "$source_dir/icons.css" ;;
                    *) cat "$source_dir/$import_path" ;;
                esac
                printf '\n'
            elif [[ $line =~ ^[[:space:]]*@import([[:space:]]|$) ]]; then
                printf 'Unsupported CSS import in %s: %s\n' "$name" "$line" >&2
                return 1
            else
                printf '%s\n' "$line"
            fi
        done < "$source_dir/$name"
        printf '\n'
        cat "$extra_css"
    } > "$body"

    digest=$(sha256sum < "$body")
    {
        printf '/* Textfox Nix SHA-256: %s */\n' "${digest%% *}"
        cat "$body"
    } > "$output_dir/$name"
    rm "$body"
}

bundle userChrome.css "$extra_chrome"
bundle userContent.css "$extra_content"
