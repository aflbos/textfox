#!/bin/sh
set -e
repo=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec bash "$repo/tools/profile-installer.sh" install "$@"
