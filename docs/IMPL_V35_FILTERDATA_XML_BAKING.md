# V3.5 FilterData XML Preset Baking Implementation Plan

Date: 2026-06-26
Status: Implemented - verified
Source spec: `docs/SPEC_V35_FILTERDATA_XML_BAKING.md`

## Scope

Implement the V3.5 release-flash default change from pre-captured `.bin` +
`.json` preset overlays to direct Hypex FilterData XML baking:

- preset A from `artifacts/LX521.4/FilterData/LX521.4 22MG10F-v5/Config.xml`
- preset B from `artifacts/LX521.4/FilterData/LX521.4 22MG10F-v8/Config.xml`
- no generated `.bin` or `.json` files during release flashing
- preserve the existing lower-level `.bin/.json` capture path for manual/debug
  compatibility and older release wrappers
- verify the canonical V3.5 v5/v8 generated table hashes before any USB
  access, because the default XML inputs live under ignored local artifacts

This is Python tooling/docs/tests work. It must not edit MAIN or CONTROL
assembly, rebuild canonical HEX artifacts, or flash hardware during
implementation.

## Required Docs Read

- `AGENTS.md`: repository layout, path policy, V3.5 release ceremony, current
  test gates, and maintenance rules.
- `README.md`: current operator deployment flow; currently documents local
  `.bin/.json` captures for V3.5 and must be updated.
- `CODING_STYLE.md`: local style and verification discipline.
- `docs/SPEC_V35_FILTERDATA_XML_BAKING.md`: source requirements.
- `docs/V31_RELEASE.md` and `docs/V32_RELEASE.md`: historical baked-capture
  operator contract inherited by V3.x wrappers.
- `docs/AB_PRESETS.md`: A/B table flash bases and filename EEPROM slots.
- `docs/HARDWARE_LOOP.md`: capture-flash behavior in measurement workflow; do
  not make it the primary path for this feature.
- `docs/HARDWARE_TEST.md`: live V3.5 prerequisites and diagnostics gates.
- `docs/TEST_SIMULATOR.md`: simulator framework context; `AGENTS.md` is the
  authoritative current test matrix.
- `.gitignore`: `artifacts/LX521.4/` is ignored/local, so required tests must
  not depend on those files being present in a clean checkout unless explicitly
  skipped with a local-fixture reason.

## Source Requirements

Goals:

- Make `scripts/dlcp_v35_release_flash.py --left|--right|--all-ch` bake
  FilterData XML by default.
- Force `mode="hfd-pz"` for V3.5 XML defaults.
- Derive filename slots from the FilterData directory name, padded to `0x1E`
  bytes with `0xFF`.
- Reuse the existing MAIN overlay/finalize machinery by constructing the same
  `CaptureOverlay` shape in memory.
- Print preflight evidence for XML source, config name, mode, flash base, and
  table SHA256.
- Do not create `LX521.4_*.bin` or `LX521.4_*.json`.
- For the V3.5 default XML path, hard-fail before any USB enumeration/open/flash
  unless generated table hashes match the known v5/v8 anchors and derived names
  match the canonical directory names. Noncanonical XML is allowed only through
  an explicit noisy developer override.

Non-goals:

- Do not migrate V3.1/V3.2/V3.3/V3.4 wrappers unless needed to keep shared
  helpers compatible.
- Do not delete existing local capture artifacts; they remain useful fixtures
  and manual/debug inputs.
- Do not change DSP coefficients, XML source files, or firmware assembly.

Invariants:

- preset A table stays `0x5600..0x5FFF`.
- preset B table for V3.1+ stays `0x4C00..0x55FF`.
- filename EEPROM slots stay A `0x60..0x7D`, B `0x83..0xA0`.
- active filename RAM stays `0x02C0..0x02DD`.
- lower-level `--capture-a/--capture-b` remains supported in
  `dlcp_main_flash.py`.
- validation failures for missing XML, bad XML, hash mismatch, and source
  conflicts happen before any USB access, not merely before USB writes.

## Current Implementation Evidence

- `src/dlcp_fw/flash/dlcp_release_flash_common.py` hard-codes
  `CAPTURE_A_BIN`, `CAPTURE_A_META`, `CAPTURE_B_BIN`, and `CAPTURE_B_META`
  under `artifacts/LX521.4/`, checks their presence, and otherwise forwards an
  unbaked `--hex --all-ch` command with a warning.
- `src/dlcp_fw/flash/dlcp_v35_release_flash.py` re-exports those capture
  constants and passes them into the shared release wrapper.
