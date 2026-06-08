#!/usr/bin/env python3
"""Visual mockup of the CONTROL Preset-screen filename scroll.

Implements the exact scroll state machine from
``docs/PRESET_FILENAME_LCD_SPEC.md`` §7 (pause-at-start -> step left-to-right
one char per step -> pause-at-end -> SNAP back to start -> repeat) so you can
judge readability and whether the LX521.4 ``-v5`` / ``-v7`` suffix is
distinguishable at end-of-travel.

Two modes:
  * default        : live side-by-side curses animation (preset A vs B).
  * --plain        : print the distinct frames of one scroll cycle as text
                     (no TTY needed; good for a quick look / logs).

The LCD is 16x2.  Row 0 = "Preset" + spaces + status@col15 ('!' on DSP fault,
else A/B); col14 would carry a compact link-health glyph when a PB link is
stale (off here).  Row 1 = the filename window, scrolled.

Examples:
  python3 scripts/preset_filename_lcd_mockup.py            # live animation
  python3 scripts/preset_filename_lcd_mockup.py --plain    # text frame dump
  python3 scripts/preset_filename_lcd_mockup.py --tail-first --plain   # suffix-first
  python3 scripts/preset_filename_lcd_mockup.py --step-ms 250 --hold-steps 6
  python3 scripts/preset_filename_lcd_mockup.py --name-a "LX521.4 22MG10F-v5" \
                                                --name-b "Some Other Tuning vB"
"""

from __future__ import annotations

import argparse
import time

LCD_W = 16  # 16x2 character LCD

# Defaults: the repo's baked LX521.4 captures (artifacts/LX521.4/*.json
# config_name).  18 chars, differing only in the final char.
DEFAULT_NAME_A = "LX521.4 22MG10F-v5"
DEFAULT_NAME_B = "LX521.4 22MG10F-v7"


def sanitize(name: str) -> str:
    """MAIN-side clamp: printable ASCII only, stop at first non-printable.

    Mirrors the spec's effective-length rule (0xFF/0x00/control terminate the
    name) and the per-byte clamp.  Returns the transmitted character run.
    """
    out = []
    for ch in name:
        o = ord(ch)
        if 0x20 <= o <= 0x7E:
            out.append(ch)
        else:
            break
    return "".join(out)


def divergence_index(name_a: str, name_b: str):
    """First index where A and B differ (Option C hint MAIN computes).

    Returns the index, or None if one name is identical-and-same-length to the
    other (no divergence).  If one is a strict prefix of the other, the
    divergence is at the shorter length.
    """
    ba, bb = sanitize(name_a), sanitize(name_b)
    n = min(len(ba), len(bb))
    for i in range(n):
        if ba[i] != bb[i]:
            return i
    return n if len(ba) != len(bb) else None


class ScrollState:
    """Faithful port of the spec §7 row-1 scroll machine, both directions.

    Holds at the rest end and the far end, single-steps in between, then SNAPS
    back to the rest end.  ``tick()`` advances one logical step-period and
    returns the offset to display until the next tick.

    prefix-first (spec default): rest=head (off 0)  -> step right -> far=tail.
    tail-first   (--tail-first): rest=tail (off max) -> step left  -> far=head.
    divergence   (--auto-divergence / Option C): rest so the differing column
                 (index ``divergence``) sits at the right edge, then scroll
                 toward the farther end.  Subsumes both above:
                   d < 16        -> rest_off 0   (prefix-first)
                   d >= tail     -> rest_off max (tail-first)
                   in between    -> a middle rest showing the divergence.
    """

    def __init__(self, name_len: int, end_hold_steps: int, tail_first: bool = False,
                 divergence=None):
        self.max_off = max(0, name_len - LCD_W)
        self.end_hold = end_hold_steps
        self.tail_first = tail_first
        if divergence is not None:
            # rest so column `divergence` is the rightmost visible cell
            self.rest_off = max(0, min(divergence - (LCD_W - 1), self.max_off))
        elif tail_first:
            self.rest_off = self.max_off
        else:
            self.rest_off = 0
        # scroll toward the farther end so the most text is revealed
        if self.rest_off * 2 <= self.max_off:
            self.far_off, self.dir = self.max_off, +1
        else:
            self.far_off, self.dir = 0, -1
        self.off = self.rest_off
        self.hold = end_hold_steps  # pause at the rest end on (re)validate

    @property
    def scrolls(self) -> bool:
        return self.max_off > 0

    def tick(self) -> int:
        if not self.scrolls:
            return 0
        if self.hold > 0:
            self.hold -= 1
            return self.off
        if self.off != self.far_off:
            self.off += self.dir
            if self.off == self.far_off:
                self.hold = self.end_hold  # pause at the far end
        else:
            self.off = self.rest_off  # SNAP back to the rest end
            self.hold = self.end_hold  # pause at the rest end
        return self.off

    def phase(self) -> str:
        if not self.scrolls:
            return "static"
        if self.off == 0:
            return "HOLD head"
        if self.off == self.max_off:
            return "HOLD tail"
        return "scroll"


