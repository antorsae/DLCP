# Rust PIC18 Silicon Fidelity Closure - Implementation Plan

Date: 2026-05-03
Status: complete; verified 2026-05-03
Parent spec: `docs/SIM_REWRITE_RUST_SPEC.md` section 11c
Target crates: `crates/dlcp-sim/`, `crates/dlcp-sim-py/`

## Goal

Close the PIC18 silicon-fidelity gaps identified in
`docs/SIM_REWRITE_RUST_SPEC.md` section 11c without regressing the DLCP
firmware simulation suite.

This is not a rewrite of the Rust simulator. It is a sequence of
focused, test-first fidelity upgrades. Each upgrade must be small enough
to review, must have a focused Rust test, and must preserve or explicitly
reclassify existing DLCP tests.

## Inputs

Use these as the authoritative references:

- MAIN MCU datasheet: `firmware/reference/39632e.pdf`
- MAIN line-stable citation companion: `firmware/reference/39632e.md`
- CONTROL MCU datasheet: `firmware/reference/40001303h.pdf`
- CONTROL line-stable citation companion: `firmware/reference/40001303h.md`
- Design spec: `docs/SIM_REWRITE_RUST_SPEC.md` section 11c
- Active migration ledger: `docs/SIM_REWRITE_RUST_PROGRESS.md`
- Existing implementation playbook: `docs/SIM_REWRITE_AGENT_INSTRUCTIONS.md`

## Non-Negotiable Rules

1. Every fidelity item starts with a focused failing or gap-pinning Rust
   test. Do not implement first and add a broad chain test later.
2. A test must cite the datasheet line, local spec section, or an
   explicitly documented DLCP-local contract.
3. Datasheet behavior wins over gpsim for silicon-focused tests. gpsim
   remains useful as a regression oracle for existing DLCP behavior, not
   as the final authority for known silicon gaps.
4. If a DLCP test breaks, investigate before changing assertions. The
   break must be classified as `sim bug`, `DLCP test bug`,
   `intentional divergence`, or `firmware behavior exposed`, matching
   parent spec section 11c.
5. Any xfail, skip, compatibility shim, or temporary old-behavior mode
   must name the removal condition in the test or ledger note.
6. Do not hand-edit status markers in `docs/SIM_REWRITE_RUST_PROGRESS.md`.
   If these tasks are scheduled there, use `scripts/sim_rewrite_next.py`
   for status transitions.

## Implementation Shape

Prefer this loop for each task:

1. Read the relevant datasheet section and source module.
2. Add or tighten the narrow focused test.
3. Run only that focused test and confirm it fails for the intended
   reason, unless the test is a guard for existing behavior.
4. Implement the simulator change in the smallest owner module.
5. Run the focused test.
6. Run the crate-level Rust regression gate.
7. Run the relevant migrated pytest subset.
8. If pytest breaks, triage and record the classification.
9. Update this doc or parent section 11c if the implementation changes
   the contract.

Minimum command pattern:

```bash
cargo test -p dlcp-sim --release <focused-filter>
cargo test -p dlcp-sim --release
.venv_ep0/bin/python -m pytest -q <relevant-tests>
```

Use the current backend policy for pytest. At this branch state, plain
pytest defaults to the Rust backend for migrated tests; use
`DLCP_SIM_BACKEND=dual` only where the migration notes say dual-run is
still the intended gate.

## Human-Readable Work Ledger

This ledger is intentionally not consumed by `sim_rewrite_next.py`.
When you want these scheduled by the existing automation, copy the
selected entries into `docs/SIM_REWRITE_RUST_PROGRESS.md` with the same
fixed shape, then let `scripts/sim_rewrite_next.py` own status changes.

Completion note (2026-05-03): all section-11c fidelity items FID-01
through FID-16 are closed by focused Rust tests with datasheet/spec
citations.  Integrated gates passed with `cargo test -p dlcp-sim
--release`, `cargo build --release -p dlcp-sim-py && bash
crates/dlcp-sim-py/build.sh`, and the current Rust-backend pytest split
gate:

- `DLCP_SIM_BACKEND=rust .../analysis/.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -m "not slow"` -> `582 passed, 39 skipped, 1 xfailed` in `8.80s`
- `DLCP_SIM_BACKEND=rust .../analysis/.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -m slow` -> `204 passed, 260 skipped, 7 xfailed` in `259.72s`

