#!/usr/bin/env sh
set -eu

if [ -z "${JUPYTER_TOKEN:-}" ]; then
  echo "JUPYTER_TOKEN is not set; Jupyter will generate a token and print it in the container logs." >&2
fi

mkdir -p /workspace/notebooks /workspace/data /workspace/scripts
exec "$@"

