# HFD v2.12 `R-L` Binary Patch Plan (Byte-Level)

Target:
- `firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe`

Goal:
- Add a 5th routing option (`R-L`) in each channel routing combo in HFD v2.12.
- Keep existing `Left`, `Right`, `L+R/Mid`, `L-R/Side` behavior unchanged.

Assumption:
- MAIN firmware already accepts route value `4` and maps it to `R-L`.

## One-command deterministic patcher

Primary flow (recommended):

```bash
python3 scripts/patch_hfd_v212_rl.py
```

Default output:
- `firmware/patched/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12-RL.exe`

This script enforces:
- input SHA-256 check against the known v2.12 binary;
- strict pre-assertions on all patched byte ranges;
- strict post-assertions, including `call rel32` destination validation;
- deterministic output SHA-256 check.

## Strategy

Patch six per-channel combo init blocks to call tiny stubs in a code cave.
Each stub appends one extra item (`"R-L"`) to the current combo list, then
executes the original replaced instruction (`mov eax, [ebx+offset]`).

This avoids resizing code blocks and keeps all existing control flow intact.

## Section Mapping

- PE `CODE` section:
  - file offset: `0x00000400`
  - VA: `0x00401000`
  - raw size: `0x00164C00`
- Free cave confirmed near end of CODE:
  - usable start: `VA 0x565AF0` (`file 0x164EF0`)
  - cave end: `VA 0x565BFF` (`file 0x164FFF`)

## Patch Set A: Hook 6 call sites

Replace the 6-byte `mov eax, [ebx+X]` instructions with `call rel32` + `nop`.

1.
- VA: `0x5506B0` (`file 0x14FAB0`)
- Original: `8B 83 14 03 00 00`
- New: `E8 3B 54 01 00 90`
- Calls stub at `0x565AF0`

2.
- VA: `0x5507F1` (`file 0x14FBF1`)
- Original: `8B 83 18 03 00 00`
- New: `E8 19 53 01 00 90`
- Calls stub at `0x565B0F`

3.
- VA: `0x550932` (`file 0x14FD32`)
- Original: `8B 83 1C 03 00 00`
- New: `E8 F7 51 01 00 90`
- Calls stub at `0x565B2E`

4.
- VA: `0x550A73` (`file 0x14FE73`)
- Original: `8B 83 20 03 00 00`
- New: `E8 D5 50 01 00 90`
- Calls stub at `0x565B4D`

5.
- VA: `0x550BB4` (`file 0x14FFB4`)
- Original: `8B 83 24 03 00 00`
- New: `E8 B3 4F 01 00 90`
- Calls stub at `0x565B6C`

6.
- VA: `0x550CF5` (`file 0x1500F5`)
- Original: `8B 83 28 03 00 00`
- New: `E8 91 4E 01 00 90`
- Calls stub at `0x565B8B`

## Patch Set B: Code cave payload

Write 190 bytes at:
- VA `0x565AF0` (`file 0x164EF0`)

Payload layout:
- `0x565AF0` stub for combo field `+0x314`
- `0x565B0F` stub for combo field `+0x318`
- `0x565B2E` stub for combo field `+0x31C`
- `0x565B4D` stub for combo field `+0x320`
- `0x565B6C` stub for combo field `+0x324`
- `0x565B8B` stub for combo field `+0x328`
- `0x565BAC` ASCII string: `52 2D 4C 00` (`"R-L\0"`)

Each stub does:
1. Load combo object from `[ebx+offset]`.
2. Load its list object from `[eax+0x214]`.
3. Call list add method (`[vtable+0x38]`) with `edx = 0x565BAC`.
4. Restore `eax = [ebx+offset]` to preserve original semantics.
5. `ret`.

Full cave payload (hex):
```text
538b83140300008b8014020000baac5b56008b08ff51385b8b8314030000c353
8b83180300008b8014020000baac5b56008b08ff51385b8b8318030000c3538b
831c0300008b8014020000baac5b56008b08ff51385b8b831c030000c3538b83
200300008b8014020000baac5b56008b08ff51385b8b8320030000c3538b8324
0300008b8014020000baac5b56008b08ff51385b8b8324030000c3538b832803
00008b8014020000baac5b56008b08ff51385b8b8328030000c3522d4c00
```

## Reproducible patch procedure (shell)

