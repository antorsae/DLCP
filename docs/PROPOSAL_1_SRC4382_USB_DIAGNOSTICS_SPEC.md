# PROPOSAL 1: SRC4382 Signal Diagnostics

Status: V1a implemented for MAIN V3.5 USB `cmd 0x45` raw page-0 reads with host-side clock/status decode; V2 remains proposal
Primary value: source visibility and field debugging
Targets:
- V1: MAIN V3.5+ USB-only diagnostics; no CONTROL/LCD/protocol changes
- V2: paired MAIN V3.5+ and CONTROL V1.74+ full LCD support
Related draft: `docs/SRC4382_USB_DIAGNOSTICS_SPEC.md`

## Goal

Expose the SRC4382 receiver state as a first-class service diagnostic surface.
The operator should be able to answer:

- which digital receiver is selected;
- whether the receiver is locked;
- whether the source is PCM or IEC61937/DTS non-PCM;
- whether the source is reporting errors;
- what sample-rate evidence exists;
- why Auto Detect held, muted, or changed route.

The feature must be read-only from the operator perspective.  It must not expose
arbitrary SRC4382 writes.

## Scope Split

### V1: USB-Only MAIN Diagnostics

V1 is deliberately narrow.  It adds MAIN-side USB/HID inspection of SRC4382
state and host tooling decode.  It does not add any CONTROL firmware, LCD pages,
current-loop frames, parser ranges, setup-menu items, or background polling.

V1a is the USB `cmd 0x45` raw page-0 register-read diagnostic.  Host tooling
uses it to assemble the receiver/SRC register set plus high-value
clock/status registers `0x03..0x07`, `0x09..0x0A`, and `0x0E`.  It does not
implement USB `cmd 0x46`, page-1 channel-status reads, PB1/PB2 addressed
snapshots, CONTROL/LCD/current-loop integration, setup menu behavior, or
arbitrary SRC4382 writes.

V1 goals:

- expose selected SRC4382 receiver state through USB `cmd 0x45`;
- decode lock/non-PCM/error/rate evidence in host tooling;
- expose enough page-0 clock/divider configuration to derive SRC4382-owned
  master-mode rates from the known 24 MHz red/MCLK clock when the selected
  Port A/B or DIT path is actually clocked from MCLK;
- preserve page 0 and avoid any writes to SRC4382;
- prove that diagnostic reads do not perturb audio, Auto Detect, mute, or
  preset apply.

V1 explicitly excludes:

- CONTROL LCD `PBn SIG` or `Src Err` pages;
- MAIN-to-CONTROL chain command `0x24`;
- CONTROL parser/range allocation and freshness logic;
- LCD rate/error/payload formatting decisions;
- any new user-visible front-panel workflow;
- USB `cmd 0x46` raw read-window support in V1a;
- page-1 channel-status bytes in V1a.

This keeps the first implementation in one firmware image and avoids combining
SRC correctness with current-loop/LCD lifecycle risk.

### V2: Full CONTROL LCD Support

V2 builds on V1 after USB behavior is hardware-proven.  It adds a compact
MAIN-to-CONTROL signal snapshot, CONTROL cache/freshness handling, and PB-scoped
LCD pages.  V2 may use either Link v2 or a legacy exact parser range; it must
not widen existing filename, identity, or diagnostics parsers.

## Existing Hardware/Firmware Hooks

- MAIN already reads and writes the SRC4382 on the secondary I2C path.
- Existing Auto Detect uses page-0 `0x13.RXCKR[1:0]` and `0x12` non-PCM.
- V3.4 already records USB-only SRC counters `N/L/C`.
- Existing draft reserves USB HID `0x45` and `0x46`.
- SRC4382 page-0 exposes:
  - `0x03..0x06`: Port A/B format, output source, master/slave mode,
    clock source, and LRCK divider (`/128`, `/256`, `/384`, `/512`);
  - `0x07`: DIT input source, master-clock source, and TX frame divider;
  - `0x0D`: receiver select;
  - `0x08`: TX/output path;
  - `0x09`: DIT validity and channel/user-data source;
  - `0x0A`: SRC/DIT interrupt/status bits including mask-gated `READY`,
    mask-gated ratio-direction interrupt status,
    transmitter slip, and transmitter-buffer-transfer status;
  - `0x0E`: RXCKO output enable/divider plus loss-of-lock and auto-mute
    behavior;
  - `0x12`: IEC61937/DTS non-PCM flags;
  - `0x13`: RXCKR recovered-clock class;
  - `0x14`/`0x15`: receiver errors, including `UNLOCK`;
  - `0x29..0x2C`: IEC61937 PC/PD burst preamble;
  - `0x32..0x33`: SRC ratio readback;
  - `0x2D..0x2F`: SRC control/word length.

