#!/usr/bin/env sh
set -e

if [ "$#" -eq 0 ]; then
  exec forgeworks --help
fi

exec "$@"