def render(letter: str, name: str, off: int, *, dsp_fault: bool = False) -> tuple[str, str]:
    """Return (row0, row1) as exact 16-char strings."""
    body = sanitize(name)
    # Row 1: the 16-char window starting at off, space-padded.
    window = (body[off:off + LCD_W]).ljust(LCD_W)[:LCD_W]
    # Row 0: "Preset" + fill + status@15 (col14 = health glyph, off here).
    status = "!" if dsp_fault else letter
    row0 = ("Preset".ljust(LCD_W - 1))[:LCD_W - 1] + status
    return row0, window


def diff_columns(a: str, b: str) -> list[int]:
    return [i for i in range(min(len(a), len(b))) if a[i] != b[i]]


# --------------------------------------------------------------------------
# Plain (non-TTY) mode
# --------------------------------------------------------------------------
def run_plain(name_a: str, name_b: str, end_hold_steps: int,
              tail_first: bool = False, divergence=None) -> None:
    body_a, body_b = sanitize(name_a), sanitize(name_b)
    sa = ScrollState(len(body_a), end_hold_steps, tail_first, divergence)
    sb = ScrollState(len(body_b), end_hold_steps, tail_first, divergence)

    if divergence is not None:
        mode = f"auto-divergence (Option C; rest on differing column d={divergence})"
    elif tail_first:
        mode = "tail-first (rest at the tail; suffix shown on entry)"
    else:
        mode = "prefix-first (spec §7 default)"
    print(f"Preset A name : {name_a!r}  (effective {len(body_a)} chars)")
    print(f"Preset B name : {name_b!r}  (effective {len(body_b)} chars)")
    print(f"LCD           : {LCD_W}x2   scroll={'yes' if sa.scrolls else 'no (fits)'}")
    print(f"Model         : {mode}")
    print("                hold rest -> step -> hold far -> SNAP back to rest\n")

    def box(letter: str, row0: str, row1: str) -> list[str]:
        return [
            "+" + "-" * LCD_W + "+",
            "|" + row0 + "|",
            "|" + row1 + "|",
            "+" + "-" * LCD_W + "+",
        ]

    # Walk one full cycle of A: collect distinct frames until A returns to its
    # rest offset after moving.  (A and B share max_off in realistic cases, so
    # they advance in lockstep; B is driven independently for generality.)
    seen = []
    last = None
    start_off = sa.off
    moved = False
    for _ in range(2000):
        frame = (sa.off, sb.off, sa.phase(), sb.phase())
        if frame != last:
            seen.append(frame)
            last = frame
        prev = sa.off
        sa.tick()
        sb.tick()
        if sa.off != prev:
            moved = True
        if moved and sa.off == start_off:
            break

    step = 0
    for (oa, ob, pa, pb) in seen:
        r0a, r1a = render("A", name_a, oa)
        r0b, r1b = render("B", name_b, ob)
        ba, bb = box("A", r0a, r1a), box("B", r0b, r1b)
        dur = "~hold" if ("HOLD" in pa or "HOLD" in pb) else "~1 step"
        print(f"[t{step}]  A off={oa} ({pa:<10})   B off={ob} ({pb:<10})   {dur}")
        lead, between = "  ", "    "
        for la, lb in zip(ba, bb):
            print(f"{lead}{la}{between}{lb}")
        # underline differing row-1 columns, positioned under the real cells
        diffs = diff_columns(r1a, r1b)
        if diffs:
            cell_a0 = len(lead) + 1                                   # after "  |"
            cell_b0 = len(lead) + 1 + LCD_W + 1 + len(between) + 1    # after A box + gap + "|"
            width = len(lead) + (LCD_W + 2) + len(between) + (LCD_W + 2)
            under = [" "] * width
            for i in diffs:
                under[cell_a0 + i] = "^"
                under[cell_b0 + i] = "^"
            print("".join(under) + "   <- displayed rows differ here")
        else:
            print("  (A and B show identical text in this window)")
        print()
        step += 1

    common = 0
    for x, y in zip(body_a, body_b):
        if x == y:
            common += 1
        else:
            break
    minlen = min(len(body_a), len(body_b))
    if common < minlen:
        diverge = (f"first differ at index {common}: "
                   f"{body_a[common]!r} vs {body_b[common]!r}")
    else:
        diverge = "one name is a prefix of the other"
    mode_lbl = "tail-first" if tail_first else "prefix-first"
    print(f"Summary [{mode_lbl}]:")
    print(f"  full names share the first {common} char(s); {diverge}.")
    print(f"  A {'scrolls' if sa.scrolls else 'fits in 16 — static'}; "
          f"B {'scrolls' if sb.scrolls else 'fits in 16 — static'}.")
    print("  a divergence near the FRONT reads soonest in prefix-first; near the")
    print("  TAIL (e.g. -v5/-v7) it reads soonest in --tail-first.")


