# Documentation source and provenance

**Transfer date:** 29 October 2026  
**Source workspace:** `C:\Users\mikef\Downloads\Tory-Poc`  
**Destination:** course repository `ay2627s2-cicdp-MikeAbat`

The documents under `docs/` were copied from the Tory-PoC workspace's `docs/` folder. The copied set includes Planning records, Requirements-stage working documents, accepted ADR-001, the technology evaluation, and PoC feasibility, results, and handover reports. These documents retain their original dates, decision attributions, scope statements, and evidence limitations. This note records provenance; it does not change or extend any project approval.

## P1 approval record

`planning/PLANNING_GATE_P1.md` was present in the source documentation and records Planning exit approval with conditions and explicit Requirements-entry authorisation on 29 October 2026. The record attributes the decision to the project owner and says it memorializes the owner's official project decision. No signature was supplied or added. The conditions remain tracked actions, not claims that the actions have been completed. Requirements exit remains unapproved.

## Transfer boundary

Only documentation files were transferred from the source workspace. The PoC's Python application source, migrations, tests, settings, dependency files, environment files, database files, virtual environment, caches, and `.git` directory were not copied. The PoC's separate Git history was not imported. PoC reports describe historical evidence; their results are not a verification run performed in this repository and do not establish that Tory itself is implemented, complete, or production-ready.

## PoC-only references

Some source documents discuss or cite PoC implementation files that are intentionally absent from this repository. Those paths are evidence references in the original reports, not files promised by this transfer. See [PoC handover](POC_HANDOVER.md), [PoC results](POC_RESULTS.md), and [technical feasibility](TECHNICAL_FEASIBILITY.md) for the recorded scope and limitations. The source workspace retained separately is the location for the original PoC source and its artifacts.

The following source-only paths remain intentionally unresolved here: `requirements.txt`, `.env.example`, `manage.py`, `config/settings.py`, `config/urls.py`, `inventory/models.py`, `inventory/services.py`, `inventory/csv_import.py`, `inventory/tests.py`, and `inventory/migrations/`. They identify the separate experiment's evidence and are not broken links to files in this repository.