- `src/dlcp_fw/flash/dlcp_main_flash.py` defines:
  - `CaptureOverlay(preset, table, name_slot, config_name, flash_base)`
  - `resolve_capture_flash_base()` for A and version-aware B bases
  - `_load_capture_overlay()` for `.bin/.json` sources
  - `_apply_capture_overlay()` for byte overlay into parsed HEX memory
  - preflight output that currently prints `capture {A|B} overlay`, name, base,
    and table SHA.
- `src/dlcp_fw/flash/filterdata_xml.py` is currently untracked code produced by
  this analysis. It parses HFD `Config.xml`, builds a `0x0A00` table, supports
  `auto/direct/legacy/hfd-pz`, and already proves v5 `hfd-pz` matches the
  existing v5 capture. It currently uses stdlib XML parsing and needs input
  hardening before becoming part of the flash path.
- `scripts/dlcp_filterdata_xml_to_bin.py` is an untracked CLI wrapper around
  that converter. It is useful for manual verification but must not be used by
  the V3.5 release path to write temporary `.bin` files.
- `tests/sim/test_filterdata_xml_to_bin.py` is untracked coverage for XML
  source discovery, v7/v5 conversion behavior, and CLI verification. It needs
  v5 `hfd-pz` and v8 SHA coverage for the new default.
- `tests/sim/test_dlcp_v35_release_flash.py` currently expects V3.5 to forward
  `--capture-a --meta-a --capture-b --meta-b` and to warn/fallback when local
  captures are absent. These tests should become red before the implementation.
- `tests/sim/test_dlcp_main_flash_capture_overlay.py` covers lower-level
  `.bin/.json` overlay stream behavior and finalizer filename writes. It should
  retain capture compatibility and gain XML overlay tests.
- `tests/hardware/test_live_state_transitions.py` derives the default expected
  preset-A filename from `dlcp_v35_release_flash.CAPTURE_A_META`; this must
  move to XML-derived default names for both A and B. Some current hardware
  gates still derive current-release A/B names from V3.2 capture sidecars.
- `README.md` still says V3.5 CLI uses captured `.bin/.json` files and flashes
  unbaked when they are absent.
- `AGENTS.md` currently says the V3.5 wrapper preserves the old baked-capture
  behavior.
- `docs/HARDWARE_TEST.md` still documents current baked preset B as
  `LX521.4 22MG10F-v7`; V3.5 XML defaults intentionally change B to v8.

## Gap Analysis

What exists:

- A working overlay/finalize path once code has a `CaptureOverlay`.
- A working XML-to-table converter in untracked files.
- Tests for old capture forwarding and lower-level capture overlay behavior.

What is missing:

- First-class `dlcp_main_flash.py` XML source arguments.
- A helper to resolve a FilterData directory or `Config.xml` path.
- A helper to build `CaptureOverlay` from XML without writing files.
- V3.5 wrapper defaults for v5/v8 XML sources plus expected SHA/name gates.
- Tests that missing captures no longer affect V3.5 when XML exists.
- Tests that v8 XML is the new preset-B default.
- Tests that no `.bin/.json` files are created, using explicit filesystem
  snapshots rather than `git status`.
- Always-on tests using tracked or temporary XML fixtures, because the real
  LX521 XMLs are under ignored local `artifacts/`.
- Docs that describe the new XML-native V3.5 flow.

What is stale:

- README V3.5 prepare/warning text.
- AGENTS V3.5 release ceremony wording.
- V3.5 wrapper constants and tests named around captures.
- Hardware preset filename expectations that read capture sidecars or still
  expect preset B v7 for the current V3.5 path.

## Proposed Implementation

### Work Unit 1: Stabilize The XML Compiler In Place

Keep `src/dlcp_fw/flash/filterdata_xml.py` in its current package for this
implementation. A package move would add import churn before the XML-default
release path is proven and is not required by the source spec.

Required changes in that module:

- Switch XML parsing to a hardened path, preferably `defusedxml.ElementTree`.
  If adding `defusedxml` requires dependency metadata changes, update the
  project dependency file and lockfile intentionally.
- Reject DTD/entity payloads, oversized XML files, unexpected object counts,
  non-finite numeric values, and out-of-range semantic fields before coefficient
  math.
- Add explicit guard constants and tests:
  - `MAX_FILTERDATA_XML_BYTES = 2_000_000` (local v5/v7/v8 XML files are about
    96 KB; this leaves large export headroom while rejecting accidental huge
    inputs).
  - `MAX_FILTERDATA_XML_ELEMENTS = 5000`.
  - exactly 6 channels and 15 biquads per channel for generated DLCP tables;
    at most 256 `processobj` nodes overall.
  - sample rate `8000 <= fs <= 384000`.
  - frequency `0 < f1 < fs / 2`.
  - Q `0 < q1 <= 100`.
  - gain `-144 <= gain_db <= 48`.
  - delay `0 <= delay_ms <= 2550` so `floor(delay/10)` cannot wrap the
    one-byte DLCP delay field.
  - embedded/direct coefficient fields must be finite and fit the TAS fixed
    range before packing (`-16 <= coeff < 16`).