# --------------------------------------------------------------------------
# Curses (live animation) mode
# --------------------------------------------------------------------------
def run_curses(name_a: str, name_b: str, step_ms: int, end_hold_steps: int,
               tail_first: bool = False, divergence=None) -> None:
    import curses

    def main(stdscr: "curses._CursesWindow") -> None:
        curses.curs_set(0)
        stdscr.nodelay(True)
        have_color = curses.has_colors()
        if have_color:
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)   # LCD text
            curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # differing cell
            curses.init_pair(3, curses.COLOR_CYAN, -1)                    # labels
        LCD = curses.color_pair(1) if have_color else curses.A_NORMAL
        HOT = (curses.color_pair(2) | curses.A_BOLD) if have_color else curses.A_REVERSE
        LBL = curses.color_pair(3) if have_color else curses.A_BOLD

        sa = ScrollState(len(sanitize(name_a)), end_hold_steps, tail_first, divergence)
        sb = ScrollState(len(sanitize(name_b)), end_hold_steps, tail_first, divergence)
        cur_step_ms = max(20, step_ms)
        paused = False
        last_tick = time.monotonic()

        def draw_lcd(y: int, x: int, letter: str, name: str, off: int, other_off: int,
                     other_name: str) -> None:
            r0, r1 = render(letter, name, off)
            o0, o1 = render("?", other_name, other_off)
            diffs = set(diff_columns(r1, o1))
            border = "+" + "-" * LCD_W + "+"
            stdscr.addstr(y, x, border, LBL)
            stdscr.addstr(y + 3, x, border, LBL)
            for ry, row in ((y + 1, r0), (y + 2, r1)):
                stdscr.addstr(ry, x, "|", LBL)
                for i, ch in enumerate(row):
                    attr = LCD
                    if ry == y + 2 and i in diffs:
                        attr = HOT
                    stdscr.addstr(ry, x + 1 + i, ch, attr)
                stdscr.addstr(ry, x + 1 + LCD_W, "|", LBL)

        while True:
            step_s = cur_step_ms / 1000.0
            now = time.monotonic()
            if not paused and now - last_tick >= step_s:
                sa.tick()
                sb.tick()
                last_tick = now

            mode = ("auto-div" if divergence is not None
                    else ("tail-first" if tail_first else "prefix-first"))
            stdscr.erase()
            stdscr.addstr(0, 2, f"CONTROL Preset-screen filename scroll  [{mode}]", LBL)
            stdscr.addstr(1, 2, "yellow = columns where A and B differ "
                                "(the -v5 / -v7 tail)", LBL)
            draw_lcd(3, 4, "A", name_a, sa.off, sb.off, name_b)
            stdscr.addstr(3 + 4, 4 + 1, f"Preset A  off={sa.off}  {sa.phase()}", LBL)
            draw_lcd(3, 4 + LCD_W + 8, "B", name_b, sb.off, sa.off, name_a)
            stdscr.addstr(3 + 4, 4 + LCD_W + 8 + 1, f"Preset B  off={sb.off}  {sb.phase()}", LBL)

            stdscr.addstr(10, 2, f"step={cur_step_ms}ms  hold={end_hold_steps} steps   "
                                 f"[{'PAUSED' if paused else 'running'}]", LBL)
            stdscr.addstr(11, 2, "keys:  q quit   space pause   + faster   - slower", LBL)
            stdscr.refresh()

            try:
                c = stdscr.getch()
            except curses.error:
                c = -1
            if c in (ord("q"), ord("Q"), 27):
                break
            if c == ord(" "):
                paused = not paused
            elif c in (ord("+"), ord("=")):
                cur_step_ms = max(20, int(cur_step_ms * 0.8))
            elif c in (ord("-"), ord("_")):
                cur_step_ms = min(2000, int(cur_step_ms * 1.25) + 1)
            time.sleep(0.02)

    try:
        curses.wrapper(main)
    except Exception as exc:  # surface a friendly hint instead of a traceback
        raise SystemExit(
            f"curses animation failed ({exc}). Try a real terminal, or use "
            f"--plain for a text frame dump."
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plain", action="store_true",
                    help="print the scroll frames as text (no TTY needed)")
    ap.add_argument("--name-a", default=DEFAULT_NAME_A)
    ap.add_argument("--name-b", default=DEFAULT_NAME_B)
    ap.add_argument("--step-ms", type=int, default=320,
                    help="ms per scroll step (curses mode; spec target ~300)")
    ap.add_argument("--hold-steps", type=int, default=5,
                    help="rest/far pause length in steps (~1.5s at 300ms)")
    ap.add_argument("--tail-first", action="store_true",
                    help="rest on the tail (suffix shown on entry), scroll left "
                         "to reveal the prefix, snap back to tail")
    ap.add_argument("--auto", action="store_true",
                    help="auto-pick (binary): tail-first iff A and B share their "
                         "first 16 chars. Needs BOTH names.")
    ap.add_argument("--auto-divergence", action="store_true",
                    help="Option C: rest the window on the MAIN-computed A/B "
                         "divergence column (subsumes prefix/tail-first; correct "
                         "for front, tail AND middle divergence). Needs BOTH names.")
    args = ap.parse_args()

    tail_first = args.tail_first
    divergence = None
    if args.auto_divergence:
        divergence = divergence_index(args.name_a, args.name_b)
        ba, bb = sanitize(args.name_a), sanitize(args.name_b)
        if divergence is None:
            print("[auto-div]  names identical -> no divergence; rest_off = 0\n")
        else:
            ca = ba[divergence] if divergence < len(ba) else "<end>"
            cb = bb[divergence] if divergence < len(bb) else "<end>"
            print(f"[auto-div]  MAIN divergence index d = {divergence}  "
                  f"(A[{divergence}]={ca!r} vs B[{divergence}]={cb!r})")
            print(f"[auto-div]  CONTROL rest_off = clamp(d-{LCD_W-1}, 0, max_off) "
                  f"-> differing column at the right edge\n")
    elif args.auto:
        ha, hb = sanitize(args.name_a)[:LCD_W], sanitize(args.name_b)[:LCD_W]
        tail_first = ha == hb
        print(f"[auto]  head A = {ha!r}")
        print(f"[auto]  head B = {hb!r}")
        print(f"[auto]  first {LCD_W} chars equal? {ha == hb}  ->  "
              f"{'TAIL-first' if tail_first else 'PREFIX-first'}\n")

    if args.plain:
        run_plain(args.name_a, args.name_b, args.hold_steps, tail_first, divergence)
    else:
        run_curses(args.name_a, args.name_b, args.step_ms, args.hold_steps,
                   tail_first, divergence)


if __name__ == "__main__":
    main()
