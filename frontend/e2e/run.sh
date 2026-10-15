#!/bin/sh
# Runs the e2e suite. Reads the admin password from the repo's .env into SAQ_ADMIN_PASSWORD (never printed);
# without it the admin specs are skipped. Extra arguments go to `playwright test`.
set -eu

cd "$(dirname "$0")/.."

if [ -z "${SAQ_ADMIN_PASSWORD:-}" ] && [ -f ../.env ]; then
  value=$(sed -n 's/^INITIAL_ADMIN_PASSWORD=//p' ../.env | head -n 1)
  # Drop the quotes some .env files put around values.
  value=${value#\"}
  value=${value%\"}
  value=${value#\'}
  value=${value%\'}
  if [ -n "$value" ]; then
    SAQ_ADMIN_PASSWORD=$value
    export SAQ_ADMIN_PASSWORD
  fi
fi

exec pnpm exec playwright test "$@"