- Keep the manual `scripts/dlcp_filterdata_xml_to_bin.py` CLI available for
  explicit operator/debug use, but the V3.5 release path must not call it or
  write its outputs.
- Add tests for DTD/entity rejection, oversized XML rejection, bad numeric
  rejection, and normal synthetic XML conversion.

### Work Unit 2: Add Canonical FilterData Paths

In `src/dlcp_fw/paths.py`, add explicit constants using existing path policy:

- `LX521_ARTIFACTS_DIR = ARTIFACTS_DIR / "LX521.4"`
- `LX521_FILTERDATA_DIR = LX521_ARTIFACTS_DIR / "FilterData"`
- `V35_FILTERDATA_PRESET_A = LX521_FILTERDATA_DIR / "LX521.4 22MG10F-v5"`
- `V35_FILTERDATA_PRESET_B = LX521_FILTERDATA_DIR / "LX521.4 22MG10F-v8"`
- `V35_FILTERDATA_PRESET_A_NAME = "LX521.4 22MG10F-v5"`
- `V35_FILTERDATA_PRESET_B_NAME = "LX521.4 22MG10F-v8"`
- `V35_FILTERDATA_PRESET_A_SHA256 =
  "5e352d409ce18c79ae5aa558b988fb0dddbacda4ca455aa0ffb9336a138e78d8"`
- `V35_FILTERDATA_PRESET_B_SHA256 =
  "474f93fceabb7d06e6936e11c1075ad59c1e588a9696290f831cf9039d2eb043"`

Do not add constants for generated v5/v8 `.bin` or `.json` defaults.

### Work Unit 3: Build XML Overlays In Memory

In `src/dlcp_fw/flash/dlcp_main_flash.py`:

- Add CLI args:
  - `--filterdata-a PATH`
  - `--filterdata-b PATH`
  - `--filterdata-mode {hfd-pz,direct,legacy,auto}`, default `hfd-pz`
  - internal/advanced expected-value args used by the V3.5 wrapper:
    `--filterdata-a-sha256`, `--filterdata-b-sha256`,
    `--filterdata-a-name`, `--filterdata-b-name`
    These should be hidden from `dlcp_main_flash.py --help` or clearly labeled
    as advanced wrapper-owned validation guards.
- Add conflict checks:
  - `--filterdata-a` conflicts with `--capture-a` and `--meta-a`.
  - `--filterdata-b` conflicts with `--capture-b` and `--meta-b`.
  - `--name-a/--name-b` remains allowed for both source types as an override.
- Add `_resolve_filterdata_config(path: Path) -> Path`:
  - directory input resolves to `path / "Config.xml"`;
  - file input must be an existing file, normally `Config.xml`;
  - missing directory, missing `Config.xml`, or non-file input is a parser
    error before any USB access.
- Add `_load_filterdata_overlay(...) -> CaptureOverlay`:
  - resolve flash base with existing `resolve_capture_flash_base()`;
  - build table using `build_preset_table(config_xml, mode=args.filterdata_mode)`;
  - assert `len(table) == PRESET_TABLE_SIZE`;
  - derive default `config_name` from `config_xml.parent.name`;
  - encode with existing `_encode_name_slot()`;
  - if expected name/SHA are supplied, compare the derived name and table SHA
    and fail through `argparse` before any USB access on mismatch;
  - store XML source and mode in the overlay for preflight output.
- Extend `CaptureOverlay` with defaulted metadata fields:
  - `source_path: Path | None = None`
  - `source_kind: str = "capture"`
  - `source_mode: str | None = None`
  - `source_sha256: str | None = None`

Keep existing `_load_capture_overlay()` and `_apply_capture_overlay()` behavior.

Preflight output should keep old capture lines for capture overlays and print
XML-specific lines for FilterData overlays, for example:

```text
  filterdata A source: artifacts/.../LX521.4 22MG10F-v5/Config.xml
  filterdata A mode: hfd-pz
  filterdata A name: 'LX521.4 22MG10F-v5'
  filterdata A flash base: 0x5600
  filterdata A table sha256: ...
```

Print canonical repo-local paths relative to the repository root. For external
absolute paths, avoid leaking `/Users/...` by printing a redacted or abbreviated
form unless a future explicit debug flag requests raw paths.

### Work Unit 4: Make V3.5 Wrapper XML-Default