Regression classification: FID-14 initially broke multicore and
PyO3-facade chain tests by exposing an old simulator shortcut where
tests/factories raw-wrote `PORTA`/`PORTC` to mean "buttons released".
Classification: `DLCP test bug` / facade-harness bug.  Resolution:
the GPIO model now keeps external pin level separate from PORT readback,
and tests/factories use `set_pin_high` on the six active-low CONTROL
button pins so released levels survive TRIS/ANSEL refreshes.  No new
skips, xfails, or compatibility shims were added.

### Wave A - Core Foundations

- [done] FIDA.1 Centralize full HEX image loading into `Core`
  - covers: FID-04
  - verify: `cargo test -p dlcp-sim --release full_hex_loader_populates_config_and_user_id`
  - follow-up verify: `cargo test -p dlcp-sim --release config::tests`
    and `cargo test -p dlcp-sim --release hex::tests`
  - artifact: shared loader helper used by Rust tests and PyO3 chain builders
  - notes: all full-firmware constructors must populate flash, EEPROM,
    CONFIG, and USER_ID in one code path.

- [done] FIDA.2 Fail loudly when XINST is enabled
  - covers: FID-05
  - verify: `cargo test -p dlcp-sim --release --test isa_parity xinst_unsupported_config_fails_loudly`
  - artifact: executor/config error path plus focused test
  - notes: product firmware uses XINST=0; silent legacy execution under
    XINST=1 is the bug.

- [done] FIDA.3 Enforce PIC18F2455 24 KiB implemented flash semantics
  - covers: FID-06
  - verify: `cargo test -p dlcp-sim --release --test isa_parity pic2455_top_8k_uses_unimplemented_memory_semantics`
  - artifact: variant-aware flash fetch/table-read bounds
  - notes: host buffers may stay 32 KiB, but 2455 silicon must not
    execute or table-read seeded bytes above 0x5FFF.

- [done] FIDA.4 Wire DEVID reads and protection-bit policy
  - covers: FID-16
  - verify: `cargo test -p dlcp-sim --release --test isa_parity tblrd_devid_and_protection_policy`
  - artifact: per-variant DEVID constants plus documented
    code-protect/write-protect behavior
  - notes: if protection bits stay unimplemented, the test must assert
    the explicit unsupported or no-op policy.

### Wave B - Reset, Power, and Clock

- [done] FIDB.1 Complete variant reset SFR tables
  - covers: FID-07
  - verify: `cargo test -p dlcp-sim --release reset::tests`
  - artifact: variant-specific POR/BOR/MCLR/WDT/RESET/stack reset tables
  - notes: remove gpsim-pinned values where the datasheet is
    unambiguous, or document an intentional exception in parent spec
    section 11c.

- [done] FIDB.2 Add WDT counter and running-mode timeout reset
  - covers: FID-02
  - verify: `cargo test -p dlcp-sim --release wdt_running_timeout_resets_and_clrwdt_clears`
  - artifact: WDT peripheral state and reset integration
  - notes: driven by CONFIG2H.WDTEN/WDTPS and WDTCON.SWDTEN.

- [done] FIDB.3 Implement Sleep/Idle CPU halt and wake behavior
  - covers: FID-02, FID-13
  - verify: `cargo test -p dlcp-sim --release sleep_idle_wake_tests`
  - artifact: core run-state plus scheduler support for sleeping cores
  - notes: sleeping CPU does not fetch instructions; allowed
    peripherals and WDT may continue according to mode.

- [done] FIDB.4 Replace fixed oscillator stub with config-driven clock state
  - covers: FID-08
  - verify: `cargo test -p dlcp-sim --release --test peripheral_osc_parity`
  - artifact: oscillator state machine consumed by scheduler and
    peripheral timing
  - notes: current DLCP configs must still resolve to CONTROL=16 and
    MAIN=12 universal ticks per Tcy unless a source comment/spec proves
    otherwise.

### Wave C - Nonvolatile Memory Writes

- [done] FIDC.1 Commit TBLWT holding registers through EECON1.WR
  - covers: FID-03
  - verify: `cargo test -p dlcp-sim --release --test peripheral_eeprom_parity flash_config_user_id_long_write`
  - artifact: flash/config/user-id write support, separate from data EEPROM
  - notes: model EEPGD/CFGS/FREE/WREN/WR/RD, unlock, holding-register
    block size, and 0->1 programming limits.

### Wave D - Peripheral Breadth

