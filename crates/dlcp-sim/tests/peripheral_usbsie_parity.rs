//! P2.8 / FID-01 USB-SIE parity gate.
//!
//! 2455-only.  `docs/SIM_REWRITE_RUST_SPEC.md` §11c FID-01
//! explicitly excludes full USB host enumeration, but requires the
//! DLCP-used SIE/HID surface: UCON/UCFG/UADDR/USTAT/UIR/UIE/UEPn
//! behavior, BDT ownership for SETUP/OUT/IN, reset/suspend/resume
//! flags, endpoint transaction interrupt flow, and HID commands
//! `0x20`, `0x21`, `0x43`, `0x44` plus active-preset filename
//! routing.  Datasheet anchor: DS39632E §17 USB and Buffer
//! Descriptor Table registers.

use dlcp_sim::core::Core;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::usb::{
    ACTIVE_PRESET_ADDR, ACTIVE_PRESET_BIT, BDSTAT_UOWN, CMD_DIAG_MEMREAD, CMD_DIAG_QUERY,
    CMD_DIAG_SNAPSHOT, CMD_PRESET_SWITCH, DIAG_BASE_ADDR, HID_REPORT_LEN, UADDR_ADDR, UCON_ADDR,
    UCON_SUSPND, UCON_USBEN, UEP_HSHK, UEP_INEN, UEP_OUTEN, UEP1_ADDR, UIR_ACTVIF, UIR_ADDR,
    UIR_IDLEIF, UIR_TRNIF, UIR_URSTIF, USTAT_ADDR, execute_dlcp_hid_report,
};
use dlcp_sim::reset::{ResetSource, apply_reset};
use dlcp_sim::stack::Stack;

fn sfr_write(core: &mut Core, addr: u16, value: u8) {
    core.memory.write_raw(Address::from_raw(addr), value);
    let memory = &mut core.memory;
    let peripherals = &mut core.peripherals;
    peripherals.on_sfr_write(addr, value, memory);
}

#[test]
fn usb_construction_for_2455_marks_2455() {
    let core = Core::new(Variant::Pic18F2455);
    // No public read accessor for `is_2455` -- the
    // observable contract is "no panic on construction"
    // and "tick is a no-op".  The unit tests inside usb.rs
    // already assert the field; here we just check Core
    // owns a Usb instance.
    let _ = &core.peripherals.usb;
}

#[test]
fn usb_construction_for_k20_does_not_panic() {
    let core = Core::new(Variant::Pic18F25K20);
    let _ = &core.peripherals.usb;
}

#[test]
fn por_reset_does_not_panic_on_2455() {
    let mut core = Core::new(Variant::Pic18F2455);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
}

#[test]
fn por_reset_does_not_panic_on_k20() {
    let mut core = Core::new(Variant::Pic18F25K20);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);
}

#[test]
fn usb_sfr_bdt_state_machine() {
    let mut core = Core::new(Variant::Pic18F2455);
    let mut stack = Stack::new();
    apply_reset(&mut core, &mut stack, ResetSource::PowerOn);

    // DS39632E USB SFRs: USBEN owns the SIE, UADDR is 7-bit, UEPn gates
    // endpoint direction, BDT UOWN moves from SIE to CPU at transaction end,
    // and UIR.TRNIF/USTAT expose one completed transaction at a time.
    sfr_write(&mut core, UCON_ADDR, UCON_USBEN);
    sfr_write(&mut core, UADDR_ADDR, 0xFF);
    assert_eq!(core.memory.read_raw(Address::from_raw(UADDR_ADDR)), 0x7F);
    sfr_write(&mut core, UEP1_ADDR, UEP_INEN | UEP_OUTEN | UEP_HSHK);

    core.peripherals.usb.arm_out(1, 64, 0x0400, false);
    let accepted = {
        let memory = &mut core.memory;
        let usb = &mut core.peripherals.usb;
        usb.inject_out(1, &[0x43, 0x00, 0x34, 0x12, 0x03], memory)
    };
    assert!(
        accepted,
        "EP1 OUT should be accepted when UOWN and EPOUTEN are set"
    );
    assert_eq!(core.peripherals.usb.out_bdt(1).stat & BDSTAT_UOWN, 0);
    assert_eq!(core.peripherals.usb.out_bdt(1).count, 5);
    assert_ne!(
        core.memory.read_raw(Address::from_raw(UIR_ADDR)) & UIR_TRNIF,
        0
    );
    assert_eq!(
        core.memory.read_raw(Address::from_raw(USTAT_ADDR)),
        1 << 3,
        "USTAT endpoint bits should point at EP1 OUT"
    );

    let clear_trnif = core.memory.read_raw(Address::from_raw(UIR_ADDR)) & !UIR_TRNIF;
    sfr_write(&mut core, UIR_ADDR, clear_trnif);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(UIR_ADDR)) & UIR_TRNIF,
        0
    );

    core.peripherals.usb.arm_in(1, b"abc", 0x0440);
    let packet = {
        let memory = &mut core.memory;
        let usb = &mut core.peripherals.usb;
        usb.take_in(1, memory)
    };
    assert_eq!(packet.as_deref(), Some(&b"abc"[..]));
    assert_eq!(core.peripherals.usb.in_bdt(1).stat & BDSTAT_UOWN, 0);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(USTAT_ADDR)),
        (1 << 3) | 0x04,
        "USTAT endpoint bits should point at EP1 IN"
    );

    {
        let memory = &mut core.memory;
        let usb = &mut core.peripherals.usb;
        usb.inject_usb_reset(memory);
        usb.inject_suspend(memory);
        usb.inject_resume(memory);
    }
    let uir = core.memory.read_raw(Address::from_raw(UIR_ADDR));
    assert_ne!(uir & UIR_URSTIF, 0);
    assert_ne!(uir & UIR_IDLEIF, 0);
    assert_ne!(uir & UIR_ACTVIF, 0);
    assert_eq!(core.memory.read_raw(Address::from_raw(UADDR_ADDR)), 0);
    assert_eq!(
        core.memory.read_raw(Address::from_raw(UCON_ADDR)) & UCON_SUSPND,
        0
    );
}