In `src/dlcp_fw/flash/dlcp_release_flash_common.py`:

- Extend `build_forward_argv()` and `release_main()` with optional
  `filterdata_a`, `filterdata_b`, `filterdata_mode`, expected names, expected
  SHA256 values, and `allow_unverified_filterdata`.
- Preserve capture behavior when those XML defaults are not supplied, so
  V3.1/V3.2/V3.3/V3.4 wrappers remain unchanged.
- When XML defaults are supplied:
  - require route as before;
  - require release hex as before;
  - require both XML source paths through a directory-aware resolver/check;
  - forward `--filterdata-a`, `--filterdata-b`, `--filterdata-mode hfd-pz`,
    expected names/SHA values, `--all-ch`, and optional `--profile`;
  - do not inspect `CAPTURE_*` files and do not emit the old unbaked warning.
- `--info-only` and `--finalize-only` must continue to bypass release-artifact
  and XML validation, while still forwarding `--profile` exactly as today.
- Parameterize the parser description/help so V3.5 advertises XML FilterData
  defaults; older wrappers keep the capture-based wording.

In `src/dlcp_fw/flash/dlcp_v35_release_flash.py`:

- Replace V3.5 capture-default constants with:
  - `FILTERDATA_A = V35_FILTERDATA_PRESET_A`
  - `FILTERDATA_B = V35_FILTERDATA_PRESET_B`
  - `FILTERDATA_MODE = "hfd-pz"`
  - `FILTERDATA_A_NAME`, `FILTERDATA_B_NAME`
  - `FILTERDATA_A_SHA256`, `FILTERDATA_B_SHA256`
- Pass those into the shared wrapper.
- Add `--allow-unverified-filterdata` for developer/noncanonical XML tests or
  manual debug. It must be noisy in help/preflight and must not be used by the
  normal V3.5 operator path.
- Expose a small helper or mapping for tests/hardware to derive both preset
  display names without reading JSON, for example
  `DEFAULT_PRESET_NAMES = {"A": FILTERDATA_A_NAME, "B": FILTERDATA_B_NAME}`.

### Work Unit 5: Update Current Hardware Expectations

The implementation must separate historical V3.2/v7 capture-era gates from the
current V3.5 XML release contract:

- Update V3.5/current hardware tests that assert preset names to use the V3.5
  XML-derived names A=`LX521.4 22MG10F-v5`,
  B=`LX521.4 22MG10F-v8`.
- Keep truly historical V3.2/V3.4 or V1.71/V3.2 ledger gates version-scoped and
  documented as historical. Do not repurpose `scripts/run_v171_v32_ledger_hardware_gate.py`
  unless it is being used as a current V3.5 release gate; if a current V3.5
  phase runner is needed, add or update a V3.5-specific path.
- Update `docs/HARDWARE_TEST.md` so current V3.5 filename criteria expect
  v5/v8 and any v7 references are explicitly historical.

### Work Unit 6: Update Tests

Update/add focused tests:

- `tests/sim/test_filterdata_xml_to_bin.py`
  - keep imports from `dlcp_fw.flash.filterdata_xml`;
  - add always-on synthetic XML coverage that does not require
    `artifacts/LX521.4`;
  - gate local v5/v8 anchor checks with clear `pytest.skip` reasons when the
    ignored local XML/capture fixtures are absent;
  - when local fixtures are present, check v5 `mode="hfd-pz"` byte-for-byte
    against the existing v5 capture and v8 SHA
    `474f93fceabb7d06e6936e11c1075ad59c1e588a9696290f831cf9039d2eb043`;
  - add hostile-input tests for DTD/entity, oversize, and invalid numeric XML;
  - keep CLI tests for manual generation, but the V3.5 release path must not
    call the CLI or write files.
- `tests/sim/test_dlcp_main_flash_capture_overlay.py`
  - add XML overlay stream test for A and B using temporary/minimal XML;
  - assert stream bytes at `0x5600` and `0x4C00` match
    `build_preset_table(..., mode="hfd-pz")`;
  - assert derived filename slot equals directory name padded with `0xFF`;
  - test both directory input and explicit `Config.xml` input for A and B;
  - assert `--filterdata-*` conflicts with corresponding `--capture-*` and
    `--meta-*`;
  - assert missing XML, parse failure, hash/name mismatch, and conflicts abort
    before any HID enumeration/open/switch/flash call;
  - capture preflight stdout and assert XML source, derived names, `hfd-pz`,
    bases `0x5600`/`0x4C00`, SHA values, and no old unbaked-capture warning;
  - snapshot temp directories before/after preflight or dry-run and assert no
    `.bin` or `.json` files are created or modified;
  - assert preflight output for repo-local paths is repo-relative and does not
    contain `/Users/`;
  - assert preflight output for an external absolute XML path redacts or
    abbreviates the path unless a future explicit raw-path debug flag is used;
  - assert lower-level `dlcp_main_flash.py --help` hides or clearly labels the
    expected SHA/name args as advanced wrapper-owned validation guards;
  - keep existing `.bin/.json` capture tests green.
