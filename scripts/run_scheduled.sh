#!/usr/bin/env bash
# Run sync, ingest, and process in sequence. Intended for cron or launchd.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

INTERVAL_S="${TVP_INTERVAL_S:-1800}"
PYTHON="${TVP_PYTHON:-python3}"

run_once() {
  echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] tackletek-video-pipeline run-all"
  "$PYTHON" -m pipeline.cli run-all
}

if [[ "${TVP_LOOP:-0}" == "1" ]]; then
  while true; do
    run_once || true
    sleep "$INTERVAL_S"
  done
else
  run_once
fi