- [done] FIDD.1 Complete timer model
  - covers: FID-09
  - verify: `cargo test -p dlcp-sim --release --test peripheral_timers_parity`
  - artifact: Timer1, Timer2, Timer0/3 latches, external clock hooks
  - notes: keep DLCP Timer0/Timer3 paths green before broadening.

- [done] FIDD.2 Complete ADC timing and channel model
  - covers: FID-12
  - verify: `cargo test -p dlcp-sim --release --test peripheral_adc_parity`
  - artifact: ACQT/ADCS timing, channel mux, Vref/FVR, sleep/FRC path
  - notes: `set_an0_sample` may remain as test injection above the
    silicon model.

- [done] FIDD.3 Tighten EUSART timing and error paths
  - covers: FID-11
  - verify: `cargo test -p dlcp-sim --release --test peripheral_eusart_parity`
  - artifact: TXIF delay, FERR, WUE, SENDB/break, 9-bit semantics,
    explicit sync-mode policy
  - notes: current 31,250 baud current-loop behavior is the regression
    guard.

- [done] FIDD.4 Define MSSP unsupported modes and add pin-level I2C gaps
  - covers: FID-10
  - verify: `cargo test -p dlcp-sim --release --test peripheral_mssp_parity`
  - artifact: SPI/slave/10-bit/general-call policy or implementation,
    bus collision and clock-stretch behavior
  - notes: DLCP TAS3108/SRC4382 virtual slaves must remain covered.

### Wave E - Pins and Peripheral Stubs

- [done] FIDE.1 Implement GPIO electrical semantics and general pin propagation
  - covers: FID-14
  - verify: `cargo test -p dlcp-sim --release --test peripheral_gpio_parity`
  - artifact: PORT/TRIS/LAT semantics, analog mux effects, INTx/KBI,
    MCLR, RA0 wake, RC4/RC5 USB sharing, `couple_pin`
  - notes: this is likely to expose old tests that wrote PORT/LAT as
    pure memory; triage before changing assertions.

- [done] FIDE.2 Audit missing peripheral SFRs and add explicit stub policies
  - covers: FID-15
  - verify: `cargo test -p dlcp-sim --release missing_peripheral_stub_policy`
  - artifact: CCP/ECCP/PWM, comparators/CVREF, HLVD, PSP/SPP, FVR policy
  - notes: a read-as-zero/no-op stub is acceptable only when tested and
    documented as out of DLCP scope.

### Wave F - USB-SIE and HID

- [done] FIDF.1 Implement USB-SIE SFRs and BDT ownership model
  - covers: FID-01
  - verify: `cargo test -p dlcp-sim --release --test peripheral_usbsie_parity usb_sfr_bdt_state_machine`
  - artifact: 2455-only USB state for UCON/UCFG/UADDR/USTAT/UIR/UIE/UEPn
  - notes: do this before HID command dispatch so endpoint semantics are
    testable in isolation.

- [done] FIDF.2 Implement DLCP HID command path
  - covers: FID-01
  - verify: `cargo test -p dlcp-sim --release --test peripheral_usbsie_parity dlcp_hid_commands`
  - artifact: HID-only commands `cmd 0x43` (flash/EEPROM memread) and
    `cmd 0x44` (V3.2 Tier-1 diag snapshot), plus filename A/B upload
    routing during DSP coefficient transfer.  Dispatched from
    `flow_hid_command_dispatch_*` (e.g. `dlcp_main_v32.asm:911-918`,
    `9701-9794`).
  - notes: BF chain UART commands (`cmd 0x20`/`0x21`/`0x22`, decoded
    in `flow_main_uart_service` at `dlcp_main_v32.asm:2225-2233`) are
    a different command space and are covered by the existing chain
    regression tests, NOT by FIDF.2.  Full HID enumeration stays out
    of scope unless a DLCP tool needs it; provide a host-injection
    helper for tests.

### Wave G - Campaign Gate

- [done] FIDG.1 Run integrated silicon-fidelity regression gate
  - covers: FID-01 through FID-16
  - verify: `cargo test -p dlcp-sim --release && .venv_ep0/bin/python -m pytest tests/sim -q`
  - artifact: regression note in the relevant ledger/progress doc
  - notes: if runtime is too high, use the current phase-4 split gate,
    but record the exact commands and outcomes.

## Detailed Implementation Guidance

### FIDA.1 - Central HEX Image Loading

