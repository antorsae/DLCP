//! FID-15 missing-peripheral stub policy.
//!
//! `docs/SIM_REWRITE_RUST_SPEC.md` §11c requires CCP/ECCP/PWM,
//! comparators/CVREF, HLVD, PSP/SPP, FVR, and otherwise unowned
//! variant-specific SFRs to be either implemented or explicitly stubbed.
//! This focused gate verifies that the simulator has a table-backed policy
//! with datasheet citations and deterministic no-side-effect SFR behavior.

use dlcp_sim::core::Core;
use dlcp_sim::memory::{Address, Variant};
use dlcp_sim::peripherals::irq::PIR2_ADDR;
use dlcp_sim::peripherals::stubs::{StubBehavior, policies_for};

fn sfr_write(core: &mut Core, addr: u16, value: u8) {
    core.memory.write_raw(Address::from_raw(addr), value);
    let memory = &mut core.memory;
    let peripherals = &mut core.peripherals;
    peripherals.on_sfr_write(addr, value, memory);
}

fn has_category(variant: Variant, name: &str) -> bool {
    policies_for(variant)
        .iter()
        .any(|policy| policy.peripheral == name)
}

#[test]
fn missing_peripheral_stub_policy() {
    for variant in [Variant::Pic18F25K20, Variant::Pic18F2455] {
        for category in [
            "CCP/ECCP/PWM",
            "Comparator/CVREF/FVR",
            "HLVD",
            "PSP/SPP",
        ] {
            assert!(
                has_category(variant, category),
                "{variant:?} must classify missing peripheral category {category}"
            );
        }
        for policy in policies_for(variant) {
            assert!(
                !policy.citation.is_empty(),
                "{variant:?} {} {} must cite the datasheet",
                policy.peripheral,
                policy.sfr
            );
            assert!(
                !policy.dlcp_scope.is_empty(),
                "{variant:?} {} {} must document why the stub is OK for DLCP",
                policy.peripheral,
                policy.sfr
            );
        }
    }

    // Representative register-backed stubs: writes are visible only through
    // documented writable bits, and no comparator/HLVD/CCP flags are created.
    let mut k20 = Core::new(Variant::Pic18F25K20);
    k20.memory.write_raw(Address::from_raw(PIR2_ADDR), 0x00);
    sfr_write(&mut k20, 0xFD2, 0xFF); // HLVDCON, bit 6 unimplemented.
    assert_eq!(k20.memory.read_raw(Address::from_raw(0xFD2)), 0xBF);
    assert_eq!(
        k20.memory.read_raw(Address::from_raw(PIR2_ADDR)),
        0x00,
        "HLVD stub must not synthesize PIR2.HLVDIF"
    );

    sfr_write(&mut k20, 0xFB4, 0xFF); // CVRCON2/FVR, lower six bits unimplemented/status.
    assert_eq!(
        k20.memory.read_raw(Address::from_raw(0xFB4)),
        0x80,
        "FVR stub stores FVREN only; no FVRST settling model"
    );

    let mut main = Core::new(Variant::Pic18F2455);
    main.memory.write_raw(Address::from_raw(PIR2_ADDR), 0x00);
    sfr_write(&mut main, 0xFBD, 0xFF); // CCP1CON, 28-pin upper bits unavailable.
    assert_eq!(main.memory.read_raw(Address::from_raw(0xFBD)), 0x3F);
    assert_eq!(
        main.memory.read_raw(Address::from_raw(PIR2_ADDR)),
        0x00,
        "CCP/PWM stub must not synthesize PIR2.CCP2IF or related flags"
    );

    assert!(
        policies_for(Variant::Pic18F2455).iter().any(|policy| {
            policy.peripheral == "PSP/SPP"
                && policy.addr.is_none()
                && policy.behavior == StubBehavior::NotPresentOnDlcpPackage
        }),
        "2455 SPP must be explicitly classified absent for the 28-pin DLCP package"
    );
}