## V2 User-Visible LCD Design

V2 only.  Do not implement this in the USB-only V1.

Add addressed PB signal pages after the existing PB diagnostics pages:

```text
Volume -> Preset -> Input -> Setup -> PB1 Diag -> PB2 Diag -> PB1 Sig -> PB2 Sig -> Src Err
```

### PBn Sig Page

The Signal page is per-MAIN.  This avoids hiding PB1/PB2 disagreement, which is
exactly the class of field issue the diagnostics must surface.

Examples:

```text
0123456789012345
+----------------+
|PB1 SIG RX1 LOCK|
|PCM 48k 24b E0  |
+----------------+

|PB2 SIG RX3 LOCK|
|NONPC 48k 24b E4|

|PB1 SIG RX1 CLK?|
|PCM --  24b E0  |

|PB2 SIG I2CERR  |
|partial old     |

|PB1 SIG n/a     |
|old MAIN        |
```

Row 0:

- columns `0..2`: `PB1` or `PB2`;
- columns `4..6`: literal `SIG`;
- columns `8..10`: receiver `RX0..RX3` or `---`;
- columns `12..15`: `LOCK`, `UNLK`, `CLK?`, `old`, or `n/a`.

Row 1:

- columns `0..4`: payload token:
  - `PCM`;
  - `AC3`;
  - `DTS1`, `DTS2`, `DTS3`;
  - `AAC`;
  - `MPEG`;
  - `ATRAC`;
  - `NONPC` if IEC61937 is set but PC decode is unknown.
- columns `6..8`: rate token derived from evidence:
  - `32k`, `44k`, `48k`, `88k`, `96k`, `192`;
  - `-- ` if unknown;
- columns `10..12`: word length token `16b`, `20b`, `24b`, or `--b`;
- columns `14..15`: compact error byte `E0..EF` or `E?`.

Lock semantics:

- `LOCK` is based on `0x14.UNLOCK == 0`, not `RXCKR`.
- `CLK?` means `RXCKR == 0` while `UNLOCK == 0`; it is a recovered-clock
  estimator hole, not source absence.
- `UNLK` means formal unlock and may feed source-loss debounce.
- Non-PCM is still source-present.  It may be muted by policy, but must not be
  rendered as no source.

### Src Err Page

```text
0123456789012345
+----------------+
|Src Err PB1     |
|CRC PAR BP V Q  |
+----------------+

|Src Err PB2     |
|UNLOCK OSLIP    |
```

Row 1 lists active error tokens in priority order:

1. `UNLOCK`
2. `BP` bipolar error
3. `PAR` parity
4. `V` validity bit
5. `CRC` channel-status CRC
6. `Q` Q-channel CRC/change
7. `OSLIP`

If no errors:

```text
|Src Err PB1     |
|clean           |
```

## V1 USB HID Design

Implement `cmd 0x45` first.  Keep `cmd 0x46` deferred.

### `cmd 0x45`: Raw Page-0 Register Read

V1a keeps MAIN firmware deliberately small.  The firmware does not maintain a
SRC4382 snapshot cache, does not whitelist a fixed register set, and does not
decode sample rate, lock, payload, PC/PD, or errors.  It reads one requested
SRC4382 page-0 register over the existing secondary I2C bus and returns that
raw byte.  Host tooling owns the register list, retry/poll policy, and human
decode.

Request:

