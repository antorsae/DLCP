//! Default-off memory trace recorder for corruption investigations.
//!
//! The recorder is intentionally range driven.  Hot paths pay only an
//! `Option` check until a test or probe enables tracing on a [`Core`].

use crate::memory::{Address, Memory};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, VecDeque};

#[derive(Serialize, Deserialize, Copy, Clone, Debug, Eq, PartialEq)]
pub enum MemSpace {
    DataRam,
    Sfr,
    Eeprom,
    HardwareDma,
}

#[derive(Serialize, Deserialize, Copy, Clone, Debug, Eq, PartialEq)]
pub enum TraceKind {
    FirmwareDataWrite,
    FirmwareSfrWrite,
    PeripheralSfrSideEffect,
    EepromArm,
    EepromCommit,
    EepromResetDrop,
    HostRamPoke,
    HostEepromSeed,
}

#[derive(Serialize, Deserialize, Copy, Clone, Debug, Eq, PartialEq)]
pub enum TraceOrigin {
    FirmwareInstruction,
    Peripheral,
    Reset,
    Host,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct TraceWatch {
    pub core_idx: Option<usize>,
    pub role: Option<String>,
    pub space: MemSpace,
    pub start: u16,
    pub end: u16,
    pub label: String,
    pub protected: bool,
    pub stop_on_write: bool,
    pub fail_on_write: bool,
}

impl TraceWatch {
    pub fn matches(&self, core_idx: usize, role: &str, space: MemSpace, addr: u16) -> bool {
        if self.core_idx.is_some_and(|idx| idx != core_idx) {
            return false;
        }
        if self.role.as_deref().is_some_and(|wanted| wanted != role) {
            return false;
        }
        self.space == space && addr >= self.start && addr <= self.end
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct MemTraceConfig {
    pub watches: Vec<TraceWatch>,
    pub max_records: usize,
}

impl Default for MemTraceConfig {
    fn default() -> Self {
        Self {
            watches: Vec::new(),
            max_records: 10_000,
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug, Default)]
pub struct TraceCpuSnapshot {
    pub wreg: u8,
    pub status: u8,
    pub bsr: u8,
    pub fsr0: u16,
    pub fsr1: u16,
    pub fsr2: u16,
    pub tos: Option<u32>,
    pub stack: Vec<u32>,
}

impl TraceCpuSnapshot {
    pub fn from_memory(mem: &Memory) -> Self {
        let read = |addr| mem.read_raw(Address::from_raw(addr));
        Self {
            wreg: read(0xFE8),
            status: read(0xFD8),
            bsr: read(0xFE0),
            fsr0: ((read(0xFEA) as u16 & 0x0F) << 8) | read(0xFE9) as u16,
            fsr1: ((read(0xFE2) as u16 & 0x0F) << 8) | read(0xFE1) as u16,
            fsr2: ((read(0xFDA) as u16 & 0x0F) << 8) | read(0xFD9) as u16,
            tos: None,
            stack: Vec::new(),
        }
    }
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct TraceContext {
    pub core_idx: usize,
    pub role: String,
    pub tick: u64,
    pub ticks_per_tcy: u32,
    pub core_tcy_before: u64,
    pub phase: String,
    pub tos: Option<u32>,
    pub stack: Vec<u32>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct EepromArmTrace {
    pub seq: u64,
    pub pc: Option<u32>,
    pub tick: u64,
    pub core_tcy: u64,
    pub eecon1_intended: u8,
    pub eecon1_landed: u8,
    pub eeadr: u8,
    pub eedata: u8,
    pub old_at_arm: u8,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct TraceRecord {
    pub seq: u64,
    pub tick: u64,
    pub core_tcy: u64,
    pub core_idx: usize,
    pub role: String,
    pub kind: TraceKind,
    pub space: MemSpace,
    pub addr: u16,
    pub old: u8,
    pub new: u8,
    pub intended: Option<u8>,
    pub changed: bool,
    pub label: String,
    pub protected: bool,
    pub stop_on_write: bool,
    pub fail_on_write: bool,
    pub phase: String,
    pub origin: TraceOrigin,
    pub pc: Option<u32>,
    pub cpu: Option<TraceCpuSnapshot>,
    pub arm: Option<EepromArmTrace>,
    pub rejected_reason: Option<String>,
}

#[derive(Clone, Debug)]
pub struct TraceEvent {
    pub kind: TraceKind,
    pub space: MemSpace,
    pub addr: u16,
    pub old: u8,
    pub new: u8,
    pub intended: Option<u8>,
    pub origin: TraceOrigin,
    pub pc: Option<u32>,
    pub cpu: Option<TraceCpuSnapshot>,
    pub arm: Option<EepromArmTrace>,
    pub rejected_reason: Option<String>,
    pub seq: Option<u64>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct MemTraceSummary {
    pub total_count: u64,
    pub dropped_count: u64,
    pub overflowed: bool,
    pub record_count: usize,
    pub first_match_labels: Vec<String>,
    pub first_violation: Option<TraceRecord>,
    pub stop_requested: bool,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct MemTraceState {
    pub config: MemTraceConfig,
    pub records: VecDeque<TraceRecord>,
    pub first_match_by_watch: BTreeMap<String, TraceRecord>,
    pub first_violation: Option<TraceRecord>,
    pub total_count: u64,
    pub dropped_count: u64,
    pub overflowed: bool,
    pub stop_requested: bool,
    next_seq: u64,
}

impl MemTraceState {
    pub fn new(config: MemTraceConfig) -> Self {
        Self {
            config,
            records: VecDeque::new(),
            first_match_by_watch: BTreeMap::new(),
            first_violation: None,
            total_count: 0,
            dropped_count: 0,
            overflowed: false,
            stop_requested: false,
            next_seq: 1,
        }
    }

    pub fn clear(&mut self) {
        self.records.clear();
        self.first_match_by_watch.clear();
        self.first_violation = None;
        self.total_count = 0;
        self.dropped_count = 0;
        self.overflowed = false;
        self.stop_requested = false;
        self.next_seq = 1;
    }

    pub fn reserve_seq(&mut self) -> u64 {
        let seq = self.next_seq;
        self.next_seq = self.next_seq.saturating_add(1);
        seq
    }

    pub fn record(&mut self, ctx: Option<&TraceContext>, event: TraceEvent) -> Option<TraceRecord> {
        let (core_idx, role, tick, core_tcy, phase) = match ctx {
            Some(ctx) => (
                ctx.core_idx,
                ctx.role.as_str(),
                ctx.tick,
                ctx.core_tcy_before,
                ctx.phase.as_str(),
            ),
            None => (usize::MAX, "unknown", 0, 0, "unknown"),
        };
        let matches: Vec<TraceWatch> = self
            .config
            .watches
            .iter()
            .filter(|watch| watch.matches(core_idx, role, event.space, event.addr))
            .cloned()
            .collect();
        if matches.is_empty() {
            return None;
        }
        if event.old == event.new
            && matches
                .iter()
                .all(|watch| !watch.stop_on_write && !watch.fail_on_write)
        {
            return None;
        }

        let first = &matches[0];
        let record = TraceRecord {
            seq: event.seq.unwrap_or_else(|| self.reserve_seq()),
            tick,
            core_tcy,
            core_idx,
            role: role.to_string(),
            kind: event.kind,
            space: event.space,
            addr: event.addr,
            old: event.old,
            new: event.new,
            intended: event.intended,
            changed: event.old != event.new,
            label: first.label.clone(),
            protected: first.protected,
            stop_on_write: first.stop_on_write,
            fail_on_write: first.fail_on_write,
            phase: phase.to_string(),
            origin: event.origin,
            pc: event.pc,
            cpu: event.cpu,
            arm: event.arm,
            rejected_reason: event.rejected_reason,
        };

        self.total_count = self.total_count.saturating_add(1);
        for watch in &matches {
            self.first_match_by_watch
                .entry(watch.label.clone())
                .or_insert_with(|| record.clone());
            if watch.stop_on_write {
                self.stop_requested = true;
            }
        }
        if matches
            .iter()
            .any(|watch| watch.protected || watch.fail_on_write)
            && self.first_violation.is_none()
        {
            self.first_violation = Some(record.clone());
        }
        let cap = self.config.max_records.max(1);
        if self.records.len() >= cap {
            self.records.pop_front();
            self.dropped_count = self.dropped_count.saturating_add(1);
            self.overflowed = true;
        }
        self.records.push_back(record.clone());
        Some(record)
    }

    pub fn summary(&self) -> MemTraceSummary {
        MemTraceSummary {
            total_count: self.total_count,
            dropped_count: self.dropped_count,
            overflowed: self.overflowed,
            record_count: self.records.len(),
            first_match_labels: self.first_match_by_watch.keys().cloned().collect(),
            first_violation: self.first_violation.clone(),
            stop_requested: self.stop_requested,
        }
    }
}
