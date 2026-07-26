# Firebird Backend Deployment Bundle

This directory prepares the Stage 3 backend for an SSH-only deployment. It does
not deploy automatically.

## Safety boundary

- Do not run the installer on Firebird without explicit authorization.
- Replace the placeholder video root with administrator-approved roots.
- Confirm the fixed SSH host and the registry filesystem's locking behavior
  before creating real data.
- All workflow users need appropriate shared read/write permissions on the
  registry root. The installer does not change ownership or group membership.
- Mac clients must call the installed command through SSH. They must not mount
  Firebird or open the SQLite file.

## Prepare configuration

Copy `backend.example.json` to a separate deployment-specific file and replace:

```text
/data/labs/vformic1-swat-lab/REPLACE_WITH_APPROVED_VIDEO_ROOT
/data/labs/vformic1-swat-lab/REPLACE_WITH_APPROVED_TOML_INBOX
```

Use only narrow roots the GUI is allowed to browse or scan. Roots may be added
to both lists when a directory intentionally contains both videos and TOMLs.
The default `minimum_file_age_seconds` is 300 so recently changing Globus files
are not offered as candidates immediately.

## Preview installation

Run the installer with `--dry-run` first:

```bash
deployment/firebird/install_backend.sh \
  --prefix /absolute/firebird/software/path \
  --source /absolute/path/to/IDtracker_workflow_manager \
  --config /absolute/path/to/backend.json \
  --dry-run
```

The dry run prints intended installation actions and does not create files.

## Installation

After explicit authorization, repeat without `--dry-run`. The installer:

1. creates a dedicated virtual environment;
2. installs this package without third-party dependencies;
3. installs the configuration only when no configuration already exists;
4. runs the backend's read-only prerequisite check.

The backend command accepts one request on standard input and returns one JSON
response on standard output:

```bash
echo '{"protocol_version":1,"request_id":"check","action":"health","parameters":{}}' |
  /absolute/firebird/software/path/venv/bin/idtracker-firebird-backend \
    --config /absolute/firebird/software/path/config/backend.json \
    --request
```

The application-level lock serializes backend registry operations. This does
not by itself prove that an arbitrary network filesystem is safe for SQLite.
Keep all registry access behind this backend, use one fixed Firebird host, and
complete concurrency plus `PRAGMA integrity_check` validation before real lab
deployment.
