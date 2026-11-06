#!/bin/sh
# Applies migrations and, on the local Compose network only, picks up the deployed contract before starting the API.
set -e

alembic -c alembic.ini upgrade head

if [ "$USE_HARDHAT_DEV_RELAYER" = "true" ]; then
  eval "$(python /app/scripts/docker_chain_env.py)"
fi

exec "$@"
