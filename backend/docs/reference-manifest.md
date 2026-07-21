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

## P0-03 shared-queue artifacts

Recorded after the P0-03 implementation and local verification on 2026-07-21. The generalized
processing worker replaces the historical-import-only process; the web process no longer performs
historical recovery.

| Target-relative path                     | SHA-256                                                            |
| ---------------------------------------- | ------------------------------------------------------------------ |
| `migrations/0006_shared_entry_queue.sql` | `a4e71e3376bcc0ecdf7c17d1dcefda1ef55afd4736e752c59041dea62fc200f4` |
| `supabase_schema.sql`                    | `3f9380b597953afd1cc1d7b9ef85762c07ac924df2a68b467e3cfe6a560ca4f2` |
| `scripts/run_processing_worker.py`       | `f37e3274667398a6cbcbce2bbc5a25d18946497028ebcfcac505f6e41547a78b` |
| `app/modules/jobs/worker.py`             | `d0da2002bdcd90f277dfe20dce82fefeb79252685a384d214e70a6f55d818c24` |

## P0-04 combined entry-analysis artifacts

Recorded after the P0-04 implementation and local verification on 2026-07-21. The combined analyzer
replaces the legacy-only entry-worker success path while retaining its user-visible extraction
outputs. The P0-03 schema checksum above remains historical; the checksum below is the current exact
ordered fresh-install schema through migration 0007.

| Target-relative path                          | SHA-256                                                            |
| --------------------------------------------- | ------------------------------------------------------------------ |
| `migrations/0007_combined_entry_analysis.sql` | `fb9275b2219477dca38301832603d6726a2298ff17f91198303c8178fa8506be` |
| `supabase_schema.sql`                         | `1c9b7c6b97de54b14df9ea7c8c96bba12429747351fbf449522737bb29bf5b07` |
| `app/modules/processing/quality.py`           | `ef5aa76789a39c47c3de5c42c4a7416a4568fa97837451096b560b6079c25fe5` |
| `app/modules/processing/prompts.py`           | `e2a6d26d0732f391a891fe0d473f965cefe04bfa37c078baa7210dad246c20df` |
| `app/modules/processing/provider.py`          | `09556b8a9f55a8f1d494dee5e74e21a484ce0dafecca805b7ea5390086180764` |
| `app/modules/processing/schemas.py`           | `8d03f69737225fd3edd737186d4e6592a27d34938eea8d2b01fa799940d7d8e7` |
| `app/modules/processing/service.py`           | `1c8d0276d614f1026e10675666d0367f8ddc57d7de0a7a72e3bcc3963782e47f` |
| `app/modules/processing/repository.py`        | `bc5c04be35eb637a9aeaa5f3de0b874a2db2ef0076c0872454056e0ff815d48c` |
| `app/modules/jobs/service.py`                 | `fb97c8fcfbade4bb562a29f6349334556302cf30c5fef6ca2694891b0364bb1b` |
| `tests/test_stage7_entry_analysis.py`         | `493e52372ad2b7da4491f97808c84aaf93740e3b2392f8543aab5b74e41c031d` |
| `tests/test_stage7_reflection_quality.py`     | `a50b69bfb61929ec00400a6da01c4f38a82bae15aaca5bf494513160e6c07ffb` |

## P0-05 deterministic candidate artifacts

Recorded after the P0-05 implementation and local verification on 2026-07-21. Candidate
construction is deterministic and model-free; synthesis, snapshots, scheduler behavior, public
Reflection APIs, and frontend integration remain outside this slice. The P0-04 schema checksum
above remains historical; the checksum below is the current exact ordered fresh-install schema
through migration 0008.