Current problem: many builders copy only flash and EEPROM into `Core`,
leaving CONFIG at `Config::from_bytes([0; 14])` and USER_ID at 0xFF.
That makes config-dependent peripherals impossible to make faithful.

Implementation:

1. Add a single helper, for example:
   ```rust
   pub struct CoreLoadOptions {
       pub bake_goto_app_entry: Option<u32>,
       pub bake_goto_irq_vector: Option<u32>,
       pub preserve_default_config: bool,
   }

   pub fn core_from_hex_image(
       variant: Variant,
       image: &HexImage,
       options: CoreLoadOptions,
   ) -> Core
   ```
2. The helper must:
   - construct `Core::new(variant)`,
   - copy flash,
   - copy every EEPROM byte into the EEPROM peripheral,
   - set `core.config = Config::from_bytes(image.config)`,
   - set `core.user_id = image.user_id`,
   - apply optional boot/IRQ vector trampolines after flash copy.
3. Replace duplicated builder code in:
   - `crates/dlcp-sim/tests/isa_parity.rs`
   - `crates/dlcp-sim/tests/multicore_parity.rs`
   - `crates/dlcp-sim-py/src/lib.rs`
4. If a test truly depends on all-zero CONFIG, make that override
   explicit in the test with a comment explaining why silicon defaults
   are not wanted.

Focused tests:

- Load V1.71 and V3.2 hex images and assert `core.config.raw()` equals
  `HexImage.config`.
- Assert TBLRD from `0x300000..0x30000D` returns those bytes.
- Assert TBLRD from `0x200000..0x200007` returns USER_ID bytes.

Regression risk:

- STVREN default changes can alter stack-overflow tests. If so, update
  tests to set the config they mean rather than relying on constructor
  defaults.

### FIDA.2 - XINST

Current problem: the parser exposes `Config::xinst()`, but the executor
does not reject or implement extended mode.

Implementation:

1. Add an executor error variant such as:
   ```rust
   UnsupportedConfig(&'static str)
   ```
2. At the start of `exec::step` or at the core construction boundary,
   reject `core.config.xinst() == true`.
3. Make the error message include `XINST=1`.
4. Do not partially emulate indexed literal offset mode unless the full
   extended instruction behavior is implemented.

Focused test:

- Build a tiny core with CONFIG4L.XINST set.
- Seed flash with a normally valid legacy instruction.
- Assert stepping returns the unsupported-XINST error before any state
  mutation.

### FIDA.3 - PIC18F2455 24 KiB Flash Semantics

Current problem: the sim stores 32 KiB for both variants and fetches
from the backing buffer. The PIC18F2455 implements 24 KiB.

Implementation:

1. Add `Variant::implemented_program_memory_bytes()`.
2. Keep the host storage size if needed for seeded images, but route all
   instruction fetch and TBLRD through a helper:
   ```rust
   fn read_program_byte_for_variant(core: &Core, addr: u32) -> u8
   ```
3. For PIC18F2455 addresses `0x6000..0x7FFF`, return the datasheet
   unimplemented-memory value, not the host buffer byte.
4. Decide and document whether PC fetch above 0x5FFF should:
   - execute as reads of zero words, or
   - raise `PcOutOfBounds`.

Preferred DLCP-safe choice: reads above implemented flash return zero,
matching program-memory gap semantics, while a PC beyond the simulator
host buffer remains `PcOutOfBounds`.

Focused test:

- Seed nonzero opcode bytes at 0x6000 on a 2455 core.
- Set PC to 0x6000.
- Step once and assert the seeded opcode was not executed.
- Repeat with K20 and assert 0x6000 remains normal executable flash.

### FIDA.4 - DEVID and Protection Policy

Current problem: TBLRD from DEVID returns zero; code-protect and
write-protect bits are parsed but not consumed.

Implementation:

1. Locate DEVID values in the local datasheets or a checked-in
   Microchip include source. Add constants with a citation.
2. Route TBLRD `0x3FFFFE..0x3FFFFF` to the per-variant constants.
3. For CONFIG5..CONFIG7:
   - either implement protection effects for table read/write, or
   - document that protection bits are parsed but not enforced in the
     simulator, and add tests pinning that explicit policy.

Focused tests:

- DEVID TBLRD returns the variant constant.
- A protection-bit-configured core follows the documented policy.

### FIDB.1 - Reset Tables