- `tests/sim/test_dlcp_v35_release_flash.py`
  - update forwarding test to expect `--filterdata-a`, `--filterdata-b`,
    `--filterdata-mode hfd-pz`, expected names/SHA values, not captures;
  - replace missing-capture fallback test with "missing captures ignored when
    XML exists";
  - add missing XML hard-error test whose message names both expected
    `Config.xml` paths and remediation, and asserts no USB/main flash calls;
  - add SHA/name mismatch tests and a developer override test for
    `--allow-unverified-filterdata`;
  - add `--help` assertions that V3.5 advertises XML FilterData defaults and
    `hfd-pz`;
  - keep `--info-only`, `--finalize-only`, explicit route, and profile
    passthrough coverage.
- `tests/hardware/test_live_state_transitions.py`
  - update V3.5/current expected preset filename fallbacks from capture sidecars
    to XML-derived V3.5 default names for both A and B; keep historical tests
    clearly version-scoped.
- Shared release-wrapper compatibility:
  - run or add coverage for `tests/sim/test_dlcp_v31_release_flash.py`,
    `tests/sim/test_dlcp_v32_release_flash.py`,
    `tests/sim/test_dlcp_v33_release_flash.py`, and
    `tests/sim/test_dlcp_v34_release_flash.py` so capture forwarding and
    missing-capture warnings remain unchanged for older wrappers.

### Work Unit 7: Update Docs

- `README.md`: replace local `.bin/.json` capture preparation and warning text
  with XML default inputs, exact expected paths, how to populate/symlink the
  ignored local FilterData tree, the new hard-error/no-unbaked-fallback
  behavior, and the fact that `.bin/.json` captures are no longer required for
  the default V3.5 CLI path.
- `AGENTS.md`: update V3.5 release ceremony, source map, CLI test description,
  default XML paths, expected SHA/name gates, and ignored artifact setup.
- `docs/HARDWARE_TEST.md`: update current V3.5 filename expectations to v5/v8
  and mark any v7 references as historical V3.2/V3.4/capture-era material.
- `docs/SPEC_V35_FILTERDATA_XML_BAKING.md`: keep as source spec; no need to
  change unless implementation evidence reveals a spec correction.
- Do not edit historical V3.1/V3.2 runbooks except if a shared wording becomes
  false for their wrappers.

## Likely Files

Code:

- `src/dlcp_fw/paths.py`
- `src/dlcp_fw/flash/filterdata_xml.py`
- `src/dlcp_fw/flash/dlcp_main_flash.py`
- `src/dlcp_fw/flash/dlcp_release_flash_common.py`
- `src/dlcp_fw/flash/dlcp_v35_release_flash.py`
- `scripts/dlcp_filterdata_xml_to_bin.py`
- dependency metadata/lockfile only if `defusedxml` is added

Tests:

- `tests/sim/test_filterdata_xml_to_bin.py`
- `tests/sim/test_dlcp_main_flash_capture_overlay.py`
- `tests/sim/test_dlcp_v35_release_flash.py`
- `tests/sim/test_dlcp_v31_release_flash.py`
- `tests/sim/test_dlcp_v32_release_flash.py`
- `tests/sim/test_dlcp_v33_release_flash.py`
- `tests/sim/test_dlcp_v34_release_flash.py`
- `tests/hardware/test_live_state_transitions.py`

Docs:

- `README.md`
- `AGENTS.md`
- `docs/HARDWARE_TEST.md`
- this IMPL for post-implementation evidence

No firmware HEX, assembly, XML, `.bin`, or `.json` outputs should be modified.

## Test Plan

Focused first:

```bash
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_filterdata_xml_to_bin.py \
  tests/sim/test_dlcp_v35_release_flash.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_main_flash_capture_overlay.py \
  tests/sim/test_dlcp_v31_release_flash.py \
  tests/sim/test_dlcp_v32_release_flash.py \
  tests/sim/test_dlcp_v33_release_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py
```

Release-path slice:

