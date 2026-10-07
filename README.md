# SiamCareNode

A Python backend for hospital discovery and a simulated referral workflow, built
for the NTT DATA Digital Innovation Challenge 2026.

## Current backend

- Discover eight fictional hospitals by ID, specialty, and recorded free beds.
- Create referrals, send hospital requests, accept or decline requests, submit for
  physician review, and approve or reject referrals.
- Persist referrals, requests, and ordered event history in SQLite through `.env`
  configuration. Hospital seed data is loaded from JSON.
- Run through the `siamcare` CLI. There is no HTTP API or frontend yet.

All examples use synthetic data. Hospital responses and actor roles are simulated;
no hospital is contacted, no bed is reserved, and no transport is dispatched.
Actor flags are not authentication. Use synthetic patient references only.

## Team setup

Prerequisites: Git and [uv](https://docs.astral.sh/uv/getting-started/installation/).
Python 3.12 is installed by the commands below. DataGrip is optional; SQLite does
not require Docker or a database server. Commands use Bash or zsh.

After this work is pushed, teammates can clone the `bambi` branch:

```bash
git clone --branch bambi https://github.com/AlbertZawSam/ntt-data-hackathon-SiamCareNode.git
cd ntt-data-hackathon-SiamCareNode/backend
uv python install 3.12
uv sync --locked
cp -n .env.example .env
uv run siamcare --help
```

For an existing checkout, switch to `bambi` and pull its latest changes before
running the setup commands from `backend/`. Keep your own uncommitted work safe
before switching branches. Run all commands below from `backend/`.
`cp -n` preserves an existing `.env`; on a new checkout it creates one from the
shared example. Each teammate has their own local database.

## Automated verification

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv build
```

Expected: 117 tests pass, lint and formatting checks pass, and a wheel plus source
archive are created in `dist/`. Tests use isolated temporary databases and do not
modify the database configured in `.env`.

| Tests | What they verify |
|---|---|
| `test_hospital_repository.py`, `test_hospital_service.py`, `test_cli.py` | JSON validation, hospital discovery, filtering, and CLI errors |
| `test_config.py` | `.env` paths, environment overrides, and explicit database selection |
| `test_referral_service.py` | Approval, decline/retry, rejection, roles, hospital scope, reasons, and invalid transitions |
| `test_referral_repository.py` | Persistence, repeat initialization, concurrent writes, constraints, and rollback |
| `test_referral_cli.py` | Workflow across separate processes, argument validation, and database errors |

## SQLite configuration and DataGrip

Set the database file in `backend/.env`:

```dotenv
SIAMCARE_DATABASE_PATH=./data/siamcare.sqlite3
```

To use an existing SQLite database, replace this value with its absolute file path.
A DataGrip project directory such as `~/DataGripProjects/default` is an IDE settings
folder, not a database file. Use the filename shown in the data source's **File**
setting. Both the application and DataGrip must use the same file.

Initialize the application's tables from `backend/`:

```bash
uv run siamcare referrals list
```

This creates missing tables without deleting existing records. In DataGrip, open
an existing SQLite data source's settings (or add one), set **File** to the absolute
path of `backend/data/siamcare.sqlite3` in your checkout, test the connection, and
apply. If you configured a different file in `.env`, select that file instead.
The JDBC URL has the form `jdbc:sqlite:/absolute/path/to/database.sqlite3`.
Refresh the database explorer and expand `main` to see `referrals`,
`hospital_requests`, and `referral_events`. SQLite needs no host, port, credentials,
or running database server. Hospital seeds currently remain in JSON.

Configuration precedence is `--database PATH`, then the exported
`SIAMCARE_DATABASE_PATH` environment variable, then `backend/.env`. Relative paths
in configuration resolve from `backend/` in a source checkout. Installed packages
read `.env` and resolve configured relative paths from the working directory.
If no database path is configured, the fallback is `~/.siamcare/referrals.sqlite3`.
Existing database files are not moved automatically. `.env` and database files
are ignored by Git; `.env.example` documents the shared setup.

## Manual test: hospital discovery

```bash
uv run siamcare hospitals list
uv run siamcare hospitals get H01
uv run siamcare hospitals search --specialty neurology
uv run siamcare hospitals search --specialty ' Neurology ' --min-free-beds 1
uv run siamcare --dataset data/mock/hospitals.json hospitals get H01
```

Specialties are trimmed and case-folded, then matched exactly: no synonyms,
substring matching, diagnosis inference, or clinical suitability assessment.
The search with `--min-free-beds 1` returns `H01` and `H06`. Without the bed filter, `H02` is also
returned despite having zero free beds. A minimum of zero includes zero-bed
hospitals. Blank or unmatched specialty searches return `[]`. IDs are case-sensitive;
hospital results sort by ID. Bed counts are hospital-wide, not specialty-specific.

## Manual test: approval workflow

The following Bash/zsh commands use the persistent database configured above.
Records remain available across commands and can be inspected in DataGrip.

```bash
referral_id=$(uv run siamcare referrals create \
  --patient SYN-001 --specialty neurology --urgency routine \
  --actor demo-clinician --role clinician \
  | uv run python -c 'import json,sys; print(json.load(sys.stdin)["referral_id"])')
echo "$referral_id"

uv run siamcare referrals list
uv run siamcare referrals get "$referral_id"
uv run siamcare referrals hospitals "$referral_id"

request_id=$(uv run siamcare requests send "$referral_id" --hospital H01 \
  --actor demo-clinician --role clinician \
  | uv run python -c 'import json,sys; print(json.load(sys.stdin)["request_id"])')
echo "$request_id"

uv run siamcare requests list --referral "$referral_id"
uv run siamcare requests list --hospital H01
uv run siamcare requests accept "$request_id" \
  --actor demo-h01-staff --role hospital_staff --actor-hospital H01
uv run siamcare referrals submit-review "$referral_id" \
  --actor demo-clinician --role clinician
uv run siamcare referrals approve "$referral_id" \
  --actor demo-physician --role approver
uv run siamcare referrals get "$referral_id"
uv run siamcare referrals history "$referral_id"
```

The final status is `approved`, with five events: `created`, `request_sent`,
`request_accepted`, `review_submitted`, `approved`. IDs are generated UUIDs and
returned in JSON. The shell variables above extract those IDs; alternatively copy
`referral_id` and `request_id` from command output into subsequent commands.

## Manual test: decline, retry, and rejection

Run this in the same terminal. It creates a second referral:

```bash
referral_id=$(uv run siamcare referrals create \
  --patient SYN-002 --specialty neurology --urgency time-critical \
  --actor demo-clinician --role clinician \
  | uv run python -c 'import json,sys; print(json.load(sys.stdin)["referral_id"])')
request_id=$(uv run siamcare requests send "$referral_id" --hospital H01 \
  --actor demo-clinician --role clinician \
  | uv run python -c 'import json,sys; print(json.load(sys.stdin)["request_id"])')
uv run siamcare requests decline "$request_id" --reason 'Synthetic ward unavailable' \
  --actor demo-h01-staff --role hospital_staff --actor-hospital H01

request_id=$(uv run siamcare requests send "$referral_id" --hospital H06 \
  --actor demo-clinician --role clinician \
  | uv run python -c 'import json,sys; print(json.load(sys.stdin)["request_id"])')
uv run siamcare requests accept "$request_id" \
  --actor demo-h06-staff --role hospital_staff --actor-hospital H06
uv run siamcare referrals submit-review "$referral_id" \
  --actor demo-clinician --role clinician
uv run siamcare referrals reject "$referral_id" --reason 'Synthetic review rejected' \
  --actor demo-physician --role approver
uv run siamcare requests list --referral "$referral_id"
uv run siamcare referrals history "$referral_id"
```

The first request stays `declined`; the second becomes `cancelled`. The referral is
terminally `rejected`. The hospital's original response reason/time is retained;
the physician's rejection reason is stored in the final event.

## Manual test: expected failures

After the rejection workflow above, these commands should fail without changing
its records. Run them individually; `echo $?` prints the preceding exit code.

```bash
uv run siamcare referrals get DOES-NOT-EXIST
echo $?  # 1: referral not found

uv run siamcare referrals approve "$referral_id" \
  --actor demo-physician --role approver
echo $?  # 2: a rejected referral cannot be approved

uv run siamcare requests accept "$request_id" \
  --actor demo-h01-staff --role hospital_staff --actor-hospital H01
echo $?  # 2: this request belongs to H06, not H01

uv run siamcare referrals history "$referral_id"
```

The rejected referral still has seven events. Automated tests additionally cover
self-review, missing reasons, wrong roles, zero-bed hospitals, duplicate responses,
and concurrent requests.

## Inspect results in DataGrip

Refresh the SQLite data source after running the workflows. Open a query console
for that connection and run:

```sql
SELECT referral_id, patient_reference, status, version
FROM referrals ORDER BY created_at;

SELECT request_id, referral_id, hospital_id, status, response_reason
FROM hospital_requests ORDER BY created_at;

SELECT referral_id, version, action, actor_id, timestamp
FROM referral_events ORDER BY referral_id, version;

PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

On a fresh database, the two workflows produce two referrals (`approved` and
`rejected`), three requests (`accepted`, `declined`, and `cancelled`), and twelve
events. Repeating the walkthrough creates additional records with new UUIDs.
Integrity should return `ok`; the foreign-key check should return no rows.

Discover arguments with `uv run siamcare referrals --help`,
`uv run siamcare requests --help`, or a command's `--help`. Successful commands
emit JSON on stdout and simulation/snapshot reminders on stderr. Exit codes:
`0` success (including empty lists), `1` unknown ID, `2` invalid input, forbidden
actor, invalid transition, concurrency conflict, or persistence failure.

## State model and rules

Referral status is separate from each hospital request's status:

| Action | Referral before → after | Request change | Demo role |
|---|---|---|---|
| Create | none → `open` | none | clinician |
| Send | `open` → `awaiting_hospital` | new `pending` request | clinician |
| Accept | `awaiting_hospital` → `hospital_accepted` | `pending` → `accepted` | hospital_staff |
| Decline | `awaiting_hospital` → `open` | `pending` → `declined` | hospital_staff |
| Submit review | `hospital_accepted` → `awaiting_review` | stays `accepted` | clinician |
| Approve | `awaiting_review` → `approved` | stays `accepted` | approver |
| Reject | `awaiting_review` → `rejected` | `accepted` → `cancelled` | approver |

- Urgency must be explicitly `routine` or `time-critical`; it is stored without
  inference, ranking, deadlines, or different execution behavior in this phase.
- Only one pending or accepted request is permitted per referral. After a decline,
  the selection clears and another request can be sent. Previous requests remain.
- Sending verifies that the referral and hospital exist, the specialty matches,
  and the recorded free-bed count is at least one, using the Phase 1 service.
- Only a pending request can receive a first response. The responder must have
  `hospital_staff` role and the matching `--actor-hospital` scope.
- Only an accepted selected request can be submitted for review. Any simulated
  clinician can send or submit; the creator remains the referring clinician.
- Approve/reject requires `awaiting_review`, an `approver` role, and an actor ID
  different from the referring clinician. Both decisions are terminal here.
- Decline and rejection require nonblank reasons. Acceptance and approval may
  include optional reasons. There is no independent cancellation command.
- Repeated/conflicting transitions fail without new events or partial state.
  Each create command intentionally creates a new referral; there is no remote
  request idempotency key or retry system in this local CLI.

## Data, paths, and reset

Global options go **before** `hospitals`, `referrals`, or `requests`:

- `--dataset PATH`: default `backend/data/mock/hospitals.json` in a source checkout,
  located relative to the package, independently of the working directory. Wheels
  bundle the same fixture. A supplied relative path uses the current directory.
- `--database PATH`: overrides the environment and `.env` database configuration.
  Parent directories are created. A path supplied through this CLI option resolves
  from the current directory; `~` is expanded.
- Hospital-only commands do not initialize SQLite. Referral/request commands
  initialize missing tables and indexes without clearing existing data.

The hospital dataset is a UTF-8 JSON array. Example record:

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

Nonblank fields, timezone-aware timestamps, strict nonnegative integer bed counts,
and `free_beds <= total_beds` are validated. Duplicate IDs, unknown fields, malformed
records, and unreadable files are rejected with useful errors. No records are
silently skipped. Use the same dataset across a referral's lifetime: historical
hospital IDs are preserved even if a later seed file changes.

SQLite stores referrals, hospital requests, and events with UUIDs and UTC timestamps.
Events record the action, demo actor/role, transition details, and referral version;
ordering by version remains deterministic even for equal timestamps. Referential
constraints link requests, selections, and events. Hospital existence is checked
by the service because hospital seeds remain in JSON, outside SQLite.

The walkthrough writes to your configured database and preserves referral history.
To start a separate experiment, use `--database /path/to/experiment.sqlite3` before
its command group. To reset a database intentionally, close application and DataGrip
connections, back up the file, and delete only that selected database file. The next
referral/request command recreates its schema. Database files and SQLite sidecars,
virtual environments, caches, build outputs, `.env` files, and private key files
are ignored by Git.

## Files and responsibilities

```text
ntt-data-hackathon-SiamCareNode/
├── README.md                     # This setup and testing guide
├── LICENSE
├── .gitignore
└── backend/
    ├── .env.example              # Shared database configuration template
    ├── .python-version
    ├── pyproject.toml
    ├── uv.lock
    ├── data/mock/hospitals.json
    ├── src/siamcare/
    │   ├── __init__.py
    │   ├── cli.py                # CLI entry point and error handling
    │   ├── config.py             # Environment and .env database paths
    │   ├── composition.py        # Construct repositories and services
    │   ├── errors.py
    │   ├── presentation.py       # JSON output
    │   ├── commands/
    │   │   ├── __init__.py
    │   │   ├── actors.py
    │   │   ├── hospitals.py
    │   │   ├── referrals.py
    │   │   └── requests.py
    │   ├── models/
    │   │   ├── __init__.py
    │   │   ├── hospital.py
    │   │   └── referral.py
    │   ├── repositories/
    │   │   ├── __init__.py
    │   │   ├── hospital_repository.py
    │   │   ├── json_hospital_repository.py
    │   │   ├── referral_repository.py
    │   │   ├── referral_schema.sql
    │   │   └── sqlite_referral_repository.py
    │   └── services/
    │       ├── __init__.py
    │       ├── hospital_service.py
    │       └── referral_service.py
    └── tests/
        ├── conftest.py
        ├── test_cli.py
        ├── test_config.py
        ├── test_hospital_repository.py
        ├── test_hospital_service.py
        ├── test_referral_cli.py
        ├── test_referral_repository.py
        └── test_referral_service.py
```

Models validate records; services enforce workflow rules; repositories handle
JSON and SQLite storage; command modules handle CLI arguments. Each workflow
write commits referral state, the changed request, and its event in one transaction.
The wheel bundles the hospital fixture and SQLite schema.

Local `.env`, SQLite files, `.venv/`, caches, and `dist/` are generated or private
files excluded from Git. They are not part of the shared source tree above.

## Current limitations

This is a local simulation with recorded capacity snapshots. It has no authenticated
users, live hospital integrations, reservations, transport dispatch, HTTP endpoints,
AI agents, or AWS deployment. History is useful for inspecting the workflow but is
not a tamper-proof audit log. Bed counts do not guarantee admission.

## License

[MIT](LICENSE) © 2026 Albert Zaw Sam