Current problem: K20 POR is broader but includes gpsim-pinned
deviations; 2455 POR/BOR/MCLR/WDT/RESET coverage is targeted.

Implementation:

1. Convert datasheet reset tables into static data with one row per SFR
   and columns for:
   - POR/BOR,
   - MCLR/WDT/RESET/stack,
   - WDT or interrupt wake.
2. Represent table symbols explicitly:
   - `0`,
   - `1`,
   - `u` preserve,
   - `x` unknown with deterministic simulator policy,
   - `-` unimplemented read-as-zero,
   - `q` config/dynamic-dependent.
3. Keep variant-specific tables separate. Do not use K20 rows as a
   fallback for 2455.
4. Resolve `q` rows from loaded CONFIG where possible:
   - MCLRE,
   - PBADEN,
   - oscillator pin mode,
   - USB pin sharing where relevant.
5. Keep any gpsim-compatibility exception in a named table with a parent
   spec reference. Do not hide it in inline comments only.

Focused tests:

- One representative test per reset source and variant.
- Specific assertions for previously known gaps: 2455 OSCCON/TRIS/USB
  defaults and K20 TRISA/ANSELH CONFIG-dependent rows.

### FIDB.2/FIDB.3 - WDT, Sleep, and Idle

Current problem: `CLRWDT` and `SLEEP` update RCON only. The CPU keeps
executing.

Implementation:

1. Add core run state:
   ```rust
   enum RunState {
       Running,
       Sleep,
       Idle,
       HeldInReset,
   }
   ```
2. Move current `mclr_held` behavior into or alongside this state so
   reset-held cores do not receive normal step events.
3. Add a WDT peripheral or power module with:
   - enable source: CONFIG2H.WDTEN or WDTCON.SWDTEN,
   - postscale: CONFIG2H.WDTPS,
   - counter clear on CLRWDT, SLEEP, and reset,
   - running-mode timeout -> WDT reset,
   - sleep/idle timeout -> wake, not reset.
4. Update scheduler behavior:
   - Running cores schedule instruction-complete events.
   - Sleep cores do not schedule instruction fetch.
   - Idle cores do not fetch instructions but selected peripherals tick.
5. Implement interrupt wake:
   - On eligible interrupt flag, leave Sleep/Idle.
   - Execute the instruction after SLEEP before vectoring when the
     datasheet requires that sequence.
6. Preserve RCON.TO/PD semantics for CLRWDT, SLEEP, WDT reset, and WDT
   wake.

Focused tests:

- `CLRWDT` clears WDT and sets RCON.TO/PD.
- WDT timeout in Running applies WDT reset.
- `SLEEP` with IDLEN=0 stops instruction execution until wake.
- `SLEEP` with IDLEN=1 stops CPU while allowing a timer/interrupt path
  that is documented to continue.

Regression risk:

- Existing tests may accidentally step past SLEEP today. If they break,
  classify whether the test was relying on the old shortcut or whether
  firmware should never sleep on that path.

### FIDB.4 - Oscillator

Current problem: oscillator behavior is a fixed conversion factor plus
no-op SFR hooks.

Implementation:

1. Add `ClockSource` and `OscState` fields for primary, secondary,
   internal, PLL, and USB clock derivation.
2. Consume loaded CONFIG:
   - FOSC,
   - PLLDIV,
   - CPUDIV,
   - USBDIV,
   - FCMEN,
   - IESO,
   - VREGEN for USB side effects.
3. OSCCON writes must affect:
   - IDLEN,
   - IRCF,
   - SCS,
   - OSTS and IOFS status transitions.
4. PLL enable/ready must include a deterministic delay in simulator
   ticks.
5. The scheduler must ask the core for current ticks-per-Tcy, not call a
   fixed const that ignores oscillator state.

Focused tests:

- V1.71 and V3.2 loaded configs produce the current known tick factors.
- SCS switch changes ticks-per-Tcy after the documented ready delay.
- IOFS/OSTS bits transition only through the oscillator state machine.

### FIDC.1 - Flash/Config/User-ID Long Writes

Current problem: TBLWT stages into a holding buffer, but EECON1.WR only
commits data EEPROM writes.

Implementation:

1. Rename or split the EEPROM peripheral if needed. A better long-term
   owner is `peripherals/nvm.rs` containing:
   - data EEPROM storage,
   - flash write holding buffer commit,
   - config byte write,
   - user ID write.