```bash
cp 'firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe' \
   /tmp/HFD_v2.12.RL.exe

# Hook sites
printf '\xE8\x3B\x54\x01\x00\x90' | dd of=/tmp/HFD_v2.12.RL.exe bs=1 seek=$((0x14FAB0)) conv=notrunc
printf '\xE8\x19\x53\x01\x00\x90' | dd of=/tmp/HFD_v2.12.RL.exe bs=1 seek=$((0x14FBF1)) conv=notrunc
printf '\xE8\xF7\x51\x01\x00\x90' | dd of=/tmp/HFD_v2.12.RL.exe bs=1 seek=$((0x14FD32)) conv=notrunc
printf '\xE8\xD5\x50\x01\x00\x90' | dd of=/tmp/HFD_v2.12.RL.exe bs=1 seek=$((0x14FE73)) conv=notrunc
printf '\xE8\xB3\x4F\x01\x00\x90' | dd of=/tmp/HFD_v2.12.RL.exe bs=1 seek=$((0x14FFB4)) conv=notrunc
printf '\xE8\x91\x4E\x01\x00\x90' | dd of=/tmp/HFD_v2.12.RL.exe bs=1 seek=$((0x1500F5)) conv=notrunc

# Cave payload
printf '\x53\x8b\x83\x14\x03\x00\x00\x8b\x80\x14\x02\x00\x00\xba\xac\x5b\x56\x00\x8b\x08\xff\x51\x38\x5b\x8b\x83\x14\x03\x00\x00\xc3\x53\x8b\x83\x18\x03\x00\x00\x8b\x80\x14\x02\x00\x00\xba\xac\x5b\x56\x00\x8b\x08\xff\x51\x38\x5b\x8b\x83\x18\x03\x00\x00\xc3\x53\x8b\x83\x1c\x03\x00\x00\x8b\x80\x14\x02\x00\x00\xba\xac\x5b\x56\x00\x8b\x08\xff\x51\x38\x5b\x8b\x83\x1c\x03\x00\x00\xc3\x53\x8b\x83\x20\x03\x00\x00\x8b\x80\x14\x02\x00\x00\xba\xac\x5b\x56\x00\x8b\x08\xff\x51\x38\x5b\x8b\x83\x20\x03\x00\x00\xc3\x53\x8b\x83\x24\x03\x00\x00\x8b\x80\x14\x02\x00\x00\xba\xac\x5b\x56\x00\x8b\x08\xff\x51\x38\x5b\x8b\x83\x24\x03\x00\x00\xc3\x53\x8b\x83\x28\x03\x00\x00\x8b\x80\x14\x02\x00\x00\xba\xac\x5b\x56\x00\x8b\x08\xff\x51\x38\x5b\x8b\x83\x28\x03\x00\x00\xc3\x52\x2d\x4c\x00' \
  | dd of=/tmp/HFD_v2.12.RL.exe bs=1 seek=$((0x164EF0)) conv=notrunc
```

## Verification checklist

1. Confirm six hook sites:
- `xxd -g 1 -s 0x14fab0 -l 6 /tmp/HFD_v2.12.RL.exe`
- `xxd -g 1 -s 0x14fbf1 -l 6 /tmp/HFD_v2.12.RL.exe`
- `xxd -g 1 -s 0x14fd32 -l 6 /tmp/HFD_v2.12.RL.exe`
- `xxd -g 1 -s 0x14fe73 -l 6 /tmp/HFD_v2.12.RL.exe`
- `xxd -g 1 -s 0x14ffb4 -l 6 /tmp/HFD_v2.12.RL.exe`
- `xxd -g 1 -s 0x1500f5 -l 6 /tmp/HFD_v2.12.RL.exe`

2. Confirm cave payload start and string tail:
- `xxd -g 1 -s 0x164ef0 -l 0xc0 /tmp/HFD_v2.12.RL.exe`
- `xxd -g 1 -s 0x164fac -l 4 /tmp/HFD_v2.12.RL.exe` should be `52 2d 4c 00`.

3. Runtime smoke test:
- Launch patched HFD.
- Verify each channel routing combo has 5 items.
- Select `R-L` and push config.
- Read back from device: value should persist as route `4`.

## Notes / Risks

- This patch is static and does not modify PE headers or section sizes.
- It relies on an in-section code cave (`0x565AF0..0x565BFF`) being unused.
- If this constructor function is ever re-entered for existing combo instances,
  `R-L` could be appended again. In observed flow this block is setup-time; if
  needed, add a one-shot guard byte in cave in a follow-up revision.