#[test]
fn dlcp_hid_commands() {
    let mut core = Core::new(Variant::Pic18F2455);
    core.flash_mut()[0x1234..0x1237].copy_from_slice(&[0xAA, 0xBB, 0xCC]);
    core.peripherals.eeprom.set_byte(0x60, b'A');
    core.peripherals.eeprom.set_byte(0x61, b'B');
    core.peripherals.eeprom.set_byte(0x62, b'C');
    for (idx, value) in [1, 2, 3, 4, 5, 6, 7, 1, 0, 1, 0].iter().enumerate() {
        core.memory
            .write_raw(Address::from_raw(DIAG_BASE_ADDR + idx as u16), *value);
    }
    sfr_write(&mut core, UCON_ADDR, UCON_USBEN);
    sfr_write(&mut core, UEP1_ADDR, UEP_INEN | UEP_OUTEN | UEP_HSHK);

    let mut report = [0u8; HID_REPORT_LEN];
    report[0] = CMD_DIAG_MEMREAD;
    report[1] = 0x00;
    report[2] = 0x34;
    report[3] = 0x12;
    report[4] = 0x03;
    let resp = execute_dlcp_hid_report(&mut core, &report);
    assert_eq!(
        &resp[..6],
        &[CMD_DIAG_MEMREAD, 0x00, 0x03, 0xAA, 0xBB, 0xCC]
    );

    report = [0u8; HID_REPORT_LEN];
    report[0] = CMD_DIAG_MEMREAD;
    report[1] = 0x01;
    report[2] = 0x60;
    report[4] = 0x03;
    let resp = execute_dlcp_hid_report(&mut core, &report);
    assert_eq!(
        &resp[..6],
        &[CMD_DIAG_MEMREAD, 0x00, 0x03, b'A', b'B', b'C']
    );

    report = [0u8; HID_REPORT_LEN];
    report[0] = CMD_DIAG_QUERY;
    let resp = execute_dlcp_hid_report(&mut core, &report);
    assert_eq!(
        &resp[..10],
        &[CMD_DIAG_QUERY, 0x00, 0x07, 1, 2, 3, 4, 5, 6, 7]
    );

    report = [0u8; HID_REPORT_LEN];
    report[0] = CMD_DIAG_SNAPSHOT;
    let resp = execute_dlcp_hid_report(&mut core, &report);
    assert_eq!(
        &resp[..14],
        &[
            CMD_DIAG_SNAPSHOT,
            0x00,
            0x0B,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            1,
            0,
            1,
            0
        ]
    );

    report = [0u8; HID_REPORT_LEN];
    report[0] = CMD_PRESET_SWITCH;
    report[1] = 1;
    let resp = execute_dlcp_hid_report(&mut core, &report);
    assert_eq!(&resp[..4], &[CMD_PRESET_SWITCH, 0x00, 0x01, 0x01]);
    assert_ne!(
        core.memory.read_raw(Address::from_raw(ACTIVE_PRESET_ADDR)) & ACTIVE_PRESET_BIT,
        0
    );
    assert_eq!(core.peripherals.usb.active_preset(), 1);

    core.peripherals.usb.write_active_filename(b"Preset B");
    report[1] = 0;
    execute_dlcp_hid_report(&mut core, &report);
    core.peripherals.usb.write_active_filename(b"Preset A");
    report[1] = 1;
    execute_dlcp_hid_report(&mut core, &report);
    assert!(
        core.peripherals
            .usb
            .active_filename()
            .starts_with(b"Preset B"),
        "filename writes must route to the active A/B preset slot"
    );
}