2. Preserve the existing data EEPROM tests.
3. Enforce the EECON2 unlock window for both data EEPROM and program
   memory writes. The current data EEPROM model acknowledges it does not
   enforce the five-instruction window; close that gap here or document
   a separate task.
4. For program flash:
   - use TBLPTR upper bits to select flash/config/user-id,
   - commit the whole write block for flash,
   - write config bytes one at a time if that is the variant behavior,
   - reset holding bytes to 0xFF after write/reset,
   - enforce 0->1 programming limits unless an erase occurred.
5. Implement FREE erase behavior if any DLCP updater path needs it.

Focused tests:

- TBLWT alone does not mutate flash.
- Correct unlock + WR commits staged bytes.
- Bad unlock sets WRERR and does not commit.
- CONFIG and USER_ID writes update TBLRD-visible storage.

### FIDD.1 - Timers

Implementation:

1. Add Timer1 and Timer2 state structs. Keep Timer0/Timer3 code readable;
   do not create one large register soup.
2. Complete Timer0 and Timer3 16-bit read/write latch semantics.
3. Wire `Peripherals::on_sfr_read` through timer read side effects.
4. Add external clock injection hooks for T0CKI and T1OSC/T13CKI.
5. Timer2 must implement PR2 match, postscaler/prescaler, and TMR2IF.
6. Add special-event reset hooks for CCP/ECCP later; stub with an
   explicit API now if useful.

Focused tests:

- 16-bit latch read returns the buffered high byte.
- Timer2 sets TMR2IF on PR2 match.
- External clock injection increments only when configured.

### FIDD.2 - ADC

Implementation:

1. Represent analog inputs separately from RAM/SFR bytes.
2. Decode ADCON0 channel select for each variant.
3. Decode ADCON1/ANSEL/ANSELH analog-vs-digital configuration.
4. Compute acquisition and conversion timing from ADCON2.ACQT/ADCS.
5. Implement Vref/FVR source policy.
6. Model FRC conversion during Sleep if selected.
7. Keep DLCP `set_an0_sample` as an injection convenience by writing the
   analog input source, not by bypassing ADC channel logic.

Focused tests:

- AN0 DLCP threshold path still passes.
- Two different channels return different injected sources.
- ACQT/ADCS changes conversion completion tick.
- Sleep/FRC conversion can wake through ADIF when enabled.

### FIDD.3 - EUSART

Implementation:

1. Add TXIF second-instruction-cycle validity delay.
2. Model RX framing at bit level enough to generate FERR on bad stop bit.
3. Complete OERR behavior tests with FIFO full and CREN toggling.
4. Add WUE wake-up path from Sleep/Idle.
5. Add SENDB/break transmit and receive behavior if any tests need it.
6. Implement full 9-bit TX/RX or reject unsupported combinations with a
   named policy.
7. Synchronous mode may be explicit unsupported unless a DLCP path uses
   it; a no-op that looks like async mode is forbidden.

Focused tests:

- TXIF delay matches datasheet.
- Bad stop bit sets FERR without corrupting unrelated status.
- WUE wakes a sleeping core on start bit.

### FIDD.4 - MSSP

Implementation:

1. Make SSPM mode decoding explicit.
2. For unsupported modes, leave documented SFR behavior intact but do
   not run I2C-master transfers accidentally.
3. Add SPI master/slave only if a DLCP or diagnostic test needs it.
4. For I2C master:
   - model SDA/SCL line state in the pin network,
   - wire clock stretching,
   - wire collision/arbitration loss,
   - model 10-bit addressing and General Call or explicitly reject.
5. Preserve virtual TAS3108 and SRC4382 device behavior.

Focused tests:

- SSPM non-I2C-master does not trigger I2C-master state.
- Clock stretch delays SSPIF/PEN/SEN clear.
- Bus collision sets BCLIF and leaves a recoverable state.

### FIDE.1 - GPIO and Pin Network

Implementation:

1. Add a GPIO peripheral owner if the current memory-only behavior is
   too implicit.
2. Reads from PORTx must reflect pins; writes to LATx/PORTx must affect
   output latch according to PIC18 semantics.
3. TRIS controls whether latch drives the pin or the pin input is read.
4. Analog configuration can force digital read behavior as documented.
5. Implement interrupt-on-change and INT0/1/2 edge detect.
6. Implement MCLR held-low as a pin-level reset condition, not only a
   scheduler pause.
7. Implement general `couple_pin` propagation with deterministic delay.
8. RC4/RC5 must respect USB ownership when USB is enabled.

