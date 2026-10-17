# JobDataPlatform

## Goal

Turn Wuhan job-posting snapshots into a Django + MySQL data service

## Tech stack

- Python 3.10+ (standard library first), pytest for tests.

## Directory layout

```text
JobDataPlatform/
+- README.md            # this file
+- docs/                # requirements, design, decisions
+- tests/               # automated tests
+- src/JobDataPlatform/     # package code
+- scripts/           # reusable scripts
\- .gitignore
```

## Install

```bash
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Run

```bash
py -3.14 -m jobdataplatform
```

## Verification commands

```bash
.\.venv\Scripts\python.exe -m pytest
verify-ai-project -Path 'D:\AIProjects\DeepSeek Harness\JobDataPlatform'
```

## Status

- Created 2026-10-17 as a $Type project. First working slice not implemented yet.

## Known issues

- Nothing implemented yet; this section must be updated as real limitations appear.

## Next steps

- Implement the first usable slice, then replace this section with the real backlog.

## Hand-off notes

- Read ..\AGENTS.md (agent rules) and ..\..\AGENTS.md (area rules) before changing anything.
- Register changes in ..\PROJECTS.md and ..\..\PROJECT_INDEX.md.
- Never commit secrets or real user data; keep placeholders like <PLACEHOLDER>.