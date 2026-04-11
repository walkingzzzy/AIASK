# Changelog

## Unreleased

### Added
- Added a real-run acceptance script for `factory_run_once` that validates persisted submit-stage completion across consecutive runs.
- Added dedicated research builder helper modules for artifact payload construction, feedback metrics, build steps, and context-source loading.

### Changed
- Split `factor_research_builder.py` into smaller helper modules to reduce builder complexity while preserving its public monkeypatch surface.

### Fixed
- Bounded external research generation and startup warmup sync timeouts so real factory runs degraded cleanly instead of hanging indefinitely.
- Recorded submit-stage entry from persisted run detail so acceptance checks reflected real `submit` completion instead of summary-only signals.
