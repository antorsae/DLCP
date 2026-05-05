"""Wire-chain BF/08 MAIN0->CONTROL integration coverage (V1.71 + V3.2).

Re-creates the end-to-end coverage from the deleted
``test_v31_v163b_robustness::test_wire_dsp_fault_reporting`` which
exercised the integration path:

  MAIN0 under I2C NACKs ->
    send_dsp_fault_status emits BF/08/<status_byte> on MAIN0.tx ->
      forward MAIN0.tx -> MAIN1.rx (passthrough) ->
        re-emit MAIN1.tx -> CONTROL.rx ->
          CONTROL parses BF/08 and updates control_flags.bit7.

Both halves are independently covered today:

  * MAIN side -- ``test_v31_v163b_robustness::test_main_dsp_ping_-
    latches_fault_on_persistent_nack`` proves MAIN sets
    0x07F.bit6 under NACKs;
    ``test_v31_review_findings::test_bf08_payload_bytes_on_dsp_-
    fault`` verifies the BF/08 payload bytes on MAIN-only chain.
  * CONTROL side -- ``test_v171_fault_indicator`` injects BF/08
    directly into a CONTROL-only chain and checks the parser
    sets control_flags.bit7.

But the END-TO-END forward across the rust 3-core wire chain
(in particular: the MAIN0->MAIN1->CONTROL passthrough sequence
plus the parser meeting an organically-produced frame rather
than an injected one) was covered only by the deleted test.
A regression in any of those three hops would slip through.
This file restores that gate.

Note on observability: the rust silicon-ring delivers UART
bytes immediately on TXSR shift-out (no bit-level UART timing
modeling per docs/SIMULATION.md).  At 12 MHz CONTROL Tcy a
3-byte BF/08 frame dispatches in ~9 us sim time -- far below
chunk-polling granularity.  In the 3-core ring V3.2 MAIN1
also emits BF/08/0x00 heartbeats on its own TX, so V1.71's
parser races between MAIN0's BF/08/<nz> setting bit7 and
MAIN1's BF/08/0x00 clearing it within a single chunk.  The
PRIMARY assertion is therefore on the BYTE STREAM landing at
CONTROL.rx -- which proves the 3-hop forwarding chain
unambiguously: any break in MAIN0.tx -> MAIN1.rx -> MAIN1.tx
-> CTL.rx forwarding would absent the BF/08/<nz> frame from
CTL.rx, regardless of parser dispatch ordering.  CONTROL-side
parser dispatch on BF/08 is independently covered by
``test_v171_fault_indicator``; integration coverage in this
file specifically gates the wire-chain forwarding.
"""

from __future__ import annotations

import pytest

from dlcp_fw.paths import V171_CONTROL_HEX, V32_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_OK = True
    _RUST_ERR: Exception | None = None
except Exception as exc:  # pragma: no cover - best-effort import
    _RUST_OK = False
    _RUST_ERR = exc


# CONTROL flags byte (V1.71): physical RAM 0x01F.  Bit 7 is the
# DSP_FAULT_BIT toggled by the BF/08 parser case.
_CONTROL_FLAGS_ADDR = 0x01F
_DSP_FAULT_BIT = 7
# Stash slot for the most recent BF/08 payload byte (V1.71's
# bf08_fault_byte at RAM 0x0AB).  Tracks the most recent BF/08
# regardless of zero/nonzero, so it isn't a sticky observable.
_BF08_FAULT_BYTE_ADDR = 0x0AB


def _require_rust() -> None:
    if not _RUST_OK:
        pytest.fail(f"rust dlcp_sim_native facade not importable: {_RUST_ERR!r}")


def _require_canonical_hexes() -> None:
    if not V171_CONTROL_HEX.exists():
        pytest.skip(f"missing canonical V1.71 hex: {V171_CONTROL_HEX}")
    if not V32_MAIN_HEX.exists():
        pytest.skip(f"missing canonical V3.2 hex: {V32_MAIN_HEX}")


def _control_flags(chain) -> int:  # type: ignore[no-untyped-def]
    return int(chain.read_reg(_CONTROL_FLAGS_ADDR))


def _dsp_fault_bit_set(chain) -> bool:  # type: ignore[no-untyped-def]
    return bool(_control_flags(chain) & (1 << _DSP_FAULT_BIT))


def _find_bf08_frames(stream: list[int]) -> list[int]:
    """Return the payload byte of every BF/08 triplet in ``stream``.

    Walks the byte stream and pulls out every contiguous
    ``[0xBF, 0x08, <payload>]`` triplet.  Skips bytes that don't
    align with a frame head.  Used to assert the BF/08 forwarding
    path across the 3-core ring.
    """
    payloads: list[int] = []
    i = 0
    while i + 2 < len(stream):
        if stream[i] == 0xBF and stream[i + 1] == 0x08:
            payloads.append(stream[i + 2] & 0xFF)
            i += 3
        else:
            i += 1
    return payloads