```bash
.venv_ep0/bin/python -m pytest -q -n 8 \
  tests/sim/test_v35_v173_release_builders.py \
  tests/sim/test_dlcp_v35_release_flash.py \
  tests/sim/test_firmware_version_label.py::test_v35_usb_and_eeprom_version_match_release_identity \
  tests/sim/test_v172_v33_diag_identity.py::test_v35_cmd25_identity_handler_emits_16bit_revision_nibbles \
  tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_diag_ok_title_shows_visible_main_identity \
  tests/sim/test_ram_bank_safety.py::test_current_targets_pass_ram_bank_safety_checker \
  tests/sim/test_ram_bank_safety.py::test_v34_v173_targets_are_registered
```

Full simulator gate if focused tests pass:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Static artifact check:

```bash
git status --short
find artifacts/LX521.4 -type f \( -name '*.bin' -o -name '*.json' \) -print
```

Use explicit before/after filesystem inventories or checksums for
`artifacts/LX521.4`; do not rely on `git status` for ignored files. Confirm no
generated `artifacts/LX521.4/LX521.4_22MG10F-v8.{bin,json}` or other new
`.bin/.json` files were created by tests or preflight commands.

Optional manual preflight, no USB writes:

```bash
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --left --preflight-only
```

Run hardware gates only if the user explicitly asks and live hardware is
connected; implementation itself does not require flashing.

## Deployment And Smoke Plan

No deployment or hardware flash is part of the implementation task. This is a
local tooling/docs/test change.

If the user later wants live validation, use the README-approved operator flow:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --path "$LEFT_HID" --left
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --path "$RIGHT_HID" --right
```

Then run post-flash probes from README:

```bash
.venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$LEFT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$RIGHT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$LEFT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$RIGHT_HID" --info-only
```

No-deploy criteria:

- any focused test failure;
- generated `.bin/.json` artifacts appear unexpectedly;
- v5/v8 XML SHA anchors do not match the spec;
- default V3.5 XML name/SHA verification can be bypassed without explicit
  `--allow-unverified-filterdata`;
- preflight output does not show XML sources and `hfd-pz` mode;
- old unbaked-capture warning still appears in V3.5 default path.

## Rollback And Compatibility

Rollback is straightforward: restore V3.5 wrapper to capture defaults and keep
the lower-level `--capture-a/--capture-b` path untouched. Because the
implementation does not alter firmware images or XML content, rollback is only
Python/docs/test code.

Compatibility requirements:

- V3.1/V3.2/V3.3/V3.4 wrappers must continue their old capture behavior unless
  explicitly migrated later.
- `dlcp_main_flash.py --capture-a/--capture-b` must keep working for manual
  debug, older wrappers, hardware-loop workflows, and tests.
- Existing local `.bin/.json` files must not be deleted or rewritten.
- Generic lower-level `dlcp_main_flash.py --filterdata-*` may support
  noncanonical XML for manual/debug use, but the V3.5 wrapper default must
  enforce expected names and SHA anchors unless the explicit unverified override
  is present.

## Risks And Assumptions

- v8 has no existing captured `.bin` fixture. The release default relies on the
  `hfd-pz` SHA anchor and semantic XML conversion. The V3.5 wrapper must make
  that SHA a runtime gate, not just a printed value.
- The XML file does not expose a project display name; deriving it from the
  FilterData directory name is required and must be tested.
- `artifacts/LX521.4` is ignored/local. Tests that require those fixtures should
  skip with explicit local-fixture reasons; V3.5 default-path unit tests must
  use monkeypatched temp XML fixtures so clean checkouts still test behavior.

## Acceptance Criteria

- `scripts/dlcp_v35_release_flash.py --left --preflight-only` builds both
  overlays from v5/v8 XML in memory, verifies expected names/SHA values before
  USB access, and prints XML source/mode/name/base/SHA.
- V3.5 wrapper no longer forwards `--capture-a/--meta-a/--capture-b/--meta-b`
  by default.
- Missing `.bin/.json` captures do not affect V3.5 defaults.
- Missing default XML inputs, malformed XML, and hash/name mismatches fail
  before any USB access with actionable errors.
- No `.bin` or `.json` artifacts are created by V3.5 release flashing.
- v5 `hfd-pz` table matches existing v5 capture; v8 `hfd-pz` table has the
  specified SHA when local fixtures are present, and always-on synthetic XML
  tests cover the conversion/overlay path in clean checkouts.
- Lower-level capture overlay tests still pass.
- README, AGENTS, and HARDWARE_TEST describe the new V3.5 XML-native default
  accurately; current hardware filename gates expect A v5 and B v8.
- Focused and release-path tests pass; full simulator gate passes or any
  unrun/blocked broader gate is explicitly documented.

## Post-Implementation Evidence

Implementation status: complete and verified on 2026-06-26.

Actual files changed:

- `src/dlcp_fw/paths.py`: added canonical LX521 FilterData path/name/SHA
  constants for V3.5.
- `src/dlcp_fw/flash/filterdata_xml.py`: hardened FilterData XML parsing,
  added size/count/numeric guards, and kept table generation in memory.
- `src/dlcp_fw/flash/dlcp_main_flash.py`: added `--filterdata-a`,
  `--filterdata-b`, `--filterdata-mode`, expected name/SHA guard args,
  directory-or-`Config.xml` resolution, XML overlay loading, pre-USB
  verification, source-aware preflight output, and repo-relative/external path
  display.
- `src/dlcp_fw/flash/dlcp_release_flash_common.py`: added XML-default wrapper
  forwarding while preserving V3.1-V3.4 capture behavior.
- `src/dlcp_fw/flash/dlcp_v35_release_flash.py`: switched V3.5 defaults to v5
  and v8 FilterData XML in `hfd-pz` mode, exposed default preset names, and
  passed expected hashes.
- `tests/sim/test_filterdata_xml_to_bin.py`: replaced local-artifact-only
  tests with synthetic always-on coverage plus guarded local v5/v8 anchors.
- `tests/sim/test_dlcp_main_flash_capture_overlay.py`: added XML overlay,
  path-resolution, verification, help, preflight, no-USB, and no-sidecar tests.
- `tests/sim/test_dlcp_v35_release_flash.py`: updated V3.5 wrapper tests for
  XML defaults, hard missing-XML errors, unverified override, help, and
  preflight behavior.
- `tests/hardware/test_live_state_transitions.py`: moved current front-panel
  expected names to V3.5 XML defaults while leaving historical V3.2 gates
  capture-based.
- `README.md`, `AGENTS.md`, `docs/HARDWARE_TEST.md`: documented the XML-native
  V3.5 flow, local FilterData setup/remediation, current v5/v8 expectations,
  and historical v7 scoping.

Actual test commands/results:

```bash
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_filterdata_xml_to_bin.py \
  tests/sim/test_dlcp_v35_release_flash.py \
  tests/sim/test_dlcp_main_flash.py \
  tests/sim/test_dlcp_main_flash_capture_overlay.py \
  tests/sim/test_dlcp_v31_release_flash.py \
  tests/sim/test_dlcp_v32_release_flash.py \
  tests/sim/test_dlcp_v33_release_flash.py \
  tests/sim/test_dlcp_v34_release_flash.py
