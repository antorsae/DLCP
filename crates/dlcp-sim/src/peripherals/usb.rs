//! USB-SIE and DLCP HID test surface.
//!
//! This is intentionally not a full USB host/enumeration model.  FID-01
//! requires the PIC18F2455 USB state that DLCP firmware and tests observe:
//! USB SFRs, BDT ownership transitions, endpoint transaction interrupt flow,
//! reset/suspend/resume flags, and host-injected HID reports for the DLCP
//! command subset (`0x20`, `0x21`, `0x43`, `0x44`, plus active-preset
//! filename routing).

use std::collections::VecDeque;

use crate::core::Core;
use crate::memory::{Address, Memory, Variant};
use serde::{Deserialize, Serialize};

pub const UFRML_ADDR: u16 = 0xF66;
pub const UFRMH_ADDR: u16 = 0xF67;
pub const UIR_ADDR: u16 = 0xF68;
pub const UIE_ADDR: u16 = 0xF69;
pub const UEIR_ADDR: u16 = 0xF6A;
pub const UEIE_ADDR: u16 = 0xF6B;
pub const USTAT_ADDR: u16 = 0xF6C;
pub const UCON_ADDR: u16 = 0xF6D;
pub const UADDR_ADDR: u16 = 0xF6E;
pub const UCFG_ADDR: u16 = 0xF6F;
pub const UEP0_ADDR: u16 = 0xF70;
pub const UEP1_ADDR: u16 = 0xF71;
pub const UEP15_ADDR: u16 = 0xF7F;

pub const UIR_URSTIF: u8 = 1 << 0;
pub const UIR_UERRIF: u8 = 1 << 1;
pub const UIR_ACTVIF: u8 = 1 << 2;
pub const UIR_TRNIF: u8 = 1 << 3;
pub const UIR_IDLEIF: u8 = 1 << 4;
pub const UIR_STALLIF: u8 = 1 << 5;
pub const UIR_SOFIF: u8 = 1 << 6;

pub const UCON_SUSPND: u8 = 1 << 1;
pub const UCON_RESUME: u8 = 1 << 2;
pub const UCON_USBEN: u8 = 1 << 3;
pub const UCON_PKTDIS: u8 = 1 << 4;

pub const UEP_STALL: u8 = 1 << 0;
pub const UEP_INEN: u8 = 1 << 1;
pub const UEP_OUTEN: u8 = 1 << 2;
pub const UEP_CONDIS: u8 = 1 << 3;
pub const UEP_HSHK: u8 = 1 << 4;

pub const BDSTAT_UOWN: u8 = 1 << 7;
pub const BDSTAT_DTS: u8 = 1 << 6;
pub const BDSTAT_DTSEN: u8 = 1 << 3;
pub const BDSTAT_BSTALL: u8 = 1 << 2;

pub const CMD_PRESET_SWITCH: u8 = 0x20;
pub const CMD_DIAG_QUERY: u8 = 0x21;
pub const CMD_DIAG_MEMREAD: u8 = 0x43;
pub const CMD_DIAG_SNAPSHOT: u8 = 0x44;

pub const HID_REPORT_LEN: usize = 64;
pub const HID_MAX_PAYLOAD: usize = 0x3D;
pub const DIAG_BASE_ADDR: u16 = 0x2E5;
pub const ACTIVE_PRESET_ADDR: u16 = 0x01F;
pub const ACTIVE_PRESET_BIT: u8 = 1 << 6;
pub const FILENAME_LEN: usize = 0x1E;

const USB_ENDPOINTS: usize = 16;

#[derive(Serialize, Deserialize, Clone, Debug, Default, Eq, PartialEq)]
pub struct BdtEntry {
    pub stat: u8,
    pub count: u8,
    pub addr: u16,
    pub buffer: Vec<u8>,
}

#[derive(Serialize, Deserialize, Clone, Debug, Eq, PartialEq)]
struct HidState {
    active_preset: u8,
    filename_a: [u8; FILENAME_LEN],
    filename_b: [u8; FILENAME_LEN],
}