```text
byte 0: 0x45
byte 1: SRC4382 page-0 register address
byte 2..63: ignored in V1a
```

Response:

```text
0: 0x45
1: status
   0 OK
   1 I2C error
2: register echo
3: register value, or 0xFF on failure
4..63: reserved, currently zero
```

Rules:

- There is intentionally no firmware-side register whitelist.  Operator tooling
  may ask for any page-0 register, including diagnostic one-offs such as
  `0x7F`, but V1a does not select other pages.
- V1a must not write the SRC4382 page-select register.  Page-1 channel-status
  reads remain deferred because they require a page flip and restore policy.
- The host default snapshot reads page-0 registers `0x03`, `0x04`, `0x05`,
  `0x06`, `0x07`, `0x08`, `0x09`, `0x0A`, `0x0D`, `0x0E`, `0x12`, `0x13`,
  `0x14`, `0x15`, `0x2D`, `0x2E`, and `0x2F`.
- The host reads ratio registers `0x32` then `0x33` as two explicit cmd45
  transactions.  Real DLCP hardware showed that a two-byte read from `0x32`
  repeats the high byte, so V1a must not rely on I2C auto-increment.
- The host reads IEC61937 PC/PD as four explicit cmd45 transactions for
  `0x29`, `0x2A`, `0x2B`, and `0x2C`.
- Any raw-read failure becomes `status=1` for that register.  Host tooling marks
  the assembled snapshot partial and fills missing derived fields with `0xFF`
  or `unknown`.
- Host rate decode must assume the red/MCLK clock is 24 MHz, then derive
  `MCLK/divider` only when `0x03..0x07` prove the relevant Port A, Port B, or
  DIT block is in master mode and clocked from MCLK.  A `/256` divider under
  those conditions is `24 MHz / 256 = 93.750 kHz`.  If the port is slave mode,
  clocked from RXCKI/RXCKO, or otherwise not tied to the rendered path, display
  the divider evidence without claiming an exact output sample rate.
- Host input-rate estimates from `0x32..0x33` must be labelled as estimates and
  require both ratio bytes plus a proven output-rate basis.  Do not require
  `0x0A.READY == 1`: hardware testing showed that `0x0A.READY` is mask-gated by
  `0x0B.MREADY`, so the DLCP default mask state can leave READY low while the
  ratio register pair is still useful.  Render READY as interrupt/status
  evidence, not as a ratio-valid gate.

### `cmd 0x46`: Bounded Raw Read Window

Deferred from V1a.  If added later, keep debug-only and read-only:

```text
request:  0x46, page, start_reg, count <= 0x30, flags bit0 restore page0
response: 0x46, status, count, data...
```

Reject any write flag.  Reject any request that does not restore page 0.

## V2 CONTROL Chain Design

V2 only.  V1 does not allocate this command, add parser state, or add CONTROL
polling.

If Link v2 is not available, use a legacy addressed query that does not overlap
the V1.73 identity range or Proposal 6's `BF/56..BF/5A` extended counter range.

```text
CONTROL -> MAIN: [B1/B2, 0x24, 0x00]

MAIN -> CONTROL:
  BF/5B  status_flags      bit0 valid, bit1 stale, bit2 partial, bit3 i2c_err
  BF/5C  route_rx          high nibble route, low nibble rx index or 0xF
  BF/5D  reg_12_nonpcm
  BF/5E  reg_13_rxckr
  BF/5F  reg_14_rxerr
  BF/60  reg_15_cserr
  BF/61  pc_type_low
  BF/62  decoded           bits 0..1 lock, bits 2..4 payload class, bit5 wordlen unknown
```

Parser rules:

- `BF/5B` starts a fresh snapshot for the addressed PB.
- `BF/62` commits it.
- A timeout renders `PBn SIG old`; a bad range byte is ignored, not parsed as
  filename, identity, or Proposal 6 data.
- Poll only the visible `PBn Sig` page, near 1 Hz.

## V1 MAIN Responsibilities

- Keep `cmd 0x45` as a compact synchronous USB operator diagnostic: one
  requested SRC4382 page-0 register in, one raw byte out.
