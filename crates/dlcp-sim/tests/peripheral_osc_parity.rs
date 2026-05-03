//! P2.9 / FID-08 Oscillator subsystem parity gate.
//!
//! Tests:
//!   1. universal-clock conversion factor per variant
//!      matches the spec's 48 MHz LCM derivation.
//!   2. OSCCON / RCON.IPEN POR values from the K20_POR
//!      table land correctly through apply_reset.
//!   3. loaded DLCP CONFIG bytes drive current ticks/Tcy.
//!   4. OSCCON.SCS/IRCF writes change clock state only after
//!      the oscillator model's deterministic ready interval.
//!   5. OSCCON.OSTS/IOFS are owned by oscillator state, not by
//!      ordinary software writes.

use dlcp_sim::chain::Chain;
use dlcp_sim::core::{Core, CoreLoadOptions, core_from_hex_image};
use dlcp_sim::hex::HexImage;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::osc::{
    ClockSource, HFINTOSC_READY_DELAY_TCY, OSC_SWITCH_DELAY_TCY, ticks_per_tcy,
};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::scheduler::EventKind;
use dlcp_sim::stack::Stack;
use std::path::PathBuf;

const OSCCON_ADDR: u16 = 0xFD3;
const RCON_ADDR: u16 = 0xFD0;
const OSCTUNE_ADDR: u16 = 0xF9B;
const OSCCON_OSTS: u8 = 0x08;
const OSCCON_IOFS: u8 = 0x04;

fn release_path(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join("firmware/patched/releases")
        .join(name)
}

#[test]
fn k20_universal_factor_is_16() {
    assert_eq!(ticks_per_tcy(Variant::Pic18F25K20), 16);
}

#[test]
fn pic2455_universal_factor_is_12() {
    assert_eq!(ticks_per_tcy(Variant::Pic18F2455), 12);
}

#[test]
fn k20_osccon_por_value_from_k20_por_table() {
    let mut core = Core::new(Variant::Pic18F25K20);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    // K20_POR sets OSCCON = 0x30 (DS Tbl 4-4 base
    // `0011 qq00`; the GPSIM_K20_DEVIATIONS table in the
    // V1.71 parity test exempts the gpsim-side 0x40
    // base-class initial value).
    assert_eq!(core.memory.read_raw(Address::from_raw(OSCCON_ADDR)), 0x30);
}

#[test]
fn rcon_por_value_includes_ri_to_pd() {
    // Per Tbl 4-4 RCON `0q-1 11q0`: RI=1 (bit 4), TO=1 (bit
    // 3), PD=1 (bit 2) at POR.  apply_reset's POR arm
    // composes RCON_RI | RCON_TO | RCON_PD = 0x1C and writes
    // it to memory after the SFR-window pass.
    let mut core = Core::new(Variant::Pic18F25K20);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
    let rcon = core.memory.read_raw(Address::from_raw(RCON_ADDR));
    assert_eq!(rcon, 0x1C);
}

#[test]
fn por_does_not_panic_on_either_variant() {
    let mut k20 = Core::new(Variant::Pic18F25K20);
    let mut s = Stack::new();
    apply_reset(&mut k20, &mut s, ResetSource::PowerOn);
    let mut p2455 = Core::new(Variant::Pic18F2455);
    let mut s2 = Stack::new();
    apply_reset(&mut p2455, &mut s2, ResetSource::PowerOn);
}

#[test]
fn loaded_dlcp_configs_drive_known_clock_factors() {
    // §11c FID-08: CONFIG1H/FOSC and CONFIG1L/CPUDIV must feed
    // the oscillator model.  Datasheet anchors: DS40001303H §2.2
    // primary clock source is selected by CONFIG1H/FOSC, and
    // DS39632E §2.2.5.4 documents 2455 PLL + CPUDIV derivation.
    let control_image = HexImage::from_hex_path(release_path("DLCP_Control_V1.71.hex"))
        .expect("V1.71 CONTROL release must load");
    let control = core_from_hex_image(
        Variant::Pic18F25K20,
        &control_image,
        CoreLoadOptions::default(),
    );
    assert_eq!(control.config.raw()[1], 0x01, "V1.71 FOSC=XT");
    assert_eq!(control.peripherals.osc.ticks_per_tcy(), 16);
    assert_eq!(control.ticks_per_tcy(), 16);

    let main_image = HexImage::from_hex_path(release_path("DLCP_Firmware_V3.2.hex"))
        .expect("V3.2 MAIN release must load");
    let main = core_from_hex_image(Variant::Pic18F2455, &main_image, CoreLoadOptions::default());
    assert_eq!(main.config.raw()[0], 0x3A, "V3.2 PLLDIV/CPUDIV");
    assert_eq!(main.config.raw()[1], 0x46, "V3.2 FOSC=ECPIO");
    assert_eq!(main.peripherals.osc.ticks_per_tcy(), 12);
    assert_eq!(main.ticks_per_tcy(), 12);
}