Focused tests:

- LAT write drives PORT read only when TRIS output.
- External pin injection is visible when TRIS input.
- MCLR low resets/holds the core and release resumes from reset.
- Coupled pin changes propagate exactly once.

### FIDE.2 - Missing Peripheral Stubs

Implementation:

1. Build an SFR coverage table for both variants from the datasheets.
2. Mark every SFR as one of:
   - implemented,
   - explicit no-op/read-as-zero stub,
   - unsupported and erroring on behavior-triggering use,
   - intentionally not represented because the variant lacks it.
3. Start with CCP/ECCP/PWM, comparators/CVREF, HLVD, PSP/SPP, and FVR.
4. Add tests for each stub class. The test can assert read-as-zero, but
   it must name the peripheral and why that is acceptable for DLCP.

Focused tests:

- SFR coverage test fails when a documented SFR is neither implemented
  nor explicitly classified.
- Representative stub reads/writes match the chosen policy.

### FIDF.1/FIDF.2 - USB-SIE and HID

Implementation order:

1. Implement USB SFR masks and reset values:
   - UCON,
   - UCFG,
   - UADDR,
   - USTAT,
   - UIE/UIR,
   - UEIE/UEIR,
   - UEP0..UEP15,
   - frame registers if DLCP-visible.
2. Implement BDT memory behavior:
   - BDnSTAT CPU/SIE ownership,
   - byte count,
   - buffer address,
   - DTS/DTSEN,
   - UOWN clear on transaction completion,
   - USTAT FIFO and TRNIF behavior.
3. Add a test host API, not a full USB host:
   ```rust
   usb.inject_setup(...)
   usb.inject_out(endpoint, bytes)
   usb.take_in(endpoint) -> Vec<u8>
   ```
4. Implement endpoint 0 control transfers enough for DLCP firmware's
   existing handlers.
5. Implement DLCP HID command injection for the HID-only command
   space dispatched from `flow_hid_command_dispatch_*`:
   - `0x43` flash/EEPROM memory read,
   - `0x44` Tier-1 diagnostic snapshot,
   - filename A/B routing during DSP coefficient upload.

   Note: `cmd 0x20` (preset switch), `cmd 0x21` (diagnostic counter
   query), and `cmd 0x22` (reset-cause flags query) are NOT HID
   commands -- they are BF chain frames decoded by
   `flow_main_uart_service` over the 31,250 baud current-loop link
   (see `dlcp_main_v32.asm:2225-2233`).  FIDF.2 must not target
   them; their fidelity is covered by the existing chain
   regression tests (chain_gpsim / multicore_parity).
6. USB reset and suspend/resume must set flags and UADDR behavior per
   datasheet.

Focused tests:

- UCON.USBEN reset/enable changes USB ownership and reset state.
- BDT OUT transaction clears UOWN, updates USTAT, and sets TRNIF.
- Clearing TRNIF advances USTAT FIFO.
- cmd 0x43 reads expected flash/config/EEPROM bytes.
- cmd 0x44 returns the same bytes as the non-USB diagnostic path.

Regression risk:

- Existing USB tests may be asserting direct RAM effects created by old
  harness shortcuts. If they break, preserve the user-level HID behavior
  but update shortcut-specific assertions.

## Regression Investigation Template

Use this template in `docs/SIM_REWRITE_RUST_PROGRESS.md` notes or a
dedicated `docs/analysis/...` note whenever a focused fidelity change
breaks current DLCP tests.

```text
Fidelity item: FID-__
Focused test command:
DLCP regression command:
Failure:
Classification: sim bug | DLCP test bug | intentional divergence | firmware behavior exposed
Root cause:
Resolution:
Remaining xfail/skip/shim:
Removal condition:
```

## Acceptance For This Campaign

The fidelity campaign is complete when:

1. Every FID row in `docs/SIM_REWRITE_RUST_SPEC.md` section 11c is either
   implemented with focused tests or explicitly documented as a DLCP
   scoped non-goal with tests pinning the chosen behavior.
2. `cargo test -p dlcp-sim --release` passes.
3. The current Rust backend pytest gate passes with no new unexplained
   skips or xfails.
4. Any existing DLCP tests changed by the campaign have a regression
   investigation record.
5. `docs/SIM_REWRITE_RUST_SPEC.md`, this implementation plan, and
   `AGENTS.md` remain synchronized.