impl Default for HidState {
    fn default() -> Self {
        HidState {
            active_preset: 0,
            filename_a: [0xFF; FILENAME_LEN],
            filename_b: [0xFF; FILENAME_LEN],
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct Usb {
    is_2455: bool,
    enabled: bool,
    out_bdt: [BdtEntry; USB_ENDPOINTS],
    in_bdt: [BdtEntry; USB_ENDPOINTS],
    ustat_fifo: VecDeque<u8>,
    hid: HidState,
}

impl Default for Usb {
    fn default() -> Self {
        Usb::new(Variant::Pic18F2455)
    }
}

impl Usb {
    pub fn new(variant: Variant) -> Self {
        Usb {
            is_2455: matches!(variant, Variant::Pic18F2455),
            enabled: false,
            out_bdt: std::array::from_fn(|_| BdtEntry::default()),
            in_bdt: std::array::from_fn(|_| BdtEntry::default()),
            ustat_fifo: VecDeque::new(),
            hid: HidState::default(),
        }
    }

    pub fn reset_state(&mut self) {
        self.enabled = false;
        self.out_bdt = std::array::from_fn(|_| BdtEntry::default());
        self.in_bdt = std::array::from_fn(|_| BdtEntry::default());
        self.ustat_fifo.clear();
        self.hid = HidState::default();
    }

    pub fn on_sfr_write(&mut self, addr: u16, value: u8, mem: &mut Memory) {
        if !self.is_2455 {
            return;
        }
        match addr {
            UCON_ADDR => self.write_ucon(value, mem),
            UADDR_ADDR => {
                mem.write_raw(Address::from_raw(UADDR_ADDR), value & 0x7F);
            }
            USTAT_ADDR => {
                self.refresh_ustat(mem);
            }
            UIR_ADDR => self.write_uir(value, mem),
            UEIR_ADDR => {
                mem.write_raw(Address::from_raw(UEIR_ADDR), value & 0x7F);
            }
            UIE_ADDR | UEIE_ADDR | UCFG_ADDR | UFRML_ADDR | UFRMH_ADDR => {}
            UEP0_ADDR..=UEP15_ADDR => {
                mem.write_raw(Address::from_raw(addr), value & 0x1F);
            }
            _ => {}
        }
    }

    pub fn tick_tcy(&mut self, _n: u32, _mem: &mut Memory) {
        // The DLCP-used USB surface is host-event driven in this model.
    }

    pub fn arm_out(&mut self, endpoint: u8, max_len: u8, mem_addr: u16, dts: bool) {
        let entry = &mut self.out_bdt[endpoint as usize];
        entry.stat = BDSTAT_UOWN | BDSTAT_DTSEN | if dts { BDSTAT_DTS } else { 0 };
        entry.count = max_len;
        entry.addr = mem_addr;
        entry.buffer.clear();
    }

    pub fn arm_in(&mut self, endpoint: u8, bytes: &[u8], mem_addr: u16) {
        let entry = &mut self.in_bdt[endpoint as usize];
        entry.stat = BDSTAT_UOWN | BDSTAT_DTSEN;
        entry.count = bytes.len().min(HID_REPORT_LEN) as u8;
        entry.addr = mem_addr;
        entry.buffer = bytes[..bytes.len().min(HID_REPORT_LEN)].to_vec();
    }

    pub fn out_bdt(&self, endpoint: u8) -> &BdtEntry {
        &self.out_bdt[endpoint as usize]
    }

    pub fn in_bdt(&self, endpoint: u8) -> &BdtEntry {
        &self.in_bdt[endpoint as usize]
    }

    pub fn inject_setup(&mut self, setup: &[u8], mem: &mut Memory) -> bool {
        self.accept_out_like_transaction(0, setup, mem, true)
    }

    pub fn inject_out(&mut self, endpoint: u8, bytes: &[u8], mem: &mut Memory) -> bool {
        self.accept_out_like_transaction(endpoint, bytes, mem, false)
    }

    pub fn take_in(&mut self, endpoint: u8, mem: &mut Memory) -> Option<Vec<u8>> {
        if !self.endpoint_in_enabled(endpoint, mem) {
            return None;
        }
        let entry = &mut self.in_bdt[endpoint as usize];
        if entry.stat & BDSTAT_UOWN == 0 {
            return None;
        }
        entry.stat &= !BDSTAT_UOWN;
        let bytes = entry.buffer.clone();
        entry.count = bytes.len().min(HID_REPORT_LEN) as u8;
        self.queue_transaction(endpoint, true, mem);
        Some(bytes)
    }

    pub fn inject_usb_reset(&mut self, mem: &mut Memory) {
        self.out_bdt = std::array::from_fn(|_| BdtEntry::default());
        self.in_bdt = std::array::from_fn(|_| BdtEntry::default());
        self.ustat_fifo.clear();
        mem.write_raw(Address::from_raw(USTAT_ADDR), 0);
        mem.write_raw(Address::from_raw(UADDR_ADDR), 0);
        set_bits(mem, UIR_ADDR, UIR_URSTIF);
    }

    pub fn inject_suspend(&mut self, mem: &mut Memory) {
        set_bits(mem, UCON_ADDR, UCON_SUSPND);
        set_bits(mem, UIR_ADDR, UIR_IDLEIF);
    }

    pub fn inject_resume(&mut self, mem: &mut Memory) {
        clear_bits(mem, UCON_ADDR, UCON_SUSPND);
        set_bits(mem, UIR_ADDR, UIR_ACTVIF);
    }

    pub const fn active_preset(&self) -> u8 {
        self.hid.active_preset
    }

    pub fn active_filename(&self) -> &[u8; FILENAME_LEN] {
        if self.hid.active_preset == 0 {
            &self.hid.filename_a
        } else {
            &self.hid.filename_b
        }
    }

    pub fn write_active_filename(&mut self, name: &[u8]) {
        let mut slot = [0xFF; FILENAME_LEN];
        let copy_len = name.len().min(FILENAME_LEN);
        slot[..copy_len].copy_from_slice(&name[..copy_len]);
        if self.hid.active_preset == 0 {
            self.hid.filename_a = slot;
        } else {
            self.hid.filename_b = slot;
        }
    }

    fn write_ucon(&mut self, value: u8, mem: &mut Memory) {
        let masked = value & (UCON_SUSPND | UCON_RESUME | UCON_USBEN | UCON_PKTDIS);
        mem.write_raw(Address::from_raw(UCON_ADDR), masked);
        let now_enabled = masked & UCON_USBEN != 0;
        if self.enabled && !now_enabled {
            self.out_bdt = std::array::from_fn(|_| BdtEntry::default());
            self.in_bdt = std::array::from_fn(|_| BdtEntry::default());
            self.ustat_fifo.clear();
            mem.write_raw(Address::from_raw(USTAT_ADDR), 0);
        }
        self.enabled = now_enabled;
    }

    fn write_uir(&mut self, value: u8, mem: &mut Memory) {
        let mut flags = mem.read_raw(Address::from_raw(UIR_ADDR)) & 0x7F;
        flags &= value & !UIR_TRNIF;
        if value & UIR_TRNIF == 0 {
            self.ustat_fifo.pop_front();
        } else {
            flags |= UIR_TRNIF;
        }
        mem.write_raw(Address::from_raw(UIR_ADDR), flags);
        self.refresh_ustat(mem);
    }

    fn accept_out_like_transaction(
        &mut self,
        endpoint: u8,
        bytes: &[u8],
        mem: &mut Memory,
        setup: bool,
    ) -> bool {
        if !self.endpoint_out_enabled(endpoint, mem, setup) {
            return false;
        }
        let entry = &mut self.out_bdt[endpoint as usize];
        if entry.stat & BDSTAT_UOWN == 0 {
            return false;
        }
        let max_len = usize::from(entry.count).max(bytes.len()).min(HID_REPORT_LEN);
        let copy_len = bytes.len().min(max_len);
        entry.buffer = bytes[..copy_len].to_vec();
        entry.count = copy_len as u8;
        entry.stat &= !BDSTAT_UOWN;
        if setup {
            set_bits(mem, UCON_ADDR, UCON_PKTDIS);
        }
        self.queue_transaction(endpoint, false, mem);
        true
    }

    fn endpoint_out_enabled(&self, endpoint: u8, mem: &Memory, setup: bool) -> bool {
        if !self.is_2455 || !self.enabled || endpoint as usize >= USB_ENDPOINTS {
            return false;
        }
        if setup && endpoint == 0 {
            return true;
        }
        let uep = mem.read_raw(Address::from_raw(UEP0_ADDR + endpoint as u16));
        uep & UEP_OUTEN != 0
    }

    fn endpoint_in_enabled(&self, endpoint: u8, mem: &Memory) -> bool {
        if !self.is_2455 || !self.enabled || endpoint as usize >= USB_ENDPOINTS {
            return false;
        }
        let uep = mem.read_raw(Address::from_raw(UEP0_ADDR + endpoint as u16));
        endpoint == 0 || uep & UEP_INEN != 0
    }

    fn queue_transaction(&mut self, endpoint: u8, in_dir: bool, mem: &mut Memory) {
        let token = ((endpoint & 0x0F) << 3) | if in_dir { 0x04 } else { 0x00 };
        self.ustat_fifo.push_back(token);
        self.refresh_ustat(mem);
    }

    fn refresh_ustat(&mut self, mem: &mut Memory) {
        if let Some(&token) = self.ustat_fifo.front() {
            mem.write_raw(Address::from_raw(USTAT_ADDR), token);
            set_bits(mem, UIR_ADDR, UIR_TRNIF);
        } else {
            mem.write_raw(Address::from_raw(USTAT_ADDR), 0);
            clear_bits(mem, UIR_ADDR, UIR_TRNIF);
        }
    }
}

pub fn execute_dlcp_hid_report(core: &mut Core, report: &[u8]) -> [u8; HID_REPORT_LEN] {
    let mut response = [0u8; HID_REPORT_LEN];
    let cmd = report.first().copied().unwrap_or(0);
    match cmd {
        CMD_PRESET_SWITCH => {
            let preset = report.get(1).copied().unwrap_or(0) & 0x01;
            response[0] = CMD_PRESET_SWITCH;
            response[1] = 0x00;
            response[2] = 0x01;
            response[3] = preset;
            let preset_cell = core.memory.read_raw(Address::from_raw(ACTIVE_PRESET_ADDR));
            let preset_cell = if preset == 0 {
                preset_cell & !ACTIVE_PRESET_BIT
            } else {
                preset_cell | ACTIVE_PRESET_BIT
            };
            core.memory
                .write_raw(Address::from_raw(ACTIVE_PRESET_ADDR), preset_cell);
            core.peripherals.usb.hid.active_preset = preset;
        }
        CMD_DIAG_QUERY => {
            response[0] = CMD_DIAG_QUERY;
            response[1] = 0x00;
            response[2] = 0x07;
            for i in 0..7 {
                response[3 + i] = core
                    .memory
                    .read_raw(Address::from_raw(DIAG_BASE_ADDR + i as u16))
                    & 0x0F;
            }
        }
        CMD_DIAG_MEMREAD => {
            response = handle_memread(core, report);
        }
        CMD_DIAG_SNAPSHOT => {
            response[0] = CMD_DIAG_SNAPSHOT;
            response[1] = 0x00;
            response[2] = 0x0B;
            for i in 0..11 {
                response[3 + i] = core
                    .memory
                    .read_raw(Address::from_raw(DIAG_BASE_ADDR + i as u16));
            }
            for byte in &mut response[3..10] {
                *byte &= 0x0F;
            }
            for byte in &mut response[10..14] {
                *byte = u8::from(*byte != 0);
            }
        }
        _ => {
            response[0] = cmd;
            response[1] = 0x01;
        }
    }
    core.peripherals.usb.arm_in(1, &response, 0);
    response
}

fn handle_memread(core: &Core, report: &[u8]) -> [u8; HID_REPORT_LEN] {
    let mut response = [0u8; HID_REPORT_LEN];
    response[0] = CMD_DIAG_MEMREAD;
    let region = report.get(1).copied().unwrap_or(0xFF);
    let addr = u16::from(report.get(2).copied().unwrap_or(0))
        | (u16::from(report.get(3).copied().unwrap_or(0)) << 8);
    let length = report.get(4).copied().unwrap_or(0) as usize;
    if length == 0 || length > HID_MAX_PAYLOAD {
        response[1] = 0x02;
        return response;
    }
    response[2] = length as u8;
    match region {
        0x00 => {
            let start = addr as usize;
            let end = start.saturating_add(length);
            if end > core.flash().len() {
                response[1] = 0x02;
                return response;
            }
            response[3..3 + length].copy_from_slice(&core.flash()[start..end]);
        }
        0x01 => {
            let start = addr as usize;
            if start + length > 256 {
                response[1] = 0x02;
                return response;
            }
            for i in 0..length {
                response[3 + i] = core.peripherals.eeprom.get_byte((start + i) as u8);
            }
        }
        _ => {
            response[1] = 0x01;
            return response;
        }
    }
    response[1] = 0x00;
    response
}

fn set_bits(mem: &mut Memory, addr: u16, mask: u8) {
    let value = mem.read_raw(Address::from_raw(addr)) | mask;
    mem.write_raw(Address::from_raw(addr), value);
}

fn clear_bits(mem: &mut Memory, addr: u16, mask: u8) {
    let value = mem.read_raw(Address::from_raw(addr)) & !mask;
    mem.write_raw(Address::from_raw(addr), value);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn k20_construction_marks_non_2455() {
        let usb = Usb::new(Variant::Pic18F25K20);
        assert!(!usb.is_2455);
    }

    #[test]
    fn pic2455_construction_marks_2455() {
        let usb = Usb::new(Variant::Pic18F2455);
        assert!(usb.is_2455);
    }

    #[test]
    fn filename_slots_follow_active_preset() {
        let mut usb = Usb::new(Variant::Pic18F2455);
        usb.write_active_filename(b"Preset A");
        usb.hid.active_preset = 1;
        usb.write_active_filename(b"Preset B");
        assert!(usb.active_filename().starts_with(b"Preset B"));
        usb.hid.active_preset = 0;
        assert!(usb.active_filename().starts_with(b"Preset A"));
    }
}
