# TackleTek Video Pipeline

Orchestrates Google Drive video sync, first-frame ingestion previews, and (Phase 2+) the TackleTek MATLAB analysis pipeline.

**Drive source (test):** [Blundell's folder](https://drive.google.com/drive/folders/1-1z2Gjy-BdYGtrVdzXnYm2wnGH45myoD)

## Phases

| Phase | Commands | Outcome |
|-------|----------|---------|
| 1 — Ingestion | `sync`, `ingest`, `status` | Videos downloaded; `_frame0.png` preview per file; audit log |
| 2 — Analysis | `process` | Runs `run_full_analysis_pipeline` in TackleTek (FlatMode) |
| 3 — Automation | `scripts/run_scheduled.sh` or launchd plist | Periodic sync + ingest + process |

Phase 1 is complete when you can sync, ingest, open preview PNGs, and read `data/events.jsonl` — no MATLAB required.

## Setup

```bash
cd tackletek-video-pipeline
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip first (required on macOS system Python / old conda base)
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

If editable install still fails on an old pip, use:

```bash
pip install -r requirements-dev.txt
pip install .
```

Then run via `python -m pipeline.cli` or the `tvp` command.

Edit [`config.yaml`](config.yaml) for your machine:

- `paths.*` — local data directories (defaults are relative to repo root)
- `tackletek.matlab_dir` / `tackletek.onevone_root` — paths to your TackleTek clone (Phase 2+)

## Phase 1 — Ingestion MVP

```bash
# Download Drive folder to data/incoming/
python -m pipeline.cli sync

# Register + extract first frame for each stable new video
python -m pipeline.cli ingest

# Human-readable summary
python -m pipeline.cli status

# Recent audit trail
python -m pipeline.cli tail-log -n 20
```

Dry-run sync (prints gdown command):

```bash
python -m pipeline.cli sync --dry-run
```

**Manual test checklist**

1. `sync` — files appear in `data/incoming/`
2. `ingest` — one PNG per video in `data/previews/`
3. Open PNGs — confirm correct footage
4. `ingest` again — idempotent (no duplicate work)
5. `status` and `tail-log` — readable dialogue

## Phase 2 — MATLAB analysis

Requires a local TackleTek clone with `FlatMode` support in [`run_full_analysis_pipeline.m`](../TackleTek/1v1/matlab/run_full_analysis_pipeline.m).

```bash
python -m pipeline.cli process
python -m pipeline.cli process --limit 1   # one video at a time
```

Videos are copied to `OutsideExamples/<dataset_name>/` before MATLAB runs. Outputs land in `OutsideExamples/<dataset_name>/<dataset_name>_output/<clip_stem>/`.

## Phase 3 — Scheduled runs

```bash
# Foreground loop (every 30 minutes)
./scripts/run_scheduled.sh

# Or install launchd agent (edit paths in plist first)
cp scripts/com.tackletek.video-pipeline.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.tackletek.video-pipeline.plist
```

## Project layout

```text
config.yaml
src/pipeline/
  sync.py       # gdown folder sync
  scanner.py    # discover + stability
  ingest.py     # frame 0 PNG
  registry.py   # SQLite job state
  events.py     # JSONL audit log
  process.py    # MATLAB batch (Phase 2)
  cli.py
data/           # gitignored
tests/
```

## Tests

```bash
python tests/make_fixture_video.py
pytest
```

## Relationship to TackleTek

| Concern | Repo |
|---------|------|
| Sync, registry, previews, scheduling | `tackletek-video-pipeline` (this repo) |
| Pose, collision, competency | TackleTek `1v1/matlab/` |

Do not commit synced videos, registry DB, or preview PNGs from real sessions (`data/` is gitignored).