```

Result: `120 passed, 3 warnings in 0.69s`.

```bash
.venv_ep0/bin/python -m pytest -q -n 8 \
  tests/sim/test_v35_v173_release_builders.py \
  tests/sim/test_dlcp_v35_release_flash.py \
  tests/sim/test_firmware_version_label.py::test_v35_usb_and_eeprom_version_match_release_identity \
  tests/sim/test_v172_v33_diag_identity.py::test_v35_cmd25_identity_handler_emits_16bit_revision_nibbles \
  tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_diag_ok_title_shows_visible_main_identity \
  tests/sim/test_ram_bank_safety.py::test_current_targets_pass_ram_bank_safety_checker \
  tests/sim/test_ram_bank_safety.py::test_v34_v173_targets_are_registered
```

Result: `24 passed in 7.26s`.

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Result: `2039 passed, 2 skipped, 4 xfailed, 7 warnings in 942.00s`.

Real default V3.5 wrapper preflight, no USB writes:

```bash
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --left --preflight-only
```

Result: passed. Output showed `preflight: OK`, target firmware `3.5`, revision
`0x90`, preset A source
`artifacts/LX521.4/FilterData/LX521.4 22MG10F-v5/Config.xml`, preset B source
`artifacts/LX521.4/FilterData/LX521.4 22MG10F-v8/Config.xml`, `hfd-pz` mode for
both, flash bases `0x5600`/`0x4C00`, and the expected v5/v8 SHA256 anchors.

Generated artifact check:

Before and after the required tests, this command:

```bash
find artifacts/LX521.4 -type f \( -name '*.bin' -o -name '*.json' \) -print | sort
```

returned only the pre-existing historical capture files:

```text
artifacts/LX521.4/LX521.4_22MG10F-v5.bin
artifacts/LX521.4/LX521.4_22MG10F-v5.json
artifacts/LX521.4/LX521.4_22MG10F-v7.bin
artifacts/LX521.4/LX521.4_22MG10F-v7.json
```

No `LX521.4_22MG10F-v8.bin`, `LX521.4_22MG10F-v8.json`, or other generated
`.bin/.json` files were created by the V3.5 XML path or tests.

Deploy/smoke evidence: no deploy and no hardware flash were run; the user did
not request live flashing for this goal. The verified output is local
tooling/docs/tests only.

Unresolved low-risk issues: none.

## Reviewer Findings And Iteration History

Review gate: 8 independent reviewer passes completed for draft 1, followed by
8 affected-role re-reviews on draft 2. The re-review reported zero High and
zero Medium findings. Draft 3 incorporates the remaining Low cleanup items.

Findings ledger:

| Role | Severity | Issue | Disposition | Changed section |
|---|---|---|---|---|
| Simplicity/scope | High | Mandatory tests depended on ignored local LX521 artifacts. | Resolved: always-on synthetic/temp XML tests; local anchors skip with explicit reason. | Work Units 6, Test Plan, Acceptance Criteria |
| Simplicity/scope | High | `git status` cannot prove ignored `.bin/.json` non-creation. | Resolved: automated temp snapshot tests and explicit filesystem inventory. | Work Unit 6, Test Plan |
| Simplicity/scope | Medium | Shared release wrapper changes lacked V3.1-V3.4 regression gates. | Resolved: added older wrapper tests to focused gate. | Work Unit 6, Test Plan |
| Simplicity/scope | Medium | V3.5 B v8 docs/hardware drift under-scoped. | Resolved: added hardware work unit and HARDWARE_TEST docs update. | Work Units 5, 7 |
| Simplicity/scope | Medium | Moving converter to `dlcp_fw.presets` was extra scope. | Resolved: keep converter in `flash/` for this implementation. | Work Unit 1, Likely Files |
| Correctness/contract | High | Hardware filename gates still expected B v7/current V3.2 sidecars. | Resolved: V3.5 helper map and current hardware gates must use v5/v8. | Work Units 4, 5, 6, 7 |
| Correctness/contract | Medium | No automated no-generated-artifact test. | Resolved. | Work Unit 6 |
| Correctness/contract | Medium | Directory-form FilterData defaults not pinned. | Resolved: directory-aware resolver/check and directory/file tests. | Work Units 3, 4, 6 |
| Correctness/contract | Medium | Shared-wrapper compatibility not directly tested. | Resolved. | Work Unit 6, Test Plan |
| Ops/tests/deploy | High | Hardware/deploy validation tied to V3.2/v7. | Resolved: split historical gates from current V3.5 gates. | Work Unit 5 |
| Ops/tests/deploy | Medium | Ignored artifact outputs not covered by status. | Resolved. | Work Unit 6, Test Plan |
| Ops/tests/deploy | Medium | Standard sim gate risked local-fixture dependency. | Resolved. | Work Unit 6 |
| UX/API-consumer | Medium | Missing XML remediation under-specified. | Resolved: README/AGENTS remediation and error-message tests. | Work Units 6, 7 |
| UX/API-consumer | Medium | CLI help could remain stale. | Resolved: parameterized help and help tests. | Work Units 4, 6 |
| Security/privacy | High | Canonical V3.5 defaults trusted ignored XML without SHA gate. | Resolved: expected name/SHA runtime gate before USB. | Work Units 3, 4, 6 |
| Security/privacy | Medium | XML parser lacked hostile-input hardening. | Resolved: hardened parser, limits, and tests. | Work Units 1, 6 |
| Security/privacy | Medium | Error tests did not prove no USB touch. | Resolved: no-enumeration/open/switch/flash assertions. | Work Unit 6 |
| Performance/reliability | High | Directory defaults could be rejected by file-only validation. | Resolved: directory-aware wrapper validation. | Work Units 3, 4, 6 |
| Performance/reliability | Medium | Preflight evidence not pinned by tests. | Resolved: stdout assertions added. | Work Unit 6 |
| Data/migration compatibility | High | Preset-B name migration incomplete. | Resolved: V3.5 A/B helper map and hardware docs/tests. | Work Units 4, 5, 7 |
| Data/migration compatibility | Medium | XML path compatibility under-tested. | Resolved: directory and `Config.xml` tests. | Work Unit 6 |
| Maintainability/observability | High | Fixture ownership unresolved. | Resolved: synthetic always-on tests plus local-anchor skips. | Work Unit 6 |
| Maintainability/observability | Medium | Live hardware observability still v7/V3.4 oriented. | Resolved: current V3.5 v5/v8 gates; historical wording scoped. | Work Units 5, 7 |

Remaining Low findings:

- None blocking. The re-review Low findings were closed in draft 3 by making
  the artifact `find` recursive, defining concrete XML size/count/numeric
  bounds, requiring external absolute path redaction tests, and requiring help
  hygiene for lower-level expected SHA/name args.

Final review summary: approved for implementation with no unresolved High or
Medium findings. Implementation remains intentionally deferred.
