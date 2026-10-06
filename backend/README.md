# SiamCareNode backend — Phase 1

A locally runnable Python 3.12 foundation for hospital discovery. No AWS account
or external services are needed. The root README describes the longer-term roadmap.

## Setup and execution

Install uv, then run from the repository root:

```bash
cd backend
uv python install 3.12
uv sync --locked
uv run siamcare hospitals list
uv run siamcare hospitals get H01
uv run siamcare hospitals search --specialty neurology
uv run siamcare hospitals search --specialty ' Neurology ' --min-free-beds 1
```

uv creates and manages `.venv`; dependencies are declared in `pyproject.toml`
and pinned in `uv.lock`. The project uses Python 3.12 (`.python-version`).

To use your own JSON array, put the global `--dataset` option before `hospitals`:

```bash
uv run siamcare --dataset /absolute/path/hospitals.json hospitals list
```

Relative supplied paths resolve against your current working directory. The default
is `backend/data/mock/hospitals.json`, resolved relative to the installed source
module, independently of the working directory. Built wheels include the same
fixture as package data. From another directory, use:

```bash
uv run --project /absolute/path/ntt-data-hackathon-SiamCareNode/backend siamcare hospitals list
```

Successful commands print UTF-8 JSON on stdout and a snapshot reminder on stderr.
Exit codes: `0` success (including empty `[]` searches), `1` unknown hospital ID,
`2` invalid arguments or data. IDs are case-sensitive. Results sort by hospital ID.

## Layers and behavior

- `models/hospital.py`: immutable Pydantic records with nonblank IDs/names,
  specialties, strict nonnegative integer bed counts, and timezone-aware timestamps.
  Free beds cannot exceed total beds. Unknown fields are rejected.
- `repositories/hospital_repository.py`: one small `Protocol` with list/get methods.
  A future DynamoDB adapter can implement this contract.
- `repositories/json_hospital_repository.py`: loads a supplied UTF-8 JSON path once,
  validates every record, and rejects duplicates and malformed data with path,
  record index, and validation details. It never silently drops invalid records.
- `services/hospital_service.py`: constructor-injected repository, deterministic
  discovery and capacity filtering. No CLI, AWS, or filesystem dependencies.
  Missing IDs raise `HospitalNotFoundError`; empty searches return an empty tuple.
- `cli.py`: argparse, dependency construction, service calls, JSON output and exit codes.

Specialties are trimmed and case-folded in both records and search input, then
matched exactly. There is no substring, synonym, diagnosis, or clinical suitability
inference. Blank or unmatched specialties return no results. Omitting the minimum
includes hospitals with zero free beds; a minimum of zero does too. The threshold
is inclusive and must be a nonnegative integer. Bed counts are hospital-wide,
not specialty-specific.

The dataset is a top-level JSON array; each record follows this schema:

```json
{
  "hospital_id": "H01",
  "name_en": "Synthetic Lotus Dawn Hospital",
  "name_th": "โรงพยาบาลบัวอรุณจำลอง",
  "specialties": ["neurology", "cardiology"],
  "total_beds": 120,
  "free_beds": 4,
  "capacity_updated_at": "2026-10-01T09:00:00+07:00"
}
```

## Synthetic data limitation

All eight hospitals, capabilities, and capacity snapshots are fictional test data.
Their names explicitly label them synthetic. These are fixed snapshots, not live
availability; a bed count does not guarantee admission. No freshness/trust labels,
ranking scores, reservations, referral workflows, or clinical recommendations are
implemented. There are no real hospital agreements or patient records.

## Verification

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run siamcare hospitals search --specialty neurology --min-free-beds 1
uv build
```

Tests cover repository validation, supplied paths, service behavior through an
in-memory repository, and CLI output/errors including execution from another directory.
The filtered sample search returns `H01` and `H06` in that order.
