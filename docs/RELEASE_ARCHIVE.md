# Historical Release Archive

This archive keeps older firmware versions out of the root README.  The supported deployment described in the README is **V3.2 MAIN + V1.71 CONTROL**.

## Stock Baseline

| Component | Stock version | Notes |
|---|---|---|
| MAIN | V2.3 | Original Hypex MAIN firmware for PIC18F2455-class DLCP units. |
| CONTROL | V1.6b | Latest stock CONTROL baseline used for V1.7/V1.71 source rewrite work. |

Stock operation works for normal use, but the firmware has unbounded waits and limited fault visibility.  The V3.2 + V1.71 line exists primarily to fix those robustness gaps.

## MAIN History

| Version | Type | Historical role |
|---|---|---|
| V2.4 | Binary patch | First A/B preset switching patch. |
| V2.5 | Binary patch | Added bounded timeouts on UART/MSSP/I2C blocking waits. |
| V2.6 | Binary patch | Added DSP ACKSTAT checks and safer volume dirty-bit handling. |
| V2.7 | Binary patch | Added bus-clear, DSP ping, BF/08 fault status, and PEN timeout work. |
| V2.8 | Binary patch | Added delayed mute/hold preset switching. Last practical binary-patched MAIN line. |
| V3.0 | Source rewrite | Stock-equivalent source-assembled baseline. |
| V3.1 | Source rewrite | Integrated the V2.x features into source; precursor to V3.2. |
| V3.2 | Source rewrite | Current supported MAIN release. |

## CONTROL History

| Version | Type | Historical role |
|---|---|---|
| V1.61b | Binary patch | A/B preset UI and V1.6b setup-LCD fix. |
| V1.62b | Binary patch | UART OERR recovery and bounded reconnect handshake. |
| V1.63b | Binary patch | BF/08 parser, LCD `!` indicator, resync-on-clear. |
| V1.64b | Binary patch | Explicit IR standby/wake endpoints. |
| V1.7 | Source rewrite | Stock-equivalent source-assembled V1.6b baseline. |
| V1.71 | Source rewrite | Current supported CONTROL release. |

## Compatibility Notes

V3.2 MAIN and V1.71 CONTROL are designed to run together.  Older combinations can still be useful for comparison or rollback, but they do not expose the full current feature set.

| MAIN | CONTROL | Status |
|---|---|---|
| V3.2 | V1.71 | Current supported pair. |
| V3.2 | V1.64b or older patched CONTROL | Basic operation; no V1.71 diagnostics page or CONTROL Layer 1/2 hardening. |
| V3.1/V3.0/V2.x | V1.71 | Basic operation; diagnostics pages show `n/a` because older MAINs do not provide V3.2 counters. |
| V2.8 | V1.64b | Legacy binary-patched fallback pair. |

## Historical Docs

- [docs/V31_RELEASE.md](V31_RELEASE.md)
- [docs/AB_PRESETS.md](AB_PRESETS.md)
- [docs/ROBUSTNESS.md](ROBUSTNESS.md)
- [docs/V27_V163B_SPEC.md](V27_V163B_SPEC.md)
- [docs/V27_V163B_STATUS.md](V27_V163B_STATUS.md)
- [docs/V30_SOURCE_REWRITE_SPEC.md](V30_SOURCE_REWRITE_SPEC.md)
- [docs/V31_SOURCE_REWRITE_SPEC.md](V31_SOURCE_REWRITE_SPEC.md)
- [docs/V16B_SOURCE_REWRITE_SPEC.md](V16B_SOURCE_REWRITE_SPEC.md)