- Reuse existing bounded I2C primitives and ACKSTAT fault latching.
- On I2C failure, return status `1`, value `0xFF`, attempt STOP, and leave
  host tooling to mark the assembled snapshot partial.
- Read `0x14.UNLOCK` as the lock oracle.  `RXCKR` is rate evidence only.
- Do not allocate persistent cmd45 RAM cache/job cells in MAIN.
- Do not add arbitrary SRC4382 writes.
- Add host-side decode in `scripts/dlcp_src4382_diag.py` so V1 is immediately
  useful without CONTROL support.

## V2 MAIN Additions

- Export the cached SRC snapshot to CONTROL using Link v2 or the exact legacy
  `cmd 0x24` range below.
- Rate-limit chain responses so LCD polling cannot compete with preset filename,
  diagnostics identity, or fault frames.
- Preserve the V1 USB snapshot ABI.

## V2 CONTROL Responsibilities

- Add Signal and Src Err pages.
- Poll the visible MAIN at about 1 Hz while parked on those pages.
- Render stale snapshots explicitly:

```text
|PB1 SIG old     |
|PCM 48k 24b E0  |
```

- Keep buttons/IR responsive while polling.
- Never display Signal as healthy if the PB diagnostics page would show `PBn!`.

## V1 Test Plan

Simulator:

- cmd `0x45` returns deterministic raw page-0 register values with register
  echo and `status=0`.
- I2C NACK returns partial/fault status and increments `I`.
- RXCKR hole with `UNLOCK=0` decodes as estimator-hole/clock-unknown, not
  source loss.
- Non-PCM renders source-present payload state and does not drive Auto Standby.
- `UNLOCK=1` decodes as formal unlock.
- IEC61937/PC values decode to `AC3`, `DTS1`, etc.
- `0x45` does not validate/whitelist byte 1 or padding and never writes
  SRC4382 page select.
- The host assembles the default register set, optional ratio registers, and
  optional PC/PD registers from independent raw cmd45 reads.
- Ratio reads are explicit `0x32` then `0x33`; no auto-increment assumption is
  made anywhere in V1a.
- `0x46`, if included, is read-only, count-limited, and refuses non-page-restore
  access.
- Normal Auto Detect, preset apply, mute refresh, and volume restore behavior is
  unchanged with USB raw-read diagnostics active.
- Host CLI/JSON decodes the snapshot and reports partial/I2C-error states
  without hiding raw bytes.

Hardware:

- SPDIF/USB/AES/Optical USB snapshot matches actual selected input.
- Non-PCM source mutes or warns before live audio.
- Track-boundary RXCKR estimator holes do not decode as hard source loss.
- Repeated USB polling while playing audio does not create mutes, route churn,
  preset changes, or SRC page-stuck behavior.

## V2 Test Plan

Simulator:

- CONTROL chain parser accepts exactly `BF/5B..BF/62` for signal snapshots and
  ignores adjacent identity/diagnostic ranges.
- `UNLOCK=1` renders `UNLK`.
- RXCKR hole with `UNLOCK=0` renders `CLK?`.
- IEC61937/PC values render as `AC3`, `DTS1`, etc.
- CONTROL Signal page remains responsive to volume, mute, preset, standby.
- Old MAIN timeout renders `PBn SIG n/a` or `old` without disturbing existing
  diagnostics pages.

Hardware:

- USB watch and CONTROL Signal page agree for lock/error/payload tokens.
- Track-boundary RXCKR estimator holes do not flap the LCD into false hard loss.
- Visible-page-only LCD polling does not cause audible disruption or current-loop
  freshness failures.

## Risks

V1:

- Page-1 channel-status reads may be disruptive.  Make that optional until
  hardware-proven.
- SRC page selection must always restore page 0, including on I2C error.
- Host decode may overstate rate certainty; label rate as evidence.

V2:

- Too much CONTROL polling can recreate current-loop load problems.  Keep
  visible-page-only cadence and prefer MAIN cached snapshots.
- Rate estimates from SRC ratio are not exact unless output rate is known.
  Display them as evidence, not truth.
