# Preset Filename on LCD — Feature Specification

Last updated: 2026-05-31
Status: **implemented for the paired V3.3/V1.72 filename build**. The feature is
still preliminary/paired-revision only; hardware OCR tolerance remains a gate
detail rather than a firmware protocol requirement.
Scope: show the active preset's DSP filename on the CONTROL Preset screen,
sourced from MAIN over the 31,250-baud current-loop chain, **horizontally
scrolled** when it exceeds the 16-column LCD row.
Targets: paired MAIN `V3.3` + CONTROL `V1.72` filename builds
(incremental filename-reply job, slot+generation query, in-loop service,
scroll, Preset row-0/row-1 redesign). This is a preliminary paired-revision
feature: both MAIN and CONTROL must contain the filename changes. Because the
feature intentionally stays on the `V3.3`/`V1.72` pair, filename-capable images
are distinguished from diagnostics-identity-only `V3.3`/`V1.72` images by the
next release revisions: MAIN `V3.3` rev `>= 0x73` and CONTROL `V1.72` rev
`>= 0x39`.

### Review history

- **Review 1** (8 findings) → slot-specific query, health-suffix conflict,
  state reset, service placement, parser pseudo-code, pacing, OCR, retry policy.
- **Review 2** (11 findings, all verified against source) — this revision:
  | # | Sev | fix |
  |---|---|---|
  | R2-1 | High | **service placement still wrong** — `display_loop_iteration` loops internally (`:2945` `bra` to `0CB4`, returns only on button/event `:2979`); move service *inside* it gated by Preset ([§7](#service-placement-r2-1)). |
  | R2-2 | High | **stale in-flight reply for wrong slot** — add `START`/`END` reply identity (the `id` byte); CONTROL discards non-matching ([§3](#3-chain-protocol), [§7](#parser-case)). |
  | R2-3 | High | **active-slot USB rename** — serving EEPROM for the active dirty slot is stale; **RAM-for-active is now mandatory** ([§2](#slot-source-mandatory-r2-3)). |
  | R2-4 | High | **HW gate can pass without the feature** — change the existing preset gate + add a failing `DLCP_HW_PRESET_FILENAME_CONFIRM` gate ([§10](#10-test-plan-red-test-first)). |
  | R2-5 | High | **OCR can't prove scrolling content** — raw ordered row capture + scroll reconstruction + tests ([§10](#10-test-plan-red-test-first)). |
  | R2-6 | Med | **pacing test too weak** — explicit unpaced-fails / paced-completes red/green vs the existing ring xfail ([§10](#10-test-plan-red-test-first)). |
  | R2-7 | Med | **MAIN handler too blocking** — a 55–90 ms in-handler burst stalls USB/I2C/preset; convert to an **incremental reply job** serviced from `periodic_service_loop` ([§4](#4-main-implementation-v33)). |
  | R2-8 | Med | **health visibility lost on Preset** — move a **compact health glyph to row-0 col 14**; change the contract + test ([§7](#row-0-status-zone-r2-8--r2-9), [§9](#9-versioning--build)). |
  | R2-9 | Med | **row-0 dropped DSP-fault precedence** — col-15 shows `'!'` on fault, else A/B ([§7](#row-0-status-zone-r2-8--r2-9)). |
  | R2-10 | Low/Med | **row-dirty flag undefined** — define `FNAME_ROW_DIRTY` (bit 3) ([§6](#6-control-ram-allocation-v172)). |
  | R2-11 | Low | **old-MAIN echo wording** — V3.2 unknown-cmd echoes the *data byte* (the arbitrary query id), not a cmd-XOR ([§2](#pre-feature-main), [§8](#8-edge-cases)). |

- **Review 3** (codex adversarial, read-only; source-verified) — folded in:
  | # | Sev | fix |
  |---|---|---|
  | R3-1 | High | **lazy MAIN reply can emit a torn name** — the active slot is served live from RAM, which USB cmd 0x03 + `preset_load_filename` mutate mid-burst (`dlcp_main_v32.asm:9871`); add a `filename_rev` snapshot guard that aborts the burst on change ([§4](#4-main-implementation-v33)). |
  | R3-2 | Low | **exactly-30 read** — check `idx >= 30` *before* the read and the `0x30+idx` calc, else idx=30 reads past the field / computes `0x4E` (=END) ([§4](#4-main-implementation-v33)). |
  | R3-3 | Med | **char frames carry no id** — a wrong-id `START` left an armed burst open; now it **disarms** (keeps PENDING) so foreign chars can't populate the cache ([§7](#parser-case)). |
  | R3-4 | Med | **parser placement** — the existing BF/2x dispatch exits for `cmd >= 0x2C` (`:1241`); the `BF/2D..4E` case must be reached *before* it or START/LEN is unreachable ([§7](#parser-case)). |
  | R3-5 | Med | **pacing is mandatory** — "one frame per pass" is not a timing contract; gate emission on a ~1 ms minimum inter-frame interval ([§3.3](#33-pacing-via-the-incremental-job-r2-6-r2-7)). |
  - Codex independently re-verified (no finding): filename constants, `0x25^0x03=0x26`, display-loop idle behavior, DSP-fault precedence, BSR tail discipline, CONTROL bank-2 nonuse, diag `<0x80` masking.

- **Review 4** (operator-directed) — folded in: filename feature kept on
  `V3.3`/`V1.72` with required rev markers (`MAIN >=0x73`, CONTROL >=0x39`);
  pending expiry added with no automatic reply retry; HFD empty
  names explicitly render blank; `cmd 0x26` is documented as a split command, not
  a reuse of `cmd 0x25`; filename pacing uses a pass-local `chain_tx_emitted`
  primitive; `filename_rev` seqlock arm order is exact; PB2-only health loss does
  not blank PB1-authoritative filenames; parser rejects non-printable injected
  chars; scroll cycle is exact; spec-manifest tests pin these requirements.
- **Review 5** (agent split: deployment/protocol/CONTROL/LCD/test coverage) —
  folded in: reply now includes a `BF/2D` length signature before chars, so
  `START+END` alone cannot validate and a dropped final char aborts; CONTROL
  uses a 16-bit scroll divider; Preset row-0 health/fault status is patched from
  the in-loop service while parked on Preset; PB2 filename helper is forbidden
  while Preset is visible in v1; reconnect/`CONNECTED` completion is the only
  automatic lifecycle requery after an interruption.
- **Review 6** (operator-directed) — folded in: `LEN` is a one-shot seal and
  any duplicate/late/corrupt `BF/2D` aborts instead of resealing a truncated
  cache; MAIN filename job RAM is cleared on every runtime cold-entry path, not
  only POR/BOR; the CONTROL filename-specific clear helper skips Diagnostics
  identity RAM; row-1 render is explicitly incremental; row-0 uses bounded
  one-cell patches; flashing validation uses app-resident chain identity, not
  USB/EEPROM revision bytes.
- **Operator decision** — row-1 filename rendering is locked as **incremental
  one-character-per-service-tick**. Full-row redraw is not an implementation
  option for V1.72; keep it only as a comparison/modeling note.

---

## 1. Summary / motivation

The DLCP stores a human-readable filename per preset (A/B) — e.g.
`LX521.4 22MG10F-v5` — visible only over USB HID today. This feature shows the
active preset's full filename on the CONTROL **Preset** screen, row 1, scrolling
names longer than 16 chars. The repo's own default config motivates scrolling:
`artifacts/LX521.4/` names A=`…-v5` and B=`…-v7` — 18 chars differing only past
col 15, so truncation would render both identically (see [§13](#13-worked-example-repo-default-config)).

### Target LCD layout (16×2), Preset screen

```
        col: 0123456789012345
            +----------------+
 row 0      |Preset         A|   col 14 = compact health glyph:
            |                |       ' ' healthy, '*' any PB stale/lost (R2-8)
            |                |   col 15 = '!' on DSP fault, else A/B (R2-9)
 row 1      |LX521.4 22MG10F-|   full filename; scrolls if >16; empty until fetched
            +----------------+
```

Exact row-0 examples:

| state | row 0 |
| --- | --- |
| healthy preset A | `|Preset         A|` |
| any PB stale/lost, preset A | `|Preset        *A|` |
| any PB stale/lost, preset B | `|Preset        *B|` |
| DSP fault, links healthy | `|Preset         !|` |
| DSP fault plus stale/lost link | `|Preset        *!|` |

The `*` glyph is intentionally generic in v1; it does not identify PB1 vs PB2
or stale vs lost. Use the Volume/Diagnostics screens for PB-specific link
detail. Volume/Input/Setup/Diagnostics screens are unchanged (they keep their
existing row-1/link-health or Diagnostics identity behavior). Only the Preset
screen gives row 1 to the filename.

---

## 2. Data source (MAIN)

| symbol | value | meaning |
| --- | --- | --- |
| `preset_filename_ram_base` | `0x02C0` | **active** preset's live name (BANK 2) |
| `preset_filename_len` | `0x1E` (30) | stored field width |
| `preset_filename_eeprom_a` | `0x60` | EEPROM offset, preset A |
| `preset_filename_eeprom_b` | `0x83` | EEPROM offset, preset B |

### Slot source — MANDATORY (R2-1 + R2-3)

The query is slot-specific. MAIN serves the **requested** slot:

```
if requested_slot == active_slot (active_flags.2):   serve preset_filename_ram_base (RAM)
else:                                                serve EEPROM(requested_slot)
```

- **Active slot ⇒ RAM (required, R2-3):** the active slot's authoritative
  current name is always in `preset_filename_ram_base`, including an
  uploaded-but-not-yet-persisted USB rename (MAIN writes the HID filename into
  live RAM first, persists to EEPROM later; `dlcp_main_v32.asm` filename
  xact-gate). Reading EEPROM for the active dirty slot would show a stale name.
- **Non-active slot ⇒ EEPROM (R2-1):** during the ~150 ms async preset apply the
  *active* slot is still the **old** one and RAM holds the old name, so a ~tens-
  of-ms query for the just-selected (not-yet-active) slot must read that slot's
  EEPROM name directly. This kills the flip race: CONTROL asks for the slot it
  displays and gets that slot's name regardless of apply timing.

### Effective length & sanitization

`L` = first index 0..29 whose byte is not printable ASCII (`0x20..0x7E`), capped
at 30 (`0xFF`/`0x00`/control terminates). LX521.4 → `L = 18`. The reply job
discovers `L` lazily (stops at the first non-printable). Every transmitted char
is clamped to `0x20..0x7E` so no `>= 0x80` byte can reach the chain (the
forwarder treats `>= 0x80` data as a route byte).

### Pre-feature MAIN (R2-11)

An older/pre-feature MAIN has no `cmd 0x26` handler: the unknown-command path echoes the
**data byte** (`dlcp_main_v32.asm:1906-1908` sets `ram_0x0BC = data` + arms the
`active_flags.6` echo), so it sends back one stray byte = the query `id`
(`(gen<<2)|(target<<1)|slot` — an arbitrary value `< 0x80`, **not** just
`0x00`/`0x01`). No valid `BF/2E`/`BF/2F` START + `BF/2D` LEN + `BF/4E` END
burst arrives, so CONTROL can never validate a filename cache. If the stray byte lands mid-frame, the normal
route-byte / frame-gap recovery restores framing; the user-visible result is
still an empty filename row. Tests must use non-zero generation ids, not only
0/1.

---

## 3. Chain protocol

### 3.1 Query: `cmd 0x26` (CONTROL → MAIN)

| field | value |
| --- | --- |
| route | `0xB1` for PB1 / primary MAIN, `0xB2` reserved for PB2 / secondary MAIN |
| cmd | `0x26` |
| data | `id = (gen & 0x1F) << 2 \| (target << 1) \| slot` — bit0 `slot` = `PRESET_BIT`; bit1 `target` = 0 for PB1, 1 for PB2; bits 6–2 = 5-bit `gen` |

`id ≤ 0x7F` (chain-safe). Gate-bypassing; dispatches from `cmd_dispatch_xor_chain`
after the existing `cmd 0x25` Diagnostics identity query. MAIN uses `slot = data
& 1` to pick the source and echoes the full `id` in `START`/`END`. The target bit
is included even though the v1 display only schedules PB1, so future PB2 filename
queries use the same command/parser path instead of a separate protocol. The
scroll-direction hint is carried by the START command, not by stealing a data bit
([§3.2](#32-reply-identity-framed-variable-length-burst-main--control)).

`cmd 0x26` is a split command, not a reuse of `cmd 0x25`. It is chosen so the
already-shipped `cmd 0x25` Diagnostics MAIN-identity handler remains in its
current position; `cmd 0x24` remains unused by this v1 feature. Regression tests
must still prove the adjacent XOR dispatch leaves `cmd 0x25` returning
`BF/4F..53` before, during, and after a filename burst.

### 3.2 Reply: identity-framed variable-length burst (MAIN → CONTROL)

| frame | cmd | data | meaning |
| --- | --- | --- | --- |
| **START prefix-first** | `0x2F` | `id` | begin burst; rest on prefix first |
| **START tail-first** | `0x2E` | `id` | begin burst; rest on suffix first |
| **LEN** | `0x2D` | `id ^ L` | expected printable length, 0..30 |
| char 0 | `0x30` | `name[0]` | char index 0 |
| … | … | … | … |
| char L−1 | `0x30+(L−1)` | `name[L−1]` | last char (≤ `0x4D`) |
| **END** | `0x4E` | `id` | burst complete |

The START command is the **auto scroll-direction hint** MAIN computes (§3.5):
`0x2E` = tail-first (rest on the suffix), `0x2F` = prefix-first. All cmd bytes
`0x2D..0x4E` and data bytes (`0x20..0x7E`, or `id ≤ 0x7F`) are `< 0x80`.
CONTROL accepts LEN/char/END frames **only** while armed by a `START` whose
identity matches exactly. A stale burst (old `gen`, e.g. an A-reply arriving
after the user flipped to B) carries the old `id` → never arms → fully discarded
(R2-2). `LEN` carries `id ^ L`, so CONTROL recovers `expected_len = data ^ id`,
requires `expected_len <= 30`, and finalizes only when `received_len ==
expected_len`. Empty name (`L=0`): `START(id)`, `LEN(id)`, then `END(id)`.
`START+END` without LEN never validates; a dropped final char is caught as an
END-time length mismatch. ACK-echo suppressed before the parser tail.

### 3.5 Auto scroll direction (1-bit hint, decided over Option C)

MAIN uses START `0x2E` (tail-first) iff the requested slot's name and the
**other** slot's name share their first 16 characters — i.e. the front window
can't tell the two presets apart, so the difference is in the tail. Otherwise it
uses START `0x2F` (prefix-first). CONTROL only knows the active name, so the
comparison must live on MAIN (it has both: RAM for the active slot, EEPROM for
the other).

**Why 1 bit, not a divergence index (Option C):** with a 16-col window, the
prefix window `[0,15]` and the suffix window `[L-16,L-1]` together cover **every**
column of any name with `L ≤ 32`. The field is `preset_filename_len = 30`, so
whichever end the divergence falls in, one of prefix-/tail-first always shows it
— the binary hint is provably complete here. A full divergence *index* (Option C)
only adds value if the name field ever exceeds 32 chars; it is documented in §12
as the future generalization, not implemented. Fallback for a partial filename
MAIN that can only emit START `0x2F`: prefix-first.

### 3.3 Pacing via the incremental job (R2-6, R2-7)

A 30-char reply is 33 frames = 99 B, **exceeding CONTROL's 48-byte RX ring**, so
the reply must be paced. Instead of a blocking in-handler delay, MAIN emits at
most one frame per pass from `periodic_service_loop` ([§4](#4-main-implementation-v33)),
keeping the command handler non-blocking.

**Pacing is a mandatory rate limit, not an assumption (R3-5 / R2-6).** "One
frame per pass" is *not* a timing contract: MAIN passes can be fast (µs), MAIN
also runs synchronous bursts (e.g. `diag_send_burst_xx`, `send_status_burst`,
`cmd25_identity_query_handler`), and CONTROL only drains when
`display_loop_iteration` reaches `rx_parser_entry`. So the filename job is
lowest-priority: it MUST emit no frame in a foreground pass where another
chain/BF burst was consumed, forwarded, or emitted, and it MUST also enforce a
measured **minimum start-to-start interval of at least 2 ms** between filename
frames. The gate is non-blocking: if the pass was chain-busy or the interval has
not elapsed, the job just returns and retries next pass. The full 33-frame reply then spans at
least ~66 ms, which is acceptable for LCD text and leaves margin above the
~0.96 ms wire time of a 3-byte frame at 31,250 baud. Test #2
([§10](#10-test-plan-red-test-first)) is the gate: *red* = unthrottled burst
overruns the ring; *green* = throttled/lowest-priority burst completes with no
overflow under worst-case status/diag/identity interleaving.

### 3.4 Reserved ranges

`cmd 0x26` is the filename query. Reply `BF/2D..4E` (LEN `0x2D`, START-tail
`0x2E`, START-prefix `0x2F`, chars `0x30..4D`, END `0x4E`) is **globally
reserved** for filename replies. No other current or future V1.72/V3.3 protocol
may emit `BF/2D..4E` while this feature exists; structural tests must guard that
reservation. (`BF/2C` remains below the filename range; `BF/4F..53` remains the
Diagnostics MAIN-identity reply range.)

---

## 4. MAIN implementation (`V3.3`)

`dlcp_main_v33.asm` (clone of v33 Diagnostics identity). The reply is an **incremental job**
(modeled on `preset_job_service`), so the parser handler never blocks (R2-7).

**Job RAM** — MAIN BANK-2 reserved scratch (`0x2F4..0x2FF`, the "Tier-2
reserved" tail in `dlcp_main_ram.inc`). Use fixed sources instead of a generic
pointer to fit the job plus pacing state into the 12-byte window:

| phys | cell | meaning |
| --- | --- | --- |
| `0x2F4` | `fn_job_state` | 0 = IDLE, 1 = SEND_START, 2 = SEND_LEN, 3 = SEND_CHARS, 4 = SEND_END |
| `0x2F5` | `fn_job_id` | byte echoed in START/END = full query `id = (gen<<2)\|(target<<1)\|slot` |
| `0x2F6` | `fn_job_idx` | current char index 0..30 |
| `0x2F7` | `fn_job_src_kind` | 0 = active RAM `0x2C0`, 1 = EEPROM A, 2 = EEPROM B |
| `0x2F8` | `filename_rev` | global byte covering **all** filename backing-store mutations: active RAM slot and A/B EEPROM filename bytes |
| `0x2F9` | `fn_job_rev` | snapshot of `filename_rev` at arm; odd/in-progress or mismatch aborts |
| `0x2FA` | `fn_job_start_cmd` | `0x2E` tail-first or `0x2F` prefix-first |
| `0x2FB` | `fn_job_len` | expected printable length `L` (0..30), sent in the LEN signature |
| `0x2FC` | `fname_tx_gap_lo` | 16-bit non-blocking inter-frame countdown low byte |
| `0x2FD` | `fname_tx_gap_hi` | 16-bit non-blocking inter-frame countdown high byte |
| `0x2FE` | `chain_tx_emitted` | pass-local arbitration flag; clear at `periodic_service_loop` top |
| `0x2FF` | `fn_job_tmp` | scratch for source reads / direction compare; not live across passes |

Because `0x2F4..0x2FF` is wipe-protected across the flash-service init wipe,
**V3.3 cold init must explicitly clear this whole block** on **every runtime
cold-entry path** before normal runtime starts: POR, BOR, software reset,
post-flash/bootloader handoff, and any release-flash return-to-app path. Do not
limit this to POR/BOR.
A random nonzero `fn_job_state` or odd `filename_rev` after a software reset or
bootloader launch would otherwise cause junk emission or permanent
filename-query aborts.

**MAIN code-size budget.** Current V3.3 has more room after the latest size
work, but the Preset-B table at `org 0x4C00` is still the hard boundary:
the current listing leaves about **636 bytes** before the table. Rough
MAIN-only implementation estimate:

| block | rough code bytes |
| --- | ---: |
| `cmd 0x26` XOR dispatch + arm shell | 20-40 |
| source selection, active-RAM vs EEPROM, length scan | 90-150 |
| A/B first-16 comparison + START direction hint | 70-130 |
| `filename_rev` seqlock checks + writer hooks | 50-90 |
| incremental reply job + frame emitter | 130-220 |
| `chain_tx_emitted` pacing/arbitration + cold clear | 60-110 |
| **total likely** | **420-740** |

An unusually aggressive implementation that drops duplication and reuses
existing helpers might land near **330-420 bytes**; the current 636-byte slack
is plausible for that version but not enough to waive the fit check, since the
upper estimate still exceeds it. Therefore this feature requires a hard listing gate:
`test_v33_filename_code_size_fits_before_preset_table`. The gate assembles the
actual image, parses the `.lst`, finds the highest emitted app byte before
`org 0x4C00`, and fails if the implementation overlaps the table or leaves less
than a required **64-byte minimum maintenance margin**. The listing gate must
also pin fixed layout labels (`preset_table_b == 0x4C00`,
`control_release_metadata == 0x77B0`, `bootloader_entry == 0x7800`) so moving a
table or metadata block cannot silently satisfy the fit check. If it fails,
reclaim code first; do not move the table silently.

1. **Dispatch** (in `cmd_dispatch_xor_chain`, after existing `cmd 0x25`):
   ```
   xorlw 0x06            ; cumulative 0x23 ^ 0x06 = 0x25
   btfsc STATUS,2,ACCESS
   goto  cmd25_identity_query_handler
   xorlw 0x03            ; cumulative 0x25 ^ 0x03 = 0x26
   btfsc STATUS,2,ACCESS
   goto  cmd26_filename_query_handler
   ```
   This avoids touching the shipped `cmd 0x25` Diagnostics identity branch.
2. **Handler `cmd26_filename_query_handler` — arm only, no emission:**
   - `id = current_cmd_data & 0x7F`; `slot = id & 1`;
     `target = (id >> 1) & 1` is echoed for CONTROL disambiguation. The MAIN
     need not branch on `target` because route `0xB1`/`0xB2` already selects the
     physical PB, but echoing it makes the protocol multi-PB-ready.
   - Pick the requested-slot source: `slot == active_flags.2` → RAM
     `preset_filename_ram_base` (`fn_job_src_kind = 0`); else → EEPROM
     A/B (`fn_job_src_kind = 1/2`).
   - **Direction hint (§3.5):** read the first 16 chars of slot A and slot B
     (each from RAM if it is the currently active slot, else from its EEPROM
     base) and set `fn_job_start_cmd = 0x2E` iff they are equal (tail-first),
     else `0x2F` (prefix-first). Store `fn_job_id = id`.
   - Compute `fn_job_len = L` while the source is selected: first byte index
     0..29 whose value is not printable ASCII (`0x20..0x7E`), capped at 30.
     The service emits LEN before chars, so the length must be known before
     `SEND_START` is armed.
   - **Snapshot guard (R3-1):** all filename writers use seqlock-style revision
     discipline: increment `filename_rev` before the first byte of any RAM or
     EEPROM filename mutation, and increment it again after the final byte. Arm
     order is exact:
     1. read `filename_rev` before source selection / direction comparison;
     2. require it to be even;
     3. select source and compute `fn_job_start_cmd`;
     4. read `filename_rev` again immediately before storing `SEND_START`;
     5. arm only if the second read is the same even value; otherwise leave the
        job IDLE and suppress the ACK echo.
     Because the active slot is served live from RAM (R2-3) and non-active slots
     are served from EEPROM, a burst spanning ~33 passes could otherwise emit a
     torn old/new name or a direction computed from bytes it never sent. The job
     aborts on an odd `filename_rev` or on any `filename_rev != fn_job_rev`
     change (see step 3). (A 30-byte snapshot buffer would also work but MAIN has
     no free 30-byte region; the revision guard is the cheap equivalent.)
   - Latch `fn_job_id`, `fn_job_idx = 0`, `fn_job_state = SEND_START`, and clear
     `fname_tx_gap_lo/hi` so START can be sent on the next eligible pass
     (overwrites any in-flight job — coalesce; CONTROL discards the abandoned
     burst by its old `id`).
   - `bcf active_flags, 6` (suppress ACK echo); `goto` the parser tail.
   The 16-byte compare + other-slot read are bounded (tens of µs) — far short of
   the incremental burst; defer them into the SEND_START pass if the handler must
   stay minimal.
3. **`filename_reply_job_service`** — called once per pass from
   `periodic_service_loop`; emits **one complete frame** then returns:
   ```
   ; R3-1 abort: if filename_rev is odd or filename_rev != fn_job_rev
   ;             -> state = IDLE, return
   ;             (no END emitted -> CONTROL never validates a torn name)
   IDLE        -> return
   SEND_START  -> emit BF / fn_job_start_cmd / fn_job_id ; state = SEND_LEN
   SEND_LEN    -> emit BF / 0x2D / (fn_job_id ^ fn_job_len); state = SEND_CHARS
   SEND_CHARS  -> if fn_job_idx >= preset_filename_len (30): state = SEND_END; return  ; bound FIRST (R3-2)
                  read byte at (source + fn_job_idx)          ; RAM via FSR, EEPROM via inline read
                  if fn_job_idx >= fn_job_len: state = SEND_END; return
                  if printable(byte): emit BF / (0x30+fn_job_idx) / clamp(byte); fn_job_idx++
                  else:               state = SEND_END
   SEND_END    -> emit BF / 0x4E / fn_job_id ; state = IDLE
   ```
   The `idx >= 30` bound is checked **before** the read and the `0x30+idx` cmd
   calc (R3-2), so idx never reads past the 30-byte field nor computes a char
   cmd of `0x4E` (= END). The `filename_rev` abort runs each pass before any
   emit.
   Each frame is 3× `uart_tx_byte_blocking` (bounded) within the single pass, so
   frames never interleave mid-frame with other senders; complete frames from a
   concurrent status/diag burst are routed by CONTROL on their own cmd bytes and
   don't corrupt the ordered char sequence. EEPROM reads happen inside the pass
   (transient `ram_0x003` use); the job's only cross-pass state is in BANK 2, so
   there is no pacing-delay scratch hazard (the prior blocking-delay design is
   gone). `L` is computed once in the arm handler and sealed by the LEN frame.

`periodic_service_loop` clears `chain_tx_emitted` at its top; every service that
consumes, forwards, or emits chain UART traffic sets it. The filename job runs last
(after `main_uart_service`, status/full-sync, BF/08, diagnostics, and
`cmd25_identity_query_handler`) and emits only if `chain_tx_emitted == 0` and the
2 ms start-to-start gate has elapsed. The gate is a 16-bit calibrated loop-pass
countdown (`fname_tx_gap_hi/lo`), initially `FNAME_TX_GAP_RELOAD = 0x0080`.
If `chain_tx_emitted` is already set when the filename job runs, reload
`fname_tx_gap_hi/lo` and return. Else if the countdown is nonzero, decrement it
and return. Else emit exactly one complete filename frame, set
`chain_tx_emitted`, reload `fname_tx_gap_hi/lo`, and return. The constant is not
trusted by inspection: native sim tests must measure UART frame-start timestamps
and assert every filename frame starts at least 2 ms after prior filename/chain
activity. If loop cadence changes, increase the reload. This is the single
arbitration primitive for pacing; no filename-specific special cases in the
other senders.

---

## 5. Dual-MAIN

The protocol is multi-PB-ready, but the v1 LCD display is PB1-authoritative and
CONTROL supports **one outstanding filename query globally** and one PB1
authoritative cache. The easiest safe v1 rule is: do not issue a PB2 filename
probe while the Preset display is active, or while any PB1 filename state is
`PENDING`, `ARMED`, or `VALID`. PB2 tooling should return busy/no-op in those
states. Future PB2 display/compare work can reuse this frame grammar but must add
either serialized scheduling with cache-owner state or per-target pending/cache
state. CONTROL has one generic filename-query helper:

```
fname_query(target, slot):
    route = target == PB1 ? 0xB1 : 0xB2
    id = (gen << 2) | (target_bit << 1) | slot
    send [route, 0x26, id]
```

The Preset screen scheduler calls it only as `fname_query(PB1, PRESET_BIT)` in
v1. PB2 tooling may use the helper only when the Preset screen is not active and
there is no PB1 filename cache/query state to overwrite. PB2 display support
should reuse the same helper and parser/cache rules; it must not grow a separate
command or separate reply grammar.

**Display authority:** the Preset-screen filename is **PB1/primary-MAIN
authoritative**. If PB1 and PB2 carry different filenames for the same preset
slot, CONTROL displays PB1's name and does not surface PB2's different name. For
example, if PB1 preset A is `FILE_A1` and PB2 preset A is `FILE_A2`, the Preset
screen for A shows `FILE_A1`.

That mismatch is treated as a deployment/configuration risk outside this
feature's v1 display contract. The intended operator invariant is that the
paired MAINs are flashed/uploaded with matching A/B preset names, but preliminary
v1 behavior intentionally does not make this a hard LCD gate: post-flash/USB
tooling may warn about mismatch, but the LCD feature itself does not compare PB1
and PB2 names.

---

## 6. CONTROL RAM allocation (`V1.72`)

CONTROL V1.72 already uses part of BANK 2 for Diagnostics MAIN identity:
physical `0x245..0x254` (`v172_diag_id_*` in `dlcp_control_ram.inc`). Filename
state may use BANK 2, but it must leave that identity block untouched. The table
below uses **physical addresses**. Direct `BANKED` equates in
`dlcp_control_ram.inc` may use low-byte operands instead, e.g. banked `0x045`
means physical `0x245`; tests must normalize banked operands to physical
addresses before checking overlap. Structural tests must assert the filename
ranges are disjoint from `0x245..0x254`.

| symbol | phys | bytes | notes |
| --- | --- | --- | --- |
| `v172_fname_cache` | `0x220..0x23D` | 30 | name chars; `lfsr FSR0, 0x220` |
| `v172_fname_len` | `0x23E` | 1 | received length / next expected char index |
| `v172_fname_expected_len` | `0x23F` | 1 | LEN-sealed expected printable length |
| `v172_fname_flags` | `0x240` | 1 | see bits below; `movlb 0x02` |
| `v172_fname_gen` | `0x241` | 1 | 5-bit query generation (mod 32) |
| `v172_fname_id` | `0x242` | 1 | outstanding `id = (gen<<2)\|(target<<1)\|slot` |
| `v172_fname_scroll_off` | `0x243` | 1 | leftmost rendered index |
| `v172_fname_scroll_hold` | `0x244` | 1 | end-pause countdown |
| `v172_fname_scroll_div_lo` | `0x255` | 1 | 16-bit scroll cadence divider low byte |
| `v172_fname_scroll_div_hi` | `0x256` | 1 | 16-bit scroll cadence divider high byte |
| `v172_fname_deadline_lo` | `0x257` | 1 | 16-bit pending countdown low byte |
| `v172_fname_deadline_hi` | `0x258` | 1 | 16-bit pending countdown high byte |
| `v172_fname_render_col` | `0x259` | 1 | incremental row-1 render column 0..15 |
| `v172_fname_render_off` | `0x25A` | 1 | row-1 render source offset snapshot |
| `v172_fname_row0_status_snap` | `0x25B` | 1 | packed last row-0 col14/15 status for live patch |
| `v172_fname_tmp` | `0x25C` | 1 | parser/render/status scratch; never live across LCD helper calls |

Reserved/overlap rule:

```
filename state:       physical 0x220..0x244 and 0x255..0x25C
diagnostics identity: physical 0x245..0x254
```

No filename cell may be added inside `0x245..0x254`.

The **filename-specific clear helper** must clear only the filename state ranges
`0x220..0x244` and `0x255..0x25C` before the display loop starts. It must not
clear or reuse Diagnostics MAIN identity `0x245..0x254`; that block is owned by
`cmd 0x25` identity display/cache. This is intentionally narrower than saying
"the whole CONTROL cold-init preserves `0x245..0x254`": current V1.72 cold init
may clear Diagnostics identity as part of its own lifecycle. The requirement is
that adding filename state must not introduce a new blind clear from
`0x220..0x25B`, and the filename helper must be split around the Diagnostics
identity block. Tests must seed nonzero bytes across all three regions, run the
filename clear helper, and assert filename state is zero while preserving
`0x245..0x254`.

Flag bits (`v172_fname_flags`): `VALID`=0, `PENDING`=1, `WANT_QUERY`=2,
`FNAME_ROW_DIRTY`=3 (R2-10), `ARMED`=4 (matching START seen; accepting chars),
`FNAME_TAILDIR`=5 (latched from START cmd `0x2E`; 1 = tail-first),
`FNAME_LEN_SEEN`=6 (matching LEN frame accepted).
Semantics: `WANT_QUERY` = query owed (set on entry/flip, cleared once sent);
`PENDING` = query on the wire; `ARMED` = matching `START` received; `VALID` =
complete matching burst cached. BSR: all via `movlb 0x02` (FSR for cache); pin
with a structural test.

---

## 7. CONTROL lifecycle, service placement, render

### Service placement (R2-1)

`display_loop_iteration` is an **internal idle loop** (`:2945` `bra` to its top
`0CB4`; returns only on a button/event at `:2979`). Therefore the filename
**query-issue + scroll service runs INSIDE `display_loop_iteration`'s loop body**
(next to `v171_health_patch_suffix` at `:2817`), **gated by
`display_state_index == 1`** — not in `v171_preset_loop` after the call (that
runs only on screen exit). The `BF/2D..4E` parser case lives in
`rx_parser_entry` (already called each internal tick at `:2814`). Add a sim test
proving the scroll advances while idle on Preset.

### State machine (3-flag + pending deadline)

Use one small reset helper everywhere so interrupted replies cannot strand the
screen in `PENDING=1, WANT_QUERY=0`. Silent failures are observable only by age,
so `PENDING` has a deadline; expiry blanks the row and **does not retry**.

```
fname_reset_blank:
    clear VALID/PENDING/ARMED/WANT_QUERY
    clear v172_fname_len / v172_fname_expected_len
    clear v172_fname_deadline_lo/hi
    reset scroll off/hold/div_hi/div_lo
    call fname_mark_row_dirty_blank  ; resets render_col/off, then dirties row

fname_reset_and_query:
    fname_reset_blank
    if display_state_index == 1 and CONNECTED and not standby: set WANT_QUERY
```

Do not set `FNAME_ROW_DIRTY` with an inline `bsf` scattered through the parser
or lifecycle code. Use two tiny marking helpers:

```
fname_mark_row_dirty_blank:
    clrf v172_fname_render_col
    clrf v172_fname_render_off
    bsf  v172_fname_flags, FNAME_ROW_DIRTY

fname_mark_row_dirty_valid:
    clrf  v172_fname_render_col
    movf  v172_fname_scroll_off, W
    movwf v172_fname_render_off
    bsf   v172_fname_flags, FNAME_ROW_DIRTY
```

This ordering is part of the contract: reset `render_col`/`render_off` first,
then set `FNAME_ROW_DIRTY`. If an abort, timeout, valid `END`, slot flip, Preset
exit, standby, or PB1-loss event happens while a prior incremental repaint is
half done, the next repaint must restart at row-1 col 0. Otherwise the renderer
can skip already-painted columns and leave stale characters from the old row.

Use a 16-bit saturating countdown, not an 8-bit raw display-loop tick counter.
Recommended initial constant: `FNAME_PENDING_DEADLINE_RELOAD = 0x4000`, which is
roughly 2 seconds at the measured ~7.7 kHz modal loop rate and still far above a
healthy 33-frame reply at the mandatory >=2 ms start-to-start rate (~66 ms). If
the measured Preset-loop cadence changes, tune this reload upward, but keep the
test invariant: a max-length paced reply under legal interleaving must complete
before the deadline.

1. **On Preset entry / `PRESET_BIT` change** (full reset, R2-2/R2-3 from review 1):
   first draw row 0 in the new Preset layout, then either synchronously write 16
   row-1 spaces during the screen-entry paint or call
   `fname_mark_row_dirty_blank` before the first visible service tick. The old
   `Active: A/B` row must not remain as a settled state after entry. Seed
   `v172_fname_row0_status_snap` to the row-0 cells just drawn, then call
   `fname_reset_and_query`. Cache need not be cleared — it's only read when
   `VALID`.
2. **On lifecycle interruption:** standby entry, `CONNECTED` clear, PB1 lost
   (`v171_health_age_pb1 >= V171_HEALTH_LOST_AGE`), PB1 reboot, or
   reconnect-wait entry calls `fname_reset_blank`. **Preset exit / menu
   navigation away from `display_state_index == 1` also calls
   `fname_reset_blank` before the state change returns to the menu dispatcher**,
   because the pending deadline only advances while the Preset service is
   visible and the global one-query state must not be stranded off-screen.
   Off-screen deadline service is deliberately not required in v1; cancellation
   on exit is the simpler invariant. Preset entry, slot flip, or
   reconnect-wait completion /
   `CONNECTED` set calls `fname_reset_and_query` if the user is still on the
   Preset screen. Periodic `full_sync_burst` is **not** a lifecycle completion
   signal and must not trigger automatic filename requery. PB1 stale
   (`V171_HEALTH_STALE_AGE <= age < V171_HEALTH_LOST_AGE`) and PB2
   stale/lost/reboot update the row-0 `*` health glyph but **do not** blank or
   invalidate the PB1-authoritative filename cache.
3. **Issue (gated by `display_state_index==1`, each internal tick):** if
   `WANT_QUERY && !PENDING`: `gen = (gen+1) & 0x1F`;
   `id = (gen<<2) | (target_bit<<1) | PRESET_BIT` with `target_bit=0` for the v1
   PB1 display; atomically reserve and enqueue exactly `[0xB1, 0x26, id]`. On
   send success: store `v172_fname_id = id`, reload `v172_fname_deadline_lo/hi`,
   set `PENDING`, clear `WANT_QUERY`. On TX saturation: emit no bytes, leave
   `WANT_QUERY` set, and do not update `v172_fname_id`/`PENDING`.
   *(Only auto-retry: getting the query onto the wire.)*
4. **Pending deadline:** while `PENDING`, each visible Preset service tick
   decrements the 16-bit `v172_fname_deadline_lo/hi` countdown unless it is
   already zero; on zero call `fname_reset_blank` and do not set `WANT_QUERY`.
5. **Reply (in `rx_parser_entry`):** see parser case. `START`(`0x2E`/`0x2F`, id
   match) → `ARMED`, clear `FNAME_LEN_SEEN`, `len=0`, `expected_len=0xFF`, latch
   `FNAME_TAILDIR` from the START cmd. `LEN`(`0x2D`) is a **one-shot seal**:
   accept it only when `ARMED && !FNAME_LEN_SEEN && len == 0`; recover
   `expected_len = rx_data ^ id`, require `expected_len <= 30`, then set
   `FNAME_LEN_SEEN`. Any duplicate `LEN`, late `LEN` after one or more chars, or
   corrupt `LEN` aborts and blanks the row. char → if `ARMED`,
   `FNAME_LEN_SEEN`, `idx==len`, `idx < expected_len`, and data is printable
   ASCII, store, `len++`; otherwise abort.
   A matching duplicate START while already armed restarts the burst for the
   same current `id`: clear `len`, clear `FNAME_LEN_SEEN`, reset
   `expected_len`, and latch the new direction. This matches the parser
   pseudo-code and is safer than continuing a half-old/half-new cache.
   `END`(id match) → only if `FNAME_LEN_SEEN` and `len == expected_len`, then
   `VALID`, clear `PENDING`/`ARMED`, init scroll **per `FNAME_TAILDIR`** (rest on
   the tail if set, else the head), reset `v172_fname_render_col = 0`, set
   `v172_fname_render_off = v172_fname_scroll_off`, then set
   `FNAME_ROW_DIRTY`.
6. **Failure** (drop/reorder/old-MAIN/silent) → parser-detected failures call
   `fname_reset_blank`; silent/no-END failures expire by pending age. Neither path
   sets `WANT_QUERY`. Row 1 is blanked, and recovery is only by Preset re-entry,
   A/B flip, wake, reconnect-wait completion / `CONNECTED` set, or another
   lifecycle event that calls `fname_reset_and_query`. Periodic `full_sync_burst`
   is not a recovery trigger. No per-tick re-query storm.

### Parser case (`rx_parser_entry`, BF/2D..4E)

**Exact insertion point (R3-4):** keep the existing `BF/08` DSP-fault parser
ahead of all filename work, then keep the existing `BF/4F..53` Diagnostics MAIN
identity parser ahead of filename. Route every identity range miss to this
filename range gate, then let filename lower/upper misses fall through to the
existing `v171_bf2x_case_check`. Do **not** branch filename misses directly to
the parser tail: `BF/08` must still update DSP fault state, `BF/21..2C`
diagnostics/health replies must still reach the BF/2x parser, and `BF/4F..53`
identity replies must still be handled before the filename gate. `movlb 0x00`
before any parser-tail exit is mandatory (ring-drain runs in BANK 0 — the
2026-04-20 disaster class, `:1357`).

```
; Called from v172_bf4f_identity_case_check when cmd is NOT BF/4F..53.
; Lower/upper misses fall through to the existing BF/2x diagnostics parser.
v172_fname_case_check:
movlw 0x2D
cpfslt rx_parsed_cmd, A           ; skip if cmd < 0x2D
bra    fname_upper                ; cmd >= 0x2D -> maybe ours
bra    v171_bf2x_case_check       ; cmd < 0x2D -> existing BF/2x path
fname_upper:
movlw 0x4F
cpfslt rx_parsed_cmd, A           ; skip if cmd < 0x4F
bra    v171_bf2x_case_check       ; cmd >= 0x4F -> existing path/tail
movlb 0x02
btfss v172_fname_flags, FNAME_PENDING, BANKED
bra   fname_exit                  ; not pending -> ignore (stale/unsolicited)
; --- START (0x2E/0x2F): arm iff id matches; latch dir from cmd ---
movlw 0x2E
cpfseq rx_parsed_cmd, A
bra   fname_maybe_prefix_start
bsf   v172_fname_flags, FNAME_TAILDIR, BANKED
bra   fname_start
fname_maybe_prefix_start:
movlw 0x2F
cpfseq rx_parsed_cmd, A
bra   fname_not_start
bcf   v172_fname_flags, FNAME_TAILDIR, BANKED
fname_start:
movf  rx_parsed_data, W, A
cpfseq v172_fname_id, BANKED      ; id match?
bra   fname_disarm                ; wrong-id START -> DISARM (R3-3), keep PENDING
bsf   v172_fname_flags, FNAME_ARMED, BANKED
bcf   v172_fname_flags, FNAME_LEN_SEEN, BANKED
clrf  v172_fname_len, BANKED
setf  v172_fname_expected_len, BANKED
bra   fname_exit
fname_not_start:
btfss v172_fname_flags, FNAME_ARMED, BANKED
bra   fname_exit                  ; chars/END before a matching START -> ignore
; --- LEN (0x2D): seal expected length before any char or END is accepted ---
movlw 0x2D
cpfseq rx_parsed_cmd, A
bra   fname_not_len
btfsc v172_fname_flags, FNAME_LEN_SEEN, BANKED
bra   fname_abort                 ; duplicate LEN may not reseal the cache
movf  v172_fname_len, W, BANKED
bnz   fname_abort                 ; late LEN after chars would truncate/retag
<expected_len = rx_parsed_data ^ v172_fname_id>
<if expected_len > 30: bra fname_abort>
movwf v172_fname_expected_len, BANKED
bsf   v172_fname_flags, FNAME_LEN_SEEN, BANKED
bra   fname_exit
fname_not_len:
; --- END (0x4E): finalize iff id and length both match; init scroll ---
movlw 0x4E
cpfseq rx_parsed_cmd, A
bra   fname_char
movf  rx_parsed_data, W, A
cpfseq v172_fname_id, BANKED
bra   fname_abort                 ; END for a different burst -> drop
btfss v172_fname_flags, FNAME_LEN_SEEN, BANKED
bra   fname_abort                 ; START+END without LEN is never valid
movf  v172_fname_len, W, BANKED
cpfseq v172_fname_expected_len, BANKED
bra   fname_abort                 ; dropped/reordered char -> length mismatch
bsf   v172_fname_flags, FNAME_VALID, BANKED
bcf   v172_fname_flags, FNAME_PENDING, BANKED
bcf   v172_fname_flags, FNAME_ARMED, BANKED
bcf   v172_fname_flags, FNAME_LEN_SEEN, BANKED
; rest at the tail (scroll_off = max_off) if FNAME_TAILDIR else the head (0)
<scroll_off = (FNAME_TAILDIR ? max_off : 0); scroll_hold = REST_HOLD>
rcall fname_mark_row_dirty_valid
bra   fname_exit
fname_char:                       ; 0x30..0x4D
btfss v172_fname_flags, FNAME_LEN_SEEN, BANKED
bra   fname_abort                 ; chars before LEN are malformed
movf  rx_parsed_cmd, W, A
addlw 0xD0                        ; idx = cmd - 0x30
cpfseq v172_fname_len, BANKED     ; idx == next-expected?
bra   fname_abort
<if v172_fname_len >= v172_fname_expected_len: bra fname_abort>
<if rx_parsed_data < 0x20 or rx_parsed_data >= 0x7F: bra fname_abort>
<FSR0 = 0x220 + idx>              ; re-derive (FSR0 clobbered by lcd_*)
movff rx_parsed_data, INDF0
incf  v172_fname_len, F, BANKED
bra   fname_exit
fname_abort:
rcall fname_reset_blank                          ; calls fname_mark_row_dirty_blank
bra   fname_exit
fname_disarm:                                   ; R3-3: wrong-id START -> stop accepting chars, KEEP PENDING
bcf   v172_fname_flags, FNAME_ARMED, BANKED
fname_exit:
movlb 0x00
bra   flow_rx_parser_entry_05EA
```

### Row-0 status zone (R2-8 + R2-9)

Row 0 = `"Preset"` (cols 0–5) + spaces (6–13) + **health glyph @ col 14** +
**status @ col 15**:

- **col 15:** `'!'` if `control_flags.DSP_FAULT_BIT` (precedence, matching the
  current Volume-screen render `:5942-5955`), else `'A'`/`'B'` from `PRESET_BIT`.
  The active preset letter is intentionally hidden while DSP fault `!` is shown.
- **col 14:** compact link-health glyph — `' '` when both PB links are fresh,
  `'*'` if any PB link is stale/lost. This is intentionally generic in v1; it
  does not distinguish PB1 from PB2 or stale from lost. This preserves compact
  PB-health visibility on the Preset screen after the row-1 suffix is suppressed
  there; the detailed state remains on Volume/Diagnostics.

`v172_fname_row0_status_snap` encoding:

| bit(s) | meaning |
| --- | --- |
| bit 0 | last col-14 health glyph: 0 = space, 1 = `*` |
| bit 1 | last preset letter source: 0 = A, 1 = B |
| bit 2 | last DSP-fault status: 0 = show A/B from bit 1, 1 = show `!` |
| bits 3..7 | reserved, written as 0 |

The desired col-15 char is `!` when bit 2 is set, otherwise `B` if bit 1 is
set, else `A`. A col-14 patch updates only bit 0. A col-15 patch updates only
bits 1 and 2. This lets one byte represent the two LCD cells without losing
which half was already patched.

`v172_preset_status_patch_service` runs inside the same Preset-gated
`display_loop_iteration` service path, before row-1 filename rendering. It
recomputes the two-character status `(col14, col15)` from current health ages,
`control_flags.DSP_FAULT_BIT`, and `PRESET_BIT`, compares it to
`v172_fname_row0_status_snap`, and patches only changed cells at DDRAM col 14
and/or col 15. Do not rely solely on `v171_health_flags.DISPLAY_DIRTY`: DSP
fault changes and A/B flips also change row 0.

The row-0 patch is deliberately not a full-row redraw. It is two bounded
single-cell updates:

1. If desired col 14 differs from the snap, set DDRAM col 14, write one char,
   update only the col-14 half of `v172_fname_row0_status_snap`, normalize BSR,
   and return or continue only after interrupts have had a chance to run.
2. If desired col 15 differs from the snap, set DDRAM col 15, write one char,
   update only the col-15 half of `v172_fname_row0_status_snap`, normalize BSR,
   and return.

This single-snap approach is sufficient even when both cells change at once:
after the first cell is patched the snap represents the partially updated LCD,
so the next service tick patches the remaining cell. No extra mask byte is
required. The visible transient is bounded to one Preset service tick.

**Scheduler contract:** a row-0 patch consumes only the current tick's **LCD
write budget**, not the whole service tick. Non-LCD work still runs first on
every visible Preset service tick: RX/parser drain, query issue, pending
deadline decrement, health/fault state recompute, and scroll-divider updates.
There must not be an early return that skips those non-LCD services merely
because col 14 or col 15 is dirty. After that state work, the service writes at
most one LCD cell: row-0 patch first if col 14 or col 15 changed, otherwise one
row-1 filename character. Worst case, a simultaneous col14+col15 change delays
row-1 repaint by two ticks, which is preferable to reintroducing long LCD busy
windows.

Concrete row-0 scenarios:

| event while parked on Preset | expected visible progression |
| --- | --- |
| PB2 becomes stale/lost, preset A healthy otherwise | `Preset         A` → `Preset        *A`; row 1 filename remains valid |
| PB2 recovers | `Preset        *A` → `Preset         A`; row 1 unchanged |
| PB1 becomes stale | `Preset         A` → `Preset        *A`; row 1 unchanged |
| PB1 becomes lost/reboots | row 0 gains `*`; `fname_reset_blank` blanks row 1, then reconnect/CONNECTED can requery |
| DSP fault appears on preset B | `Preset         B` or `Preset        *B` → `Preset         !` or `Preset        *!`; `!` hides B |
| DSP fault clears | col 15 returns to current A/B letter; col 14 keeps current health glyph |
| A/B flips while no DSP fault | only col 15 changes A↔B; row 1 resets/requeries for the selected PB1 slot |
| health and DSP fault change together | col 14 and col 15 may update over two ticks, e.g. `Preset         A` → `Preset        *A` → `Preset        *!` |

**Health-suffix change:** `v171_health_patch_suffix` must **skip
`display_state_index == 1`** for its row-1 tail patch; the Preset screen's health
is the compact col-14 glyph instead. `v171_health_service` (ping/age tick) still
runs on all screens. This changes the health contract — update
`tests/sim/test_v171_preset_lcd_health_suffix.py` accordingly.

### Row-1 render + scroll (CONTROL-local, zero chain traffic)

Visible row-1 **settled target states** in v1 are deliberately minimal:

| condition | row 1 |
| --- | --- |
| query pending / loading | 16 spaces |
| valid empty filename (`L=0`) | 16 spaces |
| old/pre-feature MAIN, dropped reply, abort, or other protocol error | 16 spaces |
| valid non-empty filename | rendered/scrolling filename |

No spinner, timeout text, or protocol-error text is shown in v1. A blank row is
therefore valid when HFD/USB intentionally leaves the preset name empty; it is
also the compatibility/failure fallback. Because row 1 is incremental, transient
partial old/new rows or partial blank rows are allowed during a repaint, but the
settled target above must be reached within the `<20 ms` repaint bound. For a
positive feature validation gate, use known non-empty PB1 A/B names. If an
operator intentionally validates an HFD empty-name case, the expected Preset row
is blank, but that is not by itself proof that filename retrieval works.

The renderer is a one-character-at-a-time row writer. `FNAME_ROW_DIRTY` means
"row 1 needs repainting"; `v172_fname_render_col` is the next LCD column to
write, and `v172_fname_render_off` snapshots the source offset for the current
16-character repaint. A repaint writes at most one DDRAM-addressed row-1
character per Preset service tick and clears `FNAME_ROW_DIRTY` only after column
15 has been written.

Hard rule: every path that sets `FNAME_ROW_DIRTY` must do so through
`fname_mark_row_dirty_blank` or `fname_mark_row_dirty_valid`, resetting
`v172_fname_render_col` to 0 and setting `v172_fname_render_off` to the desired
source offset for that repaint (`v172_fname_scroll_off` for valid filenames, 0
for blank/error states) before the dirty bit becomes visible. That includes
valid `END`, parser aborts, pending deadline expiry, Preset entry blanking,
Preset exit blanking, standby/link-loss blanking, slot flips, and
reconnect-triggered resets. A path that marks the row dirty without resetting
the render cursor can skip already-painted columns and leave stale text from the
previous row.

```
desired_off =
    0                         if !VALID or len <= 16
    v172_fname_scroll_off      if len > 16

if ROW_DIRTY:
    if render_col == 0: render_off = desired_off
    src = render_off + render_col
    ch =
        ' '                    if !VALID
        cache[src]              if src < len
        ' '                    otherwise
    set DDRAM 0xC0 + render_col
    write ch
    render_col++
    if render_col == 16:
        render_col = 0
        clear ROW_DIRTY
    return

if !VALID or len <= 16:
    return

; len > 16:
;   max_off = max(len - 16, 0)
;   rest_off = FNAME_TAILDIR ? max_off : 0
;   far_off  = FNAME_TAILDIR ? 0 : max_off
;   step     = FNAME_TAILDIR ? -1 : +1
; On VALID init: scroll_off=rest_off; scroll_hold=REST_HOLD; ROW_DIRTY=1.
if scroll_div_hi:lo != 0: decrement 16-bit divider; return
reload scroll_div_hi:lo          ; pace target 300 ms +/-100 ms per step
if scroll_hold>0: scroll_hold--; return
if scroll_off == far_off:
    scroll_off = rest_off; scroll_hold = REST_HOLD; set ROW_DIRTY; return
scroll_off += step; set ROW_DIRTY
if scroll_off == far_off: scroll_hold = FAR_HOLD
```

**Full-row redraw vs. incremental render tradeoff.**

Decision: **use incremental one-char render** for CONTROL V1.72. This is a
deliberate safety tradeoff: the extra state/code is smaller than the risk of a
long foreground LCD burst while UART/IR work is active.

| approach | pros | cons | disposition |
| --- | --- | --- | --- |
| Full 16-char redraw in one service pass | Simpler state machine; fastest visual update; fewer partially updated transient frames | Long LCD busy-delay window; higher chance of starving RCIF/RBIF while chain frames or IR arrive; repeats the class of access-bank scratch/lcd helper bugs already seen in this project; harder to prove no foreground-service regression | Rejected for implementation, acceptable only as a throwaway Python model |
| Incremental one-char render | Bounded LCD work per tick; ISR/RCIF/RBIF can run between characters; uses explicit `render_col`/`render_off` state; easier to stress with UART/IR tests | More state; a fresh repaint takes up to 16 service ticks, so the row may be blank/partially updated for a short time after entry or scroll step | Required implementation |
| Hybrid four-char chunks | Fewer ticks than one-char, less blocking than full-row | Still needs chunk state and has a larger worst-case interrupt-off/LCD-scratch window; not materially simpler than one-char | Not used unless one-char proves visibly too slow |

Expected implementation cost for the row-1 LCD renderer, based on current
PIC18 assembly style:

| renderer | estimated code | RAM | expected repaint time |
| --- | ---: | ---: | --- |
| looped synchronous full-row helper | ~90-140 bytes | 0-1 temp cells | one blocking pass |
| incremental one-char renderer | ~150-230 bytes | `render_col` + `render_off` | typically ~5-8 ms for 16 chars; must be <20 ms worst-case |

The incremental renderer's known drawbacks are the two BANK-2 state cells, more
reset/cancel edges, and a short non-atomic visual interval where row 1 may be
partially old/new or partially blank. These are accepted for V1.72 and must be
covered by the named tests in §10.

`rest_off`/`far_off`/step direction are derived from `FNAME_TAILDIR` (prefix-first
= rest 0, step right; tail-first = rest `max_off`, step left), with
`max_off = max(len - 16, 0)` clamped before storing `scroll_off`.
`REST_HOLD` targets ~2 s and `FAR_HOLD` targets ~1 s. The scroll cycle is exact:
render the rest window, hold, step one column per cadence to the far window,
hold, snap back to the rest window, hold, repeat. `lcd_char_write` clobbers
`ram_0x004`/`FSR0H`; other LCD helpers can use access-bank scratch such as
`0x005`/`0x00d`. Keep loop index, cache pointer, masks, row-dirty state, and any
value live across `lcd_command`/`lcd_char_write` in BANK 2 or re-derive them
after the call. Normalize BSR before returning from the render helper.

**LCD write safety:** do not disable interrupts for a whole 16-character row.
Render row 1 with the required incremental row writer
(`v172_fname_render_col`) that writes at most one DDRAM-addressed character per
visible Preset service tick. The helper must either re-derive all scratch after
each `lcd_command`/`lcd_char_write`, or mask GIE only around one LCD command or
one character write and immediately restore the **prior** GIE state (save
`INTCON.GIE` in a banked scratch bit/cell and restore that value; never use an
unconditional `bsf INTCON,GIE`). This keeps RCIF/RBIF able to run between
characters and avoids enabling interrupts if the caller entered with GIE already
clear. Tests must inject RBIF/IR and RCIF traffic during filename
rendering/scrolling.

---

## 8. Edge cases

| # | case | behavior |
| --- | --- | --- |
| E1 | Old/pre-feature MAIN (no `cmd 0x26`) | echoes the **query id byte** `(gen<<2)|(target<<1)|slot`, not just slot 0/1 (R2-11); no valid `BF/2E`/`BF/2F` START + `BF/2D` LEN + `BF/4E` END burst arrives, so pending expires and the row blanks. Tests must include adversarial ids `0x2D`, `0x2E`, `0x2F`, and `0x4E` injected at frame positions 0/1/2, including the case where the following byte equals the pending id, and assert no `VALID` / no stuck `ARMED`. Any parser disturbance is recovered by route-byte/frame-gap resync. |
| E2 | Silent PB1/source | pending expires or PB1 link loss calls `fname_reset_blank`; row blank; requery only after reconnect-wait completion / `CONNECTED` set if Preset is still visible. |
| E3 | `0xFF`/`0x00`/control name byte | terminates `L`; never sent; clamp keeps sent bytes `< 0x80`. |
| E4 | Name ≤ 16 | static, padded. |
| E5 | Name 17..30 | scrolls. |
| E6 | Name exactly 30 | 33-frame reply; lowest-priority, ≥2 ms start-to-start pacing keeps it inside the 48-B ring (§3.3). |
| E7 | Empty name (`L=0`) | START + LEN + END → valid empty row. This is normal for an HFD/USB preset with no filename. |
| E8 | **Flip race** | requested-slot source rule (RAM if active, else EEPROM) → correct slot regardless of the 150 ms apply (R2-1). |
| E9 | **Stale in-flight reply** (flip A→B mid-reply) | A-reply carries old `id` → CONTROL never arms on it → discarded; B-reply (new `id`) accepted (R2-2). |
| E10 | A→B→A fast | generation disambiguates same-slot bursts (R2-2). |
| E11 | USB rename of active slot, unpersisted | active-slot is served from RAM on the next query, so a rename becomes visible on next Preset entry/slot flip/lifecycle requery. No live requery while already showing a valid cache in v1. |
| E12 | Dropped/reordered char | idx≠next or END length mismatch → abort; clear VALID/PENDING/ARMED/LEN_SEEN/len, set ROW_DIRTY; row blanks until entry/flip/lifecycle requery. |
| E13 | Dropped START / LEN / END | not armed / no LEN seal / no finalize -> never VALID; pending deadline blanks the row; no per-tick requery. |
| E14 | TX saturation at issue | atomic `[B1,26,id]` reservation emits nothing on failure; `WANT_QUERY` retried until sent. |
| E15 | DSP fault active | col 15 `'!'` overrides A/B (R2-9). |
| E16 | Link stale/lost on Preset | compact `*` glyph at col 14 (R2-8); PB1 stale (`V171_HEALTH_STALE_AGE <= age < V171_HEALTH_LOST_AGE`) keeps the current row-1 cache, PB1 lost (`age >= V171_HEALTH_LOST_AGE`) blanks/requeries as a source interruption, and PB2-only stale/lost leaves row 1 untouched. |
| E17 | BSR leak on parser path | `movlb 0x00` before the tail. |
| E18 | Names share first 16 (e.g. `…-v5`/`…-v7`) | MAIN uses START `0x2E` → CONTROL rests tail-first, suffix visible on entry (§3.5). |
| E19 | Prefix START / no tail hint from a partial MAIN | START `0x2F` → prefix-first (safe default); auto-direction simply not applied. |
| E20 | Active or EEPROM-backed name mutated mid-burst (USB rename / preset apply / EEPROM commit) | `filename_rev` becomes odd or changes → MAIN aborts the burst (no END) → CONTROL never validates a torn name → blank until next entry/flip/lifecycle requery (R3-1). |
| E21 | Wrong-id / injected `START` while armed | START id mismatch → CONTROL **disarms** (drops ARMED, keeps PENDING) so the foreign burst's chars are not cached; re-arms on the correct START or blanks on pending expiry (R3-3). |
| E22 | PB1/PB2 filenames differ for the same slot | PB1 is authoritative in v1: LCD shows PB1's filename; PB2's different filename is not displayed and no mismatch glyph/error appears. Treat as an optional external deployment check, not an LCD protocol feature. |
| E23 | Wrong-id `END` while armed | aborts the pending burst, clears VALID/PENDING/ARMED/len, sets ROW_DIRTY, and never marks the cache valid. |
| E24 | Standby/wake, PB1 link loss/reconnect, PB1 reboot mid-burst | interruption calls `fname_reset_blank`; wake/reconnect-wait completion / `CONNECTED` set calls `fname_reset_and_query` if Preset is still visible. Periodic `full_sync_burst` is a no-op for filename state. No stuck `PENDING` state. |
| E25 | Injected non-printable char data | CONTROL aborts on `0x00..0x1F` or `0x7F`; it does not store them into the LCD cache even though well-formed MAIN never emits them. Injected `>=0x80` bytes are consumed as route bytes by the outer parser before the filename char path sees them; recovery is by index mismatch, frame-gap resync, or pending expiry, with no garbage stored. |
| E26 | PB2 query/probe | The same `[0xB2,0x26,id(target=PB2)]` protocol is reserved and parseable for future/tooling use; v1 Preset display does not schedule or show PB2 names, and only one filename query may be outstanding globally. |

---

## 9. Versioning & build

**MAIN `V3.3` paired filename build** (`dlcp_main_v33.asm`, `build_v33_release.py`,
runtime identity / version-tuple bump, `V33_MAIN_*`): keeps existing `cmd 0x25`
Diagnostics identity and adds `cmd 0x26` arm + `filename_reply_job`. For this
feature gate, the `cmd 0x25` reply is the app-resident runtime identity; EEPROM
byte `0x82` remains informational and is not proof that the running app contains
filename support.
**CONTROL `V1.72` paired filename build** (`dlcp_control_v172.asm`, `build_v172_release.py`,
`control_release_metadata[11]` + splash bump, `V172_CONTROL_*`): query/cache/
scroll service inside `display_loop_iteration` gated on Preset; Preset row-0
(fault `'!'`/A-B at col 15, health glyph at col 14) + row-1 filename;
`v171_health_patch_suffix` skips state 1. Update
`CLAUDE.md`/`AGENTS.md`/`RELEASE_ARCHIVE.md` and the health-suffix test.

Compatibility stance for this preliminary feature: the filename LCD behavior is
only specified for paired filename-capable `V3.3`/`V1.72` builds. Flash/runbook
validation must treat the pair as filename-capable only when MAIN reports `V3.3`
rev `>= 0x73` and CONTROL reports `V1.72` rev `>= 0x39`. Same-version
diagnostics-identity-only images (`V3.3` rev `<= 0x72`, `V1.72` rev `<= 0x38`)
must be reported as pre-feature even if every other behavior is healthy.

**Deployment identity validation:** MAIN USB/EEPROM revision bytes are not
authoritative for filename capability after app flashing because they can be
stale or reflect a different persistence path. The runbook must validate
app-resident MAIN identity through the running chain image, preferably via the
existing Diagnostics identity query `cmd 0x25` and its `BF/4F..53` reply, before
attempting filename OCR. PB1 is the MAIN physically connected to CONTROL/LCD
(the primary/current-loop side used for the Preset display); PB2 is the
downstream peer. Do not infer PB1/PB2 from host USB enumeration order when both
MAINs are connected by USB. Flash both intended MAINs, then re-check PB1's
app-resident identity from CONTROL/chain before treating the LCD filename gate
as meaningful.

Flash/deployment validation sequence:

No new formal artifact schema is required for this preliminary LCD feature.
Follow the existing repo pattern: a runbook/hardware test may keep a simple log
of the PB target, query id, observed reply frames, timeout/retry count, and
verdict, but that log is evidence, not a new compatibility contract. The actual
firmware contract is only the frame behavior below.

1. Flash both MAINs and CONTROL.
2. Verify CONTROL eligibility marker `V1.72` rev `>= 0x39` from the best
   available CONTROL evidence. Runtime-visible evidence (boot splash/release
   metadata after power-cycle) is preferred; safe-flasher release metadata is
   acceptable for v1 when live CONTROL app probing is unavailable. Do not infer CONTROL identity
   from MAIN USB enumeration.
3. **Mandatory PB1 LCD behavior gate:** verify PB1 MAIN through app-resident
   chain identity, then validate OCR/fresh burst evidence for the PB1 filename:
   - PB1: send `[0xB1, 0x25, id]`.
   - Pass only on a fresh ordered reply for the matching query:
     `BF/4F id`, `BF/50 0x03`, `BF/51 0x03`, `BF/52 rev_hi`,
     `BF/53 rev_lo`, with reconstructed rev `>= 0x73`.
4. Treat USB/HID version strings, EEPROM byte `0x82`, and HFD-visible metadata
   as informational only for this feature gate.
5. PB1 OCR validates PB1 filename behavior because PB1 is LCD-authoritative.
   PB2 old/mismatched state is warning-only in v1 and does not fail the PB1 LCD
   behavior gate once the operator accepts that risk.
6. **Optional paired audit:** verify PB2 through app-resident chain identity
   (`[0xB2,0x25,id]`) and optionally compare PB2 names externally. Any PB2
   mismatch is a warning, not an LCD failure.
7. For blank-name **data validation**, require a fresh captured
   `[0xB1,0x26,id]` followed by `START(id)`, `LEN(id^0)`, and `END(id)` with
   zero char frames. A prior non-empty PB1 OCR gate proves firmware capability
   only; it does not prove that the current blank was fetched.
8. Optional HFD/USB upload validation is a dev/HFD-specific check, not part of
   the normal deployment gate. It should separate active RAM from inactive
   EEPROM: active-slot rename validation should force a fresh query without
   flipping away and expect the active RAM name; inactive-slot validation should
   wait for EEPROM persistence/readback before flipping to the inactive slot.

Mixed-version / rollback behavior:

| CONTROL | PB1 MAIN | PB2 MAIN | Expected behavior |
| --- | --- | --- | --- |
| filename-capable V1.72 rev >=0x39 | filename-capable V3.3 rev >=0x73 | any | PB1 filename can display. PB2 mismatch/old state is an accepted v1 visibility risk; optional tooling may warn, but it is not an LCD failure. |
| filename-capable V1.72 rev >=0x39 | old/pre-feature or diagnostics-only V3.3 rev <=0x72 | any | Row 1 remains blank after pending expiry; report pair as pre-feature / not filename-capable. |
| old/pre-feature or diagnostics-only V1.72 rev <=0x38 | filename-capable V3.3 rev >=0x73 | any | Legacy Preset UI remains; CONTROL never sends `cmd 0x26`; report pair as pre-feature / not filename-capable. |
| filename-capable V1.72 rev >=0x39 | filename-capable V3.3 rev >=0x73 | old/mismatched PB2 | LCD still shows PB1 only. This is explicitly accepted for v1; external validation may warn. |

Blank-name validation: an intentionally empty HFD/USB preset name may display a
valid blank row, but blank LCD alone is never evidence that the current blank was
fetched. Capability can be proven by a prior non-empty PB1 filename gate on the
same images. Current blank-name data validation additionally requires a captured
matching fresh query/reply: `[0xB1,0x26,id(target=PB1,slot)]`, followed by
`START(id)`, `LEN(id ^ 0)`, and `END(id)` with zero char frames. After any
HFD/USB preset upload or rename used for validation, force a fresh query by
leaving/re-entering Preset, flipping A/B, or triggering reconnect-wait completion
/ `CONNECTED` set before OCR capture.

---

## 10. Test plan (red-test-first)

Simulator (`tests/sim/`):

1. **MAIN slot source (R2-1/R2-3)** — `data` slot 0/1 selects A/B; active slot
   served from RAM (incl. an unpersisted USB rename); non-active slot from
   EEPROM; correct during a 150 ms apply (flip-race regression).
2. **MAIN incremental pacing / ring (R2-6/R2-7/R3-5)** — *red:* an unthrottled
   burst (frames back-to-back as fast as passes run) overruns CONTROL's 48-B ring
   / drops frames (relate to `tests/sim/test_v171_hang_modes.py:309` ring xfail);
   *green:* the ≥2 ms-gated lowest-priority job completes with `END` and no
   parser/ring overwrite under worst-case status/diag/identity interleaving; the
   handler does not block USB/I2C/preset progress. Assert the inter-frame gate
   actually limits the rate (not "one per pass") by measuring native UART
   frame-start timestamps. Assert `periodic_service_loop` clears
   `chain_tx_emitted`, all chain traffic producers set it, `filename_reply_job`
   runs last, and filename code does not call `timer3_blocking_delay`.
2b. **MAIN snapshot guard (R3-1)** — mutate `preset_filename_ram_base` (USB cmd 0x03
    rename / `preset_load_filename` / EEPROM filename commit) **mid-burst**:
    `filename_rev` becomes odd or changes → MAIN aborts (no `END`) → CONTROL
    never marks VALID (no torn name); a clean burst with no mutation completes
    normally. Also: `idx==30` boundary emits `END`, never a `0x4E` char nor a
    read past the field (R3-2).
3. **Reply identity (R2-2)** — a stale burst (old `id`, e.g. A-reply after flip
   to B) is discarded; only the matching-`id` burst validates; A→B→A generation
   disambiguation. Include PB target in the id: PB1 uses bit1=0, PB2 uses bit1=1.
3b. **Auto direction (§3.5)** — MAIN emits START `0x2E` iff the two slots share
    their first 16 chars, else START `0x2F`; CONTROL rests tail-first for `0x2E`,
    prefix-first for `0x2F`. Assert: the LX521.4 `v5`/`v7` pair → `0x2E` (tail
    rest shows the suffix on entry); the front-divergent pair
    (`LX521 …`/`LX521.4 …`) → `0x2F` (prefix rest shows the difference).
3c. **Command coexistence** — `cmd 0x26` is a distinct filename query and does not
    reuse `cmd 0x25`; structural test pins the exact cumulative-XOR dispatch.
    Behavioral test issues `cmd 0x25` before, during, and after a filename burst
    and verifies Diagnostics identity still returns `BF/4F..53`.
3d. **Multi-PB protocol readiness** — common query helper emits
    `[0xB1,0x26,id(target=PB1)]` and `[0xB2,0x26,id(target=PB2)]` with identical
    reply grammar. V1 Preset display schedules PB1 only; PB2 query/probe must not
    require a separate command path.
4. **CONTROL parser/cache** — clean `START+LEN+chars+END` burst →
   VALID/len/cache; char before START ignored; char before LEN aborts; dropped
   char aborts; dropped START/LEN/END never VALID; START+END without LEN never
   VALID; END with `len != expected_len` aborts; BSR=0 into the
   tail (structural). Duplicate `LEN`, late `LEN` after one or more chars, and
   corrupt `LEN` (`id ^ L` where `L > 30`) abort and cannot reseal a shorter
   cache before `END`. **R3-3:** a wrong-id `START` while armed disarms (drops
   ARMED, keeps PENDING) so a following foreign `BF/30…` is not cached; a later
   correct `START` re-arms and validates, otherwise pending deadline blanks.
   Injected non-printable char data aborts. Wrong-id END aborts. Unsolicited
   in-range frames while not pending are ignored. Injected `>=0x80` bytes resolve
   by route-byte/frame-gap behavior, index mismatch, or pending expiry without
   storing garbage. **R3-4 (structural):** the `BF/2D..4E` case is reached after
   the `BF/4F..53` identity parser and before the BF/2x parser's `cmd >= 0x2C`
   exit; lower-bound misses (`cmd < 0x2D`) must fall through to BF/2x, not parser
   tail. Assert START actually validates a burst end-to-end in the chain.
5. **Retry policy** — dropped char / reordered / dropped END / old-MAIN echo →
   empty row via parser abort or pending deadline, no per-tick re-query;
   TX-saturated issue retried until sent; exactly one query per entry/flip
   otherwise. old-MAIN echo must be injected at frame positions 0/1/2, including
   ids `0x2D`, `0x2E`, `0x2F`, and `0x4E`, and including synthetic matching
   START+END without LEN plus adversarial multi-frame stale/old-byte sequences
   that look like `START(id),LEN(id^0),END(id)` but are not a fresh matching
   current query reply; none may finalize.
5b. **Lifecycle reset** — pending/armed/partial-cache burst interrupted by
    standby, wake, PB1 lost, reconnect-wait entry, PB1 reboot, or Preset
    exit/menu navigation calls `fname_reset_blank`; Preset entry, slot flip,
    reconnect-wait completion, or `CONNECTED` set calls `fname_reset_and_query`.
    Periodic `full_sync_burst` must not requery. PB1 stale and PB2-only
    stale/lost update `*` but do not blank PB1 filename. Add separate PB1-stale,
    PB1-lost, PB2-stale, PB2-lost, and Preset-exit-mid-burst tests. Assert no
    stuck `PENDING=1,WANT_QUERY=0` state.
5c. **Reserved range guard** — structural test proves no non-filename sender emits
    `BF/2D..4E`; interleaving tests cover BF/08, BF/21..2C Diagnostics,
    BF/4F..53 identity, status/full-sync, standby/wake/preset, and filename.
    Boundary tests pin `BF/2C` as diagnostics/health and `BF/4F` as identity.
5d. **RAM/deadline safety** — structural test parses actual RAM equates and
    asserts CONTROL filename RAM ranges `0x220..0x244` and `0x255..0x25C` do not
    overlap Diagnostics identity `0x245..0x254`; MAIN filename job cells are
    exactly `0x2F4..0x2FF`, clear on every runtime cold entry, and do not overlap
    diag/reset/frame-gap/recovery/SRC cells `0x2E5..0x2F3`. Deadline test proves
    a max-length paced reply under legal interleaving completes before the 16-bit
    pending countdown expires.
5e. **Listing/code-size safety** — `test_v33_filename_code_size_fits_before_preset_table`
    parses the real V3.3 listing and fails if filename code crosses `org
    0x4C00` or leaves less than 64 bytes of maintenance margin. It also pins
    `preset_table_b == 0x4C00`. A matching CONTROL listing gate parses V1.72,
    pins `control_release_metadata == 0x77B0` and `bootloader_entry == 0x7800`,
    and fails if filename code crosses release metadata or the bootloader window.
5f. **Structural implementation hooks** — tests parse real source/equates/listings
    for `chain_tx_emitted` coverage on all actual MAIN chain send paths:
    `main_uart_service_1be6` parser forward/ACK echo, `send_status_burst`,
    `send_dsp_fault_status`, `cmd21_diag_query_handler`,
    `cmd22_reset_flags_query_handler`, `cmd23_health_query_handler`,
    `cmd25_identity_query_handler`, `report_cmd29_status`, and filename.
    `filename_rev` hook coverage must cover USB filename write,
    `preset_persist_filename`, `preset_load_filename`, and the
    `btg active_flags` + incoming filename load path. Tests also cover the
    globally reserved `BF/2D..4E` emit range and CONTROL/MAIN RAM allocation.
6. **Service placement (R2-1)** — scroll advances and the query issues **while
   idle** on the Preset screen (proves the service is inside
   `display_loop_iteration`, not after the call).
7. **Render** — ≤16 static; >16 scrolls; exact row-0 strings from §1; col 15
   `'!'` on DSP fault else A/B (R2-9); col 14 `'*'` on any stale/lost PB else
   space (R2-8); FSR0/BSR and no clobbered Common RAM live ranges across
   `lcd_*`; RBIF/IR and RCIF traffic during incremental filename rendering does
   not corrupt LCD state or UART parsing.
8. **Health contract (R2-8)** — row-1 health suffix present on Volume, **absent
   on Preset**; compact col-14 glyph present on Preset instead; filename tail
   never overwritten. Update `test_v171_preset_lcd_health_suffix.py`.
9. **Worked example** — repo `artifacts/LX521.4`: a scroll cycle exposes `…-v5`
   (A) vs `…-v7` (B) → distinguishable.
10. **End-to-end full native chain** — paired filename V1.72 × V3.3 × V3.3
    chain; simulate flashing/seeding preset filenames independently for PB1 and
    PB2; flip A↔B
    (slot+gen+target, no stale); blackout → blank; pre-feature peer smoke test →
    empty filename row, no desync. Explicit mismatch test: PB1 A=`FILE_A1`,
    PB2 A=`FILE_A2` → LCD shows PB1 only, no mismatch glyph/error.
    Mixed-version tests cover filename CONTROL + old/pre-feature PB1, filename
    MAIN + old/pre-feature CONTROL, same-version diagnostics-only images, and
    one-side rollback.
10b. **Display combinations** — full chain tests cover prefix-first names,
     tail-first names with shared first 16 chars, ≤16 static names, exactly-16,
     17..30 scrolling, exactly-30, valid blank A/B presets, DSP fault `!`
     precedence, row-0 `*` health refresh, and PB1/PB2 mismatch while PB1 remains
     authoritative.
11. **Preset-screen controls** — while Preset filename row is pending, valid, and
    scrolling, IR, front-panel buttons, standby/wake, volume/mute, and A/B flips
    still dispatch through the existing foreground services.

### Named implementation test specs

These names are the minimum concrete tests to add when implementation starts.
They intentionally include the field/user failure names already used in review
notes so future work can be traced back to this spec.

| proposed test name | expected coverage |
| --- | --- |
| `test_v172_fname_parser_duplicate_len_aborts` | `START,LEN,LEN,END` clears `VALID/PENDING/ARMED`, blanks row 1, and cannot validate. |
| `test_v172_fname_parser_late_len_after_char_aborts` | `START,LEN,char0,LEN,END` aborts; the late `LEN` cannot reseal a truncated cache. |
| `test_v172_fname_parser_corrupt_len_aborts` | `LEN(id ^ 31)` and any `L > 30` abort before chars/END. |
| `test_v172_fname_parser_old_echo_positions_0_1_2_do_not_finalize` | old/pre-feature echo bytes `0x2D/0x2E/0x2F/0x4E` injected at frame positions 0/1/2, including following byte equal to pending id, never produce `VALID` or stuck `ARMED`. |
| `test_v172_fname_parser_interleaved_bf08_identity_diag_preserved` | `BF/08`, `BF/21..2C`, and `BF/4F..53` still route correctly before/during/after filename pending/armed states. |
| `test_v172_fname_parser_old_echo_multiframe_start_len_end_do_not_finalize` / `test_raw_protocol_model_old_echo_multibyte_start_len_end_streams_do_not_finalize` | stale/old-byte sequences that look like `START(id),LEN(id^0),END(id)` but are not a fresh current reply do not validate and normal BF/08/diag/identity routing recovers. |
| `test_v172_fname_cold_init_clears_filename_state_preserves_diag_identity` | seeded `0x220..0x25B` clears only filename cells, preserving `0x245..0x254`. |
| `test_v33_fname_cold_entry_clears_job_state_after_software_reset` | seeded `0x2F4..0x2FF` clears on POR/BOR/software-reset/post-flash handoff. |
| `test_v172_fname_ram_equates_do_not_overlap_diag_identity` | parses real equates/listing, not copied ranges, and rejects any overlap with Diagnostics identity. |
| `test_v33_filename_code_size_fits_before_preset_table` | parses real V3.3 `.lst`; filename code must fit before `org 0x4C00` with margin. |
| `test_v172_filename_code_size_fits_before_bootloader` | parses real V1.72 `.lst`; filename code must not cross release metadata/bootloader space. |
| `test_v33_filename_chain_tx_emitted_coverage_all_chain_senders` | every MAIN chain/status/diag/identity/filename sender sets the pass-local arbitration flag. |
| `test_v33_filename_rev_writer_hooks_cover_all_filename_mutators` | every RAM/EEPROM filename writer bumps `filename_rev` odd/even around mutation. |
| `test_v33_reserved_bf_2d_4e_only_filename_emitters` | only filename reply code emits `BF/2D..4E`; diagnostics/status/identity remain outside the range. |
| `test_v172_fname_row1_incremental_render_writes_one_char_per_tick` | row-1 repaint advances `v172_fname_render_col` one char per visible tick and clears `FNAME_ROW_DIRTY` only after col 15. |
| `test_v172_fname_dirty_paths_reset_render_cursor` | every path that sets `FNAME_ROW_DIRTY` resets `render_col`/`render_off`; abort blanking cannot leave stale prefix chars. |
| `test_v172_fname_preset_exit_cancels_pending_or_armed_query` | leaving Preset mid-query calls `fname_reset_blank` and does not strand global filename state. |
| `test_v172_fname_preset_entry_blanks_old_active_row` | initial Preset paint cannot leave old `Active: A/B` row-1 text visible as a settled state. |
| `test_v172_fname_row1_render_tolerates_ir_rcif_during_pending_valid_scrolling` | IR, RCIF/chain frames, standby/wake, volume/mute, and A/B buttons dispatch during pending, valid static, and scrolling states. |
| `test_v172_preset_row0_live_patch_health_fault_preset_scenarios` | PB1/PB2 stale/lost, DSP fault `!`, A/B flips, and simultaneous health+fault changes produce the tabled row-0 progressions. |
| `test_v172_v33_deployment_uses_cmd25_app_identity_not_usb_eeprom_rev` | flashing/runbook validation rejects stale USB/EEPROM rev evidence and accepts only app-resident `cmd 0x25` chain identity. |
| `test_preset_filename_spec_requires_cmd25_app_resident_identity_for_flash_validation` | spec requires PB1/PB2 chain identity replies, not host-side USB enumeration, before LCD OCR. |
| `test_preset_filename_spec_rejects_usb_eeprom_revision_as_authoritative_marker` | USB/HID version, EEPROM byte `0x82`, and HFD metadata are informational only. |
| `test_preset_filename_spec_documents_pb1_lcd_authority_and_pb2_flash_validation` | PB1 OCR is authoritative, PB2 mismatch is warning-only, and both MAINs are still identity-verified after flash. |
| `test_preset_filename_spec_requires_blank_name_chain_evidence` | blank LCD passes only with fresh `START/LEN(0)/END` capture or prior non-empty gate. |
| `test_preset_filename_spec_defines_hfd_active_ram_vs_inactive_eeprom_validation` | active slot validates RAM on fresh requery; inactive slot validation waits for EEPROM persistence/readback. |
| `test_v172_v33_pb1_authoritative_lcd_with_pb2_mismatch` | PB1 A=`FILE_A1`, PB2 A=`FILE_A2` displays PB1 only; mismatch is optional warning, not LCD failure. |
| `test_v172_v33_full_chain_blank_name_requires_fresh_start_len_end_evidence` | blank row passes only with fresh PB1 query id plus `START/LEN(0)/END` capture or after a prior non-empty gate. |
| `test_preset_filename_row1_dirty_render_initializes_render_cursor` | first dirty render snapshots `v172_fname_render_off`, starts at col 0, writes only one row-1 char, and leaves dirty set. |
| `test_preset_filename_row1_incremental_writer_advances_one_col_per_tick` | every visible Preset tick writes exactly one addressed row-1 char; dirty clears only after col 15. |
| `test_preset_filename_row1_render_uses_snapshot_offset_until_complete` | a repaint that starts at one scroll offset finishes that 16-char window even if `scroll_off` changes mid-render. |
| `test_preset_filename_row1_pending_blank_is_incremental_not_full_clear` | abort/timeout blanking clears one column per tick, not a 16-space full-row write. |
| `test_preset_filename_row1_valid_empty_renders_blank_without_error_text` | valid `L=0` renders 16 spaces, with no loading/error/spinner text. |
| `test_preset_filename_row1_static_name_pads_to_16_and_does_not_scroll` | names shorter than 16 pad with spaces and never schedule scroll. |
| `test_preset_filename_row1_exactly_16_chars_does_not_scroll` | exactly 16 chars render static; no offset 1 scroll step. |
| `test_preset_filename_row1_tail_first_scroll_exact_windows` | LX521.4 `v5/v7` shared-prefix names enter on suffix window, then step toward the head and snap back. |
| `test_preset_filename_row1_prefix_first_scroll_exact_windows` | front-divergent names enter on prefix window, then step toward the tail and snap back. |
| `test_preset_filename_row0_patch_changes_only_cols_14_15` | health/preset/fault changes touch only row-0 cols 14/15 and never overwrite row-1 filename. |
| `test_preset_filename_row0_patch_handles_both_cells_changed` | simultaneous health+fault transition reaches `Preset        *!` over one/two bounded cell patches. |
| `test_preset_filename_pb2_only_stale_updates_star_without_blanking_row1` | PB2-only stale/lost sets `*`; PB1 filename remains valid and visible. |
| `test_preset_filename_pb1_lost_blanks_row1_and_sets_health_star` | PB1 lost blanks/reset row 1 and sets row-0 health `*`. |
| `test_preset_filename_ir_volume_mute_during_pending_render` | IR volume/mute still dispatches while pending blank render is in progress. |
| `test_preset_filename_buttons_during_valid_static_render` | front-panel navigation/select/back still dispatches during static filename render. |
| `test_preset_filename_standby_wake_during_scrolling_render` | standby resets any half-rendered scrolling row; wake/reconnect reissues a fresh query if still on Preset. |
| `test_preset_filename_ab_flip_during_incremental_render_restarts_query` | A render abandoned on A→B flip; B query/gen issued; stale A reply ignored. |
| `test_v172_native_filename_clean_burst_sets_valid_len_cache` | native CONTROL parser accepts only well-formed `START+LEN+chars+END` and caches exact bytes. |
| `test_v172_native_filename_late_len_after_char_aborts_and_blanks` | native CONTROL reproduces the late-LEN bug shape and rejects it. |
| `test_v172_native_filename_duplicate_len_aborts_and_blanks` | native CONTROL rejects duplicate `LEN` before chars. |
| `test_v172_native_filename_len_greater_than_30_aborts` | native CONTROL rejects corrupt `LEN` values whose decoded length exceeds 30. |
| `test_v172_native_filename_wrong_id_start_disarms_keeps_pending` | wrong-id START clears ARMED but keeps PENDING so a later correct START can still validate before deadline. |
| `test_v172_native_parser_old_echo_multiframe_start_len_end_do_not_finalize` | native raw frame parser rejects adversarial old/pre-feature bytes that look like `START(id),LEN(id^0),END(id)` unless tied to the current pending query. |
| `test_v172_native_lcd_row1_abort_valid_end_restart_render_cursor` | native LCD row-1 service proves abort/timeout blanking and valid `END` repaint both restart at col 0 after a partial repaint. |
| `test_v172_native_row0_patch_consumes_lcd_budget_only` | native Preset service drains parser/deadline/query work even when a row-0 patch is pending, and writes at most one LCD cell. |
| `test_v172_v33_fname_foreground_ir_buttons_standby_while_pending_valid_scrolling` | full-chain foreground-service test across pending, valid static, and scrolling phases. |
| `test_v172_v33_native_chain_tail_first_prefix_first_blank_mismatch_cases` | native full chain covers tail-first shared-prefix names, prefix-first divergent names, valid blank A/B, and PB1/PB2 mismatch with PB1 authority. |
| `test_v172_v33_native_chain_mixed_old_new_peers_do_not_finalize` | native full chain covers filename CONTROL + old/pre-feature MAIN, filename MAIN + old/pre-feature CONTROL, diagnostics-only same-version images, and one-side rollback. |
| `test_v172_v33_filename_flash_gate_fails_when_usb_rev_new_but_cmd25_missing` | deployment gate fails if USB/EEPROM looks new but running MAIN app does not answer `cmd 0x25`. |
| `test_v172_v33_hfd_active_slot_rename_uses_ram_on_requery` | active slot HFD rename appears from RAM on fresh query without flipping away. |
| `test_v172_v33_hfd_inactive_slot_validation_waits_for_eeprom_persist` | inactive slot validation waits for EEPROM persistence/readback before flip/OCR. |

Hardware (R2-4/R2-5 — existing harness will **not** work unmodified):

- **OCR (R2-5):** add a **raw ordered row-capture** mode (no template/`Active:`
  normalization, `hardware_lcd_probe.py:324/469`) and a **scroll-reconstruction**
  step that stitches row-1 windows across a scroll cycle into the full name;
  add unit tests for the reconstruction logic against synthetic scroll frames.
- **Gates (R2-4):** the existing front-panel preset gate
  (`tests/hardware/test_live_state_transitions.py:748`) asserts `Active: A|B`,
  which this feature removes — **update it** to read the row-0 col-15 status
  (`'!'`/A/B) so it cannot pass against the old layout. Add a distinct
  `DLCP_HW_PRESET_FILENAME_CONFIRM=1` gate that OCR-reconstructs row 1 across a
  scroll and **fails** unless it spells the expected non-empty PB1 A/B name and
  tracks on A↔B flip. HFD/USB empty-name validation is a separate accepted-blank
  case and must not be used as the positive feature gate. Update
  `docs/HARDWARE_TEST.md:523` + runbook.

---

## 11. Future extensions

Ping-pong / wrap-marquee scroll; PB2 filename display/compare using the already
reserved multi-PB protocol; transient name toast on the Volume screen; one coarse
reply-retry if dropped-reply blanks annoy.

---

## 12. Decisions & open items

Locked by operator: empty not-loaded row; paired `V3.3`/`V1.72` filename builds;
pending deadline blanks without retry; HFD/USB empty names display as blank;
full-name scroll; row-1 LCD rendering is incremental one-char-per-service-tick;
**auto scroll direction = START-command hint** (Option A; §3.5);
PB1-authoritative display in v1 with a multi-PB-ready query id; `cmd 0x26`
query is split from `cmd 0x25` Diagnostics identity.
Resolved across the reviews: slot+generation query; incremental non-blocking
MAIN job; RAM-for-active-slot (mandatory); reply identity (START/END `id`,
target bit in id, START cmd = direction); in-loop service placement; row-0
fault/health zone; corrected parser; OCR/gate changes; 3-flag plus pending-age
blank-without-retry policy.

**Design note — why the 1-bit hint, not a divergence index (Option C).** With a
16-column window, the prefix window `[0,15]` and suffix window `[L-16,L-1]`
together cover every column of any name with `L ≤ 32` (the gap closes once
`L-16 ≤ 16`). The field is `preset_filename_len = 30`, so the first divergence
always lands in one of the two windows: `d < 16` → shown by prefix-first,
`d ≥ 16` → shown by tail-first. The binary "first-16-equal → tail-first" hint is
therefore **provably complete** for this field — no ≤32-char counter-example
exists (verified empirically incl. middle-divergence names). A full divergence
*index* (Option C) is the generalization needed only if `preset_filename_len`
ever exceeds 32; it would ship the index in a new reserved frame and rest
`clamp(d-15,0,max_off)`. Not implemented; revisit only on a name-field grow.

Implementation review note: OCR scroll-reconstruction is implemented in the
hardware probe/runbook path, but exact camera/capture tolerances remain a
hardware gate detail. The compact health glyph is locked for v1 as space =
healthy, `*` = any PB stale/lost.

---

## 13. Worked example (repo default config)

`config_name_raw_hex` from the LX521.4 sidecars (the literal 30-byte EEPROM slot):

```
A: 4c 58 35 32 31 2e 34 20 32 32 4d 47 31 30 46 2d 76 35 | ff ×12   -> L=18, "LX521.4 22MG10F-v5"
B: …………………………………………………………………………………………… 76 37 | ff ×12             "LX521.4 22MG10F-v7"
```

`L=18` (>16) → scroll. A/B share their first 16 chars, so MAIN uses START
`0x2E` and CONTROL rests at the tail first. Preset A visible sequence:

```
off=2  (hold, ENTRY)  row1 |521.4 22MG10F-v5|   row0 |Preset         A|  <- "v5" first
off=1                 row1 |X521.4 22MG10F-v|
off=0  (hold)         row1 |LX521.4 22MG10F-|
```

Selecting B sends `cmd 0x26 data = (gen<<2)|(target=PB1<<1)|1`. MAIN (B not yet
active during apply) reads EEPROM `0x83`, finds A and B share their first 16
chars, uses START `0x2E`, and bursts B's name with START/END identity = `id`.
CONTROL arms on the matching `id`, latches `FNAME_TAILDIR` from START `0x2E`,
and shows B even mid-apply:

```
off=2  (hold, ENTRY)  row1 |521.4 22MG10F-v7|   row0 |Preset         B|  <- "v7" first
off=1                 row1 |X521.4 22MG10F-v|
off=0  (hold)         row1 |LX521.4 22MG10F-|
```

The discriminating suffix is visible the **instant** you land on either preset's
screen (auto tail-first, §3.5). By contrast a front-divergent pair
(`LX521 …`/`LX521.4 …`) gets START `0x2F` → prefix-first, so its difference
shows at the natural start. The row-1 link-health suffix is suppressed on this
screen (it moved to the row-0 col-14 glyph), so the suffix is never clobbered.