#[test]
fn scs_internal_switch_changes_clock_after_ready_delay() {
    // §11c FID-08: OSCCON.SCS selects the internal oscillator,
    // IRCF selects its frequency, and IOFS rises only after the
    // oscillator has stabilized.  DS40001303H §2.2.1/2.2.2/2.2.4
    // define SCS, IRCF and IOFS; DS39632E has the same contract
    // in Register 2-2 for the 2455.
    let mut core = Core::new(Variant::Pic18F25K20);
    core.memory.write_raw(Address::from_raw(OSCCON_ADDR), 0x32); // IRCF=1 MHz, SCS=internal
    core.peripherals
        .osc
        .on_sfr_write(OSCCON_ADDR, 0x32, &mut core.memory);

    assert_eq!(core.peripherals.osc.current_source(), ClockSource::Primary);
    assert_eq!(core.peripherals.osc.ticks_per_tcy(), 16);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(OSCCON_ADDR)) & (OSCCON_OSTS | OSCCON_IOFS),
        0
    );

    core.peripherals
        .osc
        .tick_tcy(HFINTOSC_READY_DELAY_TCY - 1, &mut core.memory);
    assert_eq!(core.peripherals.osc.current_source(), ClockSource::Primary);
    assert_eq!(core.peripherals.osc.ticks_per_tcy(), 16);

    core.peripherals.osc.tick_tcy(1, &mut core.memory);
    assert_eq!(core.peripherals.osc.current_source(), ClockSource::Internal);
    assert_eq!(core.peripherals.osc.ticks_per_tcy(), 192);
    let osccon = core.memory.read_raw(Address::from_raw(OSCCON_ADDR));
    assert_eq!(osccon & OSCCON_OSTS, 0);
    assert_eq!(osccon & OSCCON_IOFS, OSCCON_IOFS);
}

#[test]
fn oscillator_owns_osts_iofs_transitions() {
    // §11c FID-08: OSCCON.OSTS and IOFS are hardware status
    // bits.  DS39632E Register 2-2 marks them read-only; software
    // writes may request SCS/IRCF, but the oscillator state
    // machine decides when the status bits rise.
    let mut core = Core::new(Variant::Pic18F25K20);
    core.memory.write_raw(
        Address::from_raw(OSCCON_ADDR),
        0x32 | OSCCON_OSTS | OSCCON_IOFS,
    );
    core.peripherals.osc.on_sfr_write(
        OSCCON_ADDR,
        0x32 | OSCCON_OSTS | OSCCON_IOFS,
        &mut core.memory,
    );
    assert_eq!(
        core.memory.read_raw(Address::from_raw(OSCCON_ADDR)) & (OSCCON_OSTS | OSCCON_IOFS),
        0,
        "software cannot force OSTS/IOFS high during a pending switch"
    );
    core.peripherals
        .osc
        .tick_tcy(HFINTOSC_READY_DELAY_TCY, &mut core.memory);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(OSCCON_ADDR)) & (OSCCON_OSTS | OSCCON_IOFS),
        OSCCON_IOFS,
        "internal HF clock completion sets IOFS only"
    );

    core.memory.write_raw(Address::from_raw(OSCCON_ADDR), 0x30); // SCS=primary
    core.peripherals
        .osc
        .on_sfr_write(OSCCON_ADDR, 0x30, &mut core.memory);
    core.peripherals
        .osc
        .tick_tcy(OSC_SWITCH_DELAY_TCY, &mut core.memory);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(OSCCON_ADDR)) & (OSCCON_OSTS | OSCCON_IOFS),
        OSCCON_OSTS,
        "primary-clock completion sets OSTS only"
    );
}

#[test]
fn osctune_intsrc_controls_low_frequency_internal_clock_source() {
    // DS39632E OSCTUNE.INTSRC and DS40001303H §2.2.3 select
    // whether IRCF=000 uses LFINTOSC (~31 kHz) or HFINTOSC
    // divided down.  Both are slow; the exact factor differs
    // and the simulator must surface the choice.
    let mut core = Core::new(Variant::Pic18F2455);
    core.memory.write_raw(Address::from_raw(OSCCON_ADDR), 0x02); // IRCF=000, SCS=internal
    core.peripherals
        .osc
        .on_sfr_write(OSCCON_ADDR, 0x02, &mut core.memory);
    core.peripherals
        .osc
        .tick_tcy(OSC_SWITCH_DELAY_TCY, &mut core.memory);
    let lf_factor = core.peripherals.osc.ticks_per_tcy();

    core.memory.write_raw(Address::from_raw(OSCTUNE_ADDR), 0x80); // INTSRC=1
    core.peripherals
        .osc
        .on_sfr_write(OSCTUNE_ADDR, 0x80, &mut core.memory);
    core.peripherals
        .osc
        .tick_tcy(HFINTOSC_READY_DELAY_TCY, &mut core.memory);
    let hf_div_factor = core.peripherals.osc.ticks_per_tcy();

    assert_ne!(lf_factor, hf_div_factor);
    assert_eq!(hf_div_factor, 6144); // 48 MHz / (31.25 kHz / 4)
}

#[test]
fn chain_scheduler_uses_live_oscillator_factor() {
    // §11c FID-08: the multicore scheduler must ask the core's
    // oscillator for current ticks/Tcy.  A K20 switched to the
    // 16 MHz HFINTOSC path has 12 ticks/Tcy, not its primary XT
    // default of 16.
    let mut core = Core::new(Variant::Pic18F25K20);
    core.memory.write_raw(Address::from_raw(OSCCON_ADDR), 0x72); // IRCF=16 MHz, SCS=internal
    core.peripherals
        .osc
        .on_sfr_write(OSCCON_ADDR, 0x72, &mut core.memory);
    core.peripherals
        .osc
        .tick_tcy(HFINTOSC_READY_DELAY_TCY, &mut core.memory);
    assert_eq!(core.ticks_per_tcy(), 12);

    let mut chain = Chain::new();
    let idx = chain.push_core(core);
    chain.cores[idx].advance_cycles(100);
    chain.schedule_next_core_step(idx);
    let event = chain.events.peek().unwrap();
    assert_eq!(event.tick, 1200);
    assert_eq!(event.kind, EventKind::CoreInstructionComplete(idx));
}
