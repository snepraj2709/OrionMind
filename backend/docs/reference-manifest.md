# Reference manifest

Recorded: 2026-07-21 (Asia/Kolkata)

## Workspace

- Reference mode: current working-tree snapshot
- Reference path: `/Users/snehaprajapati/iCloud Drive (Archive)/Documents/Sneha_Work/orion/Orion-Web-App`
- Target path: `/Users/snehaprajapati/Downloads/Orion Mind/backend`
- Canonical paths are distinct.
- Reference HEAD: `1a993c3438460dcdf5d0680a272e43c6c09e34e3`
- Reference dirty-state observation: clean (`git status --short` returned no paths).
- Safety rule: the reference is read-only; no target command writes into it.
- Target exception authorized by the owner: preserve the existing Stage 0 blueprint and trimmed
  contract and audit/revise them in place.

An earlier safety observation listed `backend/architecture_notes.md`; it disappeared due to an
external filesystem change before Stage 0 read it. This build did not remove or recreate it.

## Approved document checksums

SHA-256 values identify the exact current-worktree documents used by Stage 0.

Target execution contract: `Implementation_doc.md` —
`8057592723eaa35bacae80d7f3f82e15de759eeaf9b20a16ac1fd17be499c8d3`.

| Reference-relative path                | SHA-256                                                            |
| -------------------------------------- | ------------------------------------------------------------------ |
| `docs/orion_prd_plan.md`               | `40e4f5a19132d13ff6fadcfbe3ee09391afa94de92a4c5b3012f237490c099da` |
| `docs/IMPLEMENTATION_HANDOFF.md`       | `be0fc0d82280fd5c89d796c5fabd0b6189b850a3750f23b150055e3f7c965aca` |
| `docs/ORION_API_UI_CONTRACT.md`        | `86a443020916903717d5cfcc1f173bf8dc46c366fb08b991a641de32777cf30e` |
| `docs/ORION_DATABASE_DESIGN.md`        | `649e5658fd6d9125ca9383b1fd2d4eec77584357fcc462cc3c2feee04c8b4128` |
| `docs/ORION_DATABASE_DESIGN_REVIEW.md` | `8f62669342a83c7e515d411512df6005d660e034f9abbd893df9e6e07077f8f4` |
| `docs/contracts/orion-v1.openapi.yaml` | `d5af2a3bb865eebf6a8129f85c2fad1c7321781d74d92b1e374706178fc3a623` |
| `backend/requirements.txt`             | `b6a72342ccec907e87e57ffd60d9dd7a123f443b294c6db51c26ab18a7a5f2b2` |
| `backend/requirements-dev.txt`         | `95122798b3d76337ce774e7e00baa3b755f5c8be880801f464c3db5f87c6058b` |
| `backend/.env.example`                 | `37059f30e8bfd98b768c1018ce22907cfbb3562994ff16152e31593c45aee218` |
| `backend/app/main.py`                  | `a3ed71d3cdf8a962c1e69ac1074c374ee119c39ce52bca8c2ba757fd20c3adde` |
| `backend/app/router.py`                | `fb3add4ae1763a73a8048222f2244bfa6a18c0a17e51ea5b36a2376db20bc357` |

Current feature modules, shared platform code, relevant ordered migrations, and relevant tests were
read from the recorded Git snapshot. They are implementation evidence below the approved documents,
not separately elevated contract documents.

## Selected versions

Runtime:

- Python 3.11
- FastAPI 0.110.1
- Uvicorn 0.25.0
- Pydantic 2.12.5
- pydantic-settings 2.14.2
- SQLAlchemy 2.0.51
- psycopg binary 3.2.9
- Supabase Python 2.27.2
- OpenAI Python 1.99.9
- PyCryptodome 3.23.0
- httpx 0.28.1
- python-multipart 0.0.21
- python-dotenv 1.2.1
- OpenTelemetry API/SDK/exporter 1.43.0
- OpenTelemetry FastAPI/SQLAlchemy instrumentation 0.64b0

Development and infrastructure:

- pytest 8.4.2
- PostgreSQL 15+
- FFmpeg and FFprobe
- Docker with Python 3.11 slim

No dependency was upgraded during Stage 0.