@pytest.mark.dual_supported
@pytest.mark.slow
def test_main0_dsp_nack_drives_bf08_through_wire_chain_to_control() -> None:
    """End-to-end: MAIN0 DSP NACKs -> BF/08/<nz> reaches CONTROL.rx.

    Path under test:
      1. CONTROL boots and reaches CONNECTED.
      2. MAIN0 DSP starts NACKing all addressed accesses.
      3. A B0/07/0x30 DSP-ping command is injected into MAIN0's
         RX FIFO (mirrors the trigger used by the existing
         MAIN-only tests; reproducible regardless of CONTROL's
         heartbeat cadence).
      4. send_dsp_fault_status emits BF/08/<nz> on MAIN0.tx.
      5. MAIN1 receives on its RX, forwards on its TX.
      6. CONTROL.rx accepts the BF/08/<nz> frame.

    The PRIMARY assertion is on the CTL.rx byte stream: any
    break in the 3-hop forwarding chain (MAIN0.tx -> MAIN1.rx,
    MAIN1.tx -> CTL.rx, the rust ring's UART couplings, or
    the executor's RX-FIFO acceptance) would absent the
    BF/08/<nz> frame from CTL.rx and trip the assertion.
    Parser dispatch on BF/08 is independently covered by
    test_v171_fault_indicator.
    """
    _require_rust()
    _require_canonical_hexes()

    chain = RustChain.from_v171_v32()

    chunks = chain.run_until_connected(limit=400)
    assert chunks < 400, (
        f"chain failed to reach CONNECTED within budget; "
        f"lcd={chain.lcd_lines()!r}"
    )

    # Bit7 must be CLEAR pre-fault (nothing's faulted yet).
    assert not _dsp_fault_bit_set(chain), (
        f"DSP_FAULT_BIT pre-fault must be 0; "
        f"control_flags=0x{_control_flags(chain):02X}"
    )

    chain.mark_ctl_rx_capture_point()
    chain.set_i2c_fault("dsp34", address_nack_count=60000)

    # B0/07/0x30 = DSP-ping (Layer 5 enable mask) -- triggers
    # dsp_ping which NACKs all addressed accesses, walks
    # send_dsp_fault_status, emits BF/08/<status> upstream.
    chain.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)

    # Step the chain enough to:
    #   - drain the ping injection (~few ms),
    #   - exhaust the DSP-ping retry budget (~several ms),
    #   - emit BF/08/<nz> on MAIN0.tx,
    #   - forward MAIN0.tx -> MAIN1.rx -> MAIN1.tx -> CTL.rx.
    # 100 chunks of 3.2 M ticks each = 320 M ticks (~6.7 s sim)
    # is well past the worst-case retry+forward latency.
    for _ in range(100):
        chain.step()

    ctl_rx = list(chain.ctl_rx_record_since_last_capture())
    bf08_payloads = _find_bf08_frames(ctl_rx)
    nonzero_bf08 = [p for p in bf08_payloads if p != 0]

    assert bf08_payloads, (
        f"no BF/08 frames reached CONTROL.rx after MAIN0 DSP "
        f"NACK; the 3-hop forwarding chain "
        f"(MAIN0.tx -> MAIN1.rx -> MAIN1.tx -> CTL.rx) is "
        f"broken.  CTL.rx bytes: "
        f"{[f'{b:02x}' for b in ctl_rx[:50]]}"
    )
    assert nonzero_bf08, (
        f"only BF/08/0x00 (clean-status) frames reached CTL.rx; "
        f"MAIN0 either didn't dispatch send_dsp_fault_status or "
        f"the wire-chain dropped the non-zero frame.  Saw "
        f"BF/08 payloads: {[f'0x{p:02x}' for p in bf08_payloads]}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_clean_dsp_chain_does_not_set_control_dsp_fault_bit() -> None:
    """Negative gate: a healthy 3-core ring keeps bit7 clear.

    With both MAINs' DSPs healthy, MAIN1's BF/08/0x00 heartbeat
    keeps streaming clean-status frames to CONTROL.  CONTROL's
    BF/08 parser must keep bit7 cleared throughout.

    This guards against the parser's BF/08/0x00 case incorrectly
    SETTING the bit (a regression that would mute CONTROL into
    the 'fault' indicator state on a healthy chain).
    """
    _require_rust()
    _require_canonical_hexes()

    chain = RustChain.from_v171_v32()

    chunks = chain.run_until_connected(limit=400)
    assert chunks < 400, "chain failed to reach CONNECTED"

    # Run a few hundred ms past CONNECTED so MAIN1's BF/08/0x00
    # heartbeat has fired multiple times.  bit7 must stay clear.
    for _ in range(80):
        chain.step()
        assert not _dsp_fault_bit_set(chain), (
            f"DSP_FAULT_BIT set on a healthy chain; "
            f"control_flags=0x{_control_flags(chain):02X}"
        )
