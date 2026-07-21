#!/usr/bin/env bash

set -euo pipefail

backend_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/../backend" && pwd)"
cd "$backend_dir"

needs_install=false

if [[ ! -x .venv/bin/python ]]; then
  if ! command -v python3.11 >/dev/null 2>&1; then
    echo "Python 3.11 is required to create backend/.venv." >&2
    exit 1
  fi

  echo "Creating backend/.venv..."
  python3.11 -m venv .venv
  needs_install=true
elif ! .venv/bin/python -c "import server" >/dev/null 2>&1; then
  needs_install=true
fi

if [[ "$needs_install" == true ]]; then
  echo "Installing backend dependencies..."
  .venv/bin/python -m pip install -r requirements-dev.txt
fi

exec .venv/bin/python -m uvicorn server:app --reload
