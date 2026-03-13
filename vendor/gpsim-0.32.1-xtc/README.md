# gpsim-0.32.1-xtc

Local DLCP analysis fork of upstream `gpsim` 0.32.1.

## Provenance

- Upstream project: `gpsim` (`http://gpsim.sourceforge.net/`)
- Local source tree name: `vendor/gpsim-0.32.1-xtc/`
- Intended local build/output root: `artifacts/tools/gpsim-xtc/`
- Intended local binary name: `gpsim-xtc`

This fork started from a downloaded upstream `gpsim-0.32.1` source drop and is
kept here as an explicit local fork for DLCP simulator work.

## Local Modifications Policy

- Keep upstream version lineage visible in the directory name.
- Keep local divergences minimal and focused on DLCP requirements.
- Record new device-model or build-system changes in repository docs when they
  affect simulator behavior or canonical paths.
- Keep build outputs out of this source tree.

## Current Local Purpose

- Add `PIC18F25K20` support needed by the DLCP CONTROL firmware harness.
- Provide a reproducible repo-local gpsim build for tests and simulator tools.
