#!/usr/bin/env bash
set -euo pipefail

PROXY_URL="http://127.0.0.1:20122"

export http_proxy="$PROXY_URL"
export https_proxy="$PROXY_URL"
export HTTP_PROXY="$PROXY_URL"
export HTTPS_PROXY="$PROXY_URL"

# Forward all args to git push.
# Example: ./git_push_with_proxy.sh origin master
exec git push "$@"