| Target-relative path                                      | SHA-256                                                            |
| --------------------------------------------------------- | ------------------------------------------------------------------ |
| `migrations/0008_deterministic_reflection_candidates.sql` | `e906fa06dc8c228c7b3bc1ee619f2e61c4506dce1705288e5801566c0c9f690d` |
| `supabase_schema.sql`                                     | `9fa7ccc73d7579c12171533f6cb336193b7d980dde0a334c3399e7ac333683f5` |
| `app/shared/security/encryption.py`                       | `95eee6891dceee6edcc47b88fd3924efa26f4450acdc9186507395800a7fc083` |
| `app/modules/reflection_engine/__init__.py`               | `c4abbf8fade07beb12dd0731a469178c1a9377d1863e4eb7c69d210dec79ff4d` |
| `app/modules/reflection_engine/schemas.py`                | `c07e9ca029cd174606d250a1594a00478286daebd97d9a93cbfdd31c1b614231` |
| `app/modules/reflection_engine/scoring.py`                | `dee2ebe7ed2fab69be60f60290504df47beedb40b9f5ffddc483debdb62c6b2e` |
| `app/modules/reflection_engine/evidence.py`               | `034efe469d0e9d6249257f0e1dc8868cf80ca423a7ed74ac90a1e91f433c86ab` |
| `app/modules/reflection_engine/repository.py`             | `5265ae10d4dc77357af6dbd07ce2052d0552d2c2459aceab0030626f2e08166b` |
| `app/modules/reflection_engine/service.py`                | `c5a985621b8f34f17b4eb15840d6b1bc0c61c2d1e0ab8b635128a165d6eb8e92` |
| `tests/test_stage7_reflection_candidates.py`              | `53cd92d378f6aea6fc73e7ecffcf82b94e2de4f0bd3652ab16f22ee4cf7e20d5` |
| `tests/test_stage7_reflection_database.py`                | `8a16387c157bada2ec3f04e47918442169392f26ca1bc61f68f0a431e6420e55` |

## P0-06 scheduler and reflection-synthesis artifacts

Recorded after the P0-06 implementation and local verification on 2026-07-21. The P0-05
checksums above remain historical; the checksum below is the current exact ordered fresh-install
schema through migration 0009. P0-07 APIs and frontend work are not included.

| Target-relative path                          | SHA-256                                                            |
| --------------------------------------------- | ------------------------------------------------------------------ |
| `migrations/0009_reflection_synthesis.sql`    | `e89f976e09b8f26234de46110255817b97f4cf45af2725799c1f58708d78f791` |
| `supabase_schema.sql`                         | `2b5135b36fdeae4249cb68bd714aa9b493c9907c6b5079f1ba16c6256feb31a1` |
| `app/main.py`                                 | `34ad7da2c44790cefdbbaef0103cb71c3aba78e6eab4712f03cab60a3a49b9d5` |
| `app/modules/jobs/repository.py`              | `998aa4855b0e9bccb5a97bd910ede541ea5774055e90a71b518a295cc394490d` |
| `app/modules/jobs/service.py`                 | `34ef5a0831b5ce69ec2870bb09d2670b777399a49472c26d66e2a6f0a67767d1` |
| `app/modules/jobs/worker.py`                  | `41d1864daa8db8dcca0f001d8daa59a8cd4157a029bf115816171dd5a16b234e` |
| `app/modules/reflection_engine/evidence.py`   | `82e178d585ac6ec8c2dd15a4f3eb4b352a7062d9dedaafdbbe3b4210cc630172` |
| `app/modules/reflection_engine/prompts.py`    | `d62834c4f9e168f1a588a6832b03c641f8cecb188b42e45f4c0a2ed679e06669` |
| `app/modules/reflection_engine/provider.py`   | `e89b4158a92ff97174514110b5fa69a0dbf5debb089723a8c11dc0a6aad639ef` |
| `app/modules/reflection_engine/repository.py` | `14b44861b0e374ab57daf5ef9a8abdc13cf7cd5d72425ebbd5fb908fd4483baa` |
| `app/modules/reflection_engine/schemas.py`    | `076b052b5d5a4fe11226d27a2d523540a4e7263ee111fec5af7efd84021a027e` |
| `app/modules/reflection_engine/service.py`    | `4ef7aec706707f845cc0d43ab5eff7ad736d2b16db05873ccd65578459dc8a85` |
| `app/shared/config/settings.py`               | `7ea3af874d76825b1b14f477f706d9c11d71dcc27f1d69b5a5752d730a5f1a4d` |
| `.env.example`                                | `21a30fb14716fff9a4ceaadcb1406eac11eed0bda5ce3c1abcb00dec21645e08` |
| `tests/test_stage7_reflection_database.py`    | `0cc341cdf8262269b383f1541bbf66c1ff5caf4257a1e08e982836d5765332f7` |
| `tests/test_stage7_reflection_synthesis.py`   | `41f8dd46a0904e2a2a16ecbaa4620c0caa418a9da854bcc1341457bd69af2fce` |
