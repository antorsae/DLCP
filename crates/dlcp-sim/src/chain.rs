//! `Chain` — multi-core container + universal-clock
//! scheduler driver.
//!
//! ## Phase-3 scope
//!
//! P3.1 lands the skeleton: a `Chain` holds N cores, owns
//! the global event queue from [`crate::scheduler`], and
//! exposes `step_ticks(n)` that advances the universal
//! clock by `n` ticks while draining due events.
//! Cross-core wiring (P3.2 pin net), boot offsets (P3.4),
//! and the actual instruction-step path that posts
//! `CoreInstructionComplete` events back into the queue
//! land in subsequent sub-tasks.
//!
//! ## Universal clock invariants
//!
//! * Tick is `u64` of a 48 MHz universal clock (LCM of K20
//!   12 MHz Fosc and 2455 16 MHz Fosc).  Range: ~12 years.
//! * Each core advances by `ticks_per_tcy(variant)`
//!   universal ticks per instruction-cycle (Tcy):
//!   K20=16, 2455=12.  See `peripherals/osc.rs`.

use crate::clock::ClockDomain;
use crate::core::Core;
use crate::exec::step;
use crate::lcd::Hd44780;
use crate::memory::Address;
use crate::peripherals::mssp::{I2cBusEvent, Mssp};
use crate::peripherals::osc;
use crate::peripherals::tas3108::Tas3108;
use crate::pinnet::{PinId, PinNet};
use crate::reset::{ResetSource, apply_reset};
use crate::scheduler::{Event, EventKind, EventQueue};
use crate::stack::Stack;

/// Multi-core chain on a single universal-clock timeline.
pub struct Chain {
    /// Cores in firmware-deterministic order.  Index into
    /// this vec is the `core_idx` carried in event kinds.
    pub cores: Vec<Core>,
    /// One stack per core, parallel to `cores`.  The
    /// PIC18 `exec::step` API takes a `&mut Stack`
    /// alongside the core, so the chain owns one per core
    /// and pairs them by index.
    pub stacks: Vec<Stack>,
    /// Per-core clock domain (ticks/Tcy + drift_ppm).
    /// Parallel to `cores`.  P3.5 uses these to schedule
    /// the next instruction-complete event with drift
    /// applied via `ClockDomain::apply_drift`.
    pub clocks: Vec<ClockDomain>,
    /// Per-core boot-offset epoch tick.  Recorded by
    /// `schedule_initial_steps` and added to every
    /// subsequent `schedule_next_core_step` call so a
    /// late-booting core's instruction-complete events
    /// stay delayed by the offset rather than collapsing
    /// to the start-of-time.  Defaults to 0 for cores
    /// that never had `schedule_initial_steps` called.
    pub boot_epochs: Vec<u64>,
    /// Universal-clock tick at the head of the queue.
    /// Phase-3.5 dispatch updates this as events fire so
    /// each core's instruction completes at its own
    /// drifted-ticks-per-Tcy boundary.
    pub current_tick: u64,
    /// Global event queue.  Phase-3.5 dispatch consumes
    /// `CoreInstructionComplete` events here; future P3.x
    /// sub-tasks add `PinPropagation` and
    /// `PeripheralDeadline` handlers.
    pub events: EventQueue,
    /// Cross-core electrical wiring (UART couplings, pin
    /// couplings, I²C slave couplings).  Populated via
    /// `couple_uart` / `couple_pin` / `couple_i2c_slave`.
    /// Phase-3.5 dispatches byte propagation across these
    /// on event firing.
    pub pinnet: PinNet,
    /// Time-stamped UART byte deliveries between cores.
    /// Appended to every time `deliver_uart_byte` runs --
    /// captures the (tick, src_core, dst_core, byte) tuple.
    /// Phase-3.5 part-10+ will use this to compare TX byte
    /// streams bit-exact against gpsim ground truth (per
    /// `docs/SIM_REWRITE_RUST_PROGRESS.md` P3.5 spec); the
    /// part-9 minimum-viable acceptance test
    /// (`chain_v171_v31_reaches_first_uart_tx`) just
    /// asserts the recorder is non-empty after V3.1 chain
    /// convergence.  Cleared by `apply_reset_all` so a
    /// re-bootstrap doesn't carry pre-reset history forward.
    pub uart_tx_history: Vec<UartByteRecord>,
    /// TAS3108 audio-DSP I²C slaves connected to one or
    /// more master cores via `couple_tas3108`.  Phase-3.5
    /// uses these to ACK V3.1 MAIN's `dsp_ping` and
    /// `volume_dsp_write` so the firmware advances past
    /// `wait_bf_clear_loop` instead of spin-retrying.
    pub tas3108_slaves: Vec<Tas3108>,
    /// (master_core, slave_idx) coupling list parallel to
    /// `pinnet.i2c`.  After each `execute_core_step`, the
    /// chain drains the master core's MSSP `last_bus_event`
    /// and routes Start/Stop/RepeatedStart/TxByte to every
    /// slave coupled to that master.  TxByte routes
    /// override the master's ACKSTAT to 0 if any slave
    /// ACKed the byte.
    pub tas3108_couplings: Vec<(usize, usize)>,
    /// Virtual HD44780 character LCDs driven by one or more
    /// controller cores via `couple_lcd`.  Each LCD watches
    /// the controller core's pin state (RS = LATA[5], E =
    /// LATB[4], D4..D7 = PORTB[3:0]) after every executed
    /// instruction and reconstructs DDRAM contents from the
    /// E-falling-edge nibble stream.  Task #34.
    pub lcd_slaves: Vec<Hd44780>,
    /// (controller_core, lcd_slave_idx) coupling list.
    /// Parallel to `tas3108_couplings`; one controller core
    /// can drive multiple LCDs (rare on the DLCP hardware
    /// but the model permits it).  Task #34.
    pub lcd_couplings: Vec<(usize, usize)>,
}

/// One UART byte delivered between two cores.  See
/// `Chain::uart_tx_history`.
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub struct UartByteRecord {
    /// Universal-clock tick at the moment the byte was
    /// emitted from the source core's TX path -- i.e. the
    /// `Chain::current_tick` snapshot taken right before
    /// `Chain::deliver_uart_byte` calls
    /// `Eusart::deliver_rx_byte`.  The record is pushed
    /// regardless of whether the destination's RCSTA
    /// SPEN/CREN gate accepts the byte (gpsim's UART trace
    /// records bits on the wire similarly), so a record
    /// with this tick does NOT imply the byte ever
    /// landed in the destination's RCREG.
    pub tick: u64,
    /// Source core index in `Chain::cores`.
    pub src_core: usize,
    /// Destination core index in `Chain::cores`.
    pub dst_core: usize,
    /// The delivered byte.
    pub byte: u8,
}

impl Chain {
    /// Construct an empty chain with no cores.  Callers
    /// `push_core` to add CONTROL + MAINs in firmware
    /// order.
    pub fn new() -> Self {
        Chain {
            cores: Vec::new(),
            stacks: Vec::new(),
            clocks: Vec::new(),
            boot_epochs: Vec::new(),
            current_tick: 0,
            events: EventQueue::new(),
            pinnet: PinNet::new(),
            uart_tx_history: Vec::new(),
            tas3108_slaves: Vec::new(),
            tas3108_couplings: Vec::new(),
            lcd_slaves: Vec::new(),
            lcd_couplings: Vec::new(),
        }
    }

    /// Push an HD44780 LCD slave into the chain.  Returns
    /// the slave's index for use by `couple_lcd`.  Task #34.
    pub fn push_lcd(&mut self, lcd: Hd44780) -> usize {
        let idx = self.lcd_slaves.len();
        self.lcd_slaves.push(lcd);
        idx
    }

    /// Wire an LCD slave (by index in `lcd_slaves`) to a
    /// controller core's GPIO bus.  After each
    /// `execute_core_step` the chain samples the
    /// controller's RS / E / D4..D7 pins and feeds them
    /// to every coupled LCD's pin observer.  Pin map (per
    /// V1.71 CONTROL `lcd_char_write`):
    /// `LATA[5]=RS`, `LATB[4]=E`, `PORTB[3:0]=D4..D7`.
    /// Task #34.
    pub fn couple_lcd(&mut self, controller_core_idx: usize, lcd_idx: usize) {
        assert!(
            controller_core_idx < self.cores.len(),
            "couple_lcd: controller_core_idx {} out of range (cores.len()={})",
            controller_core_idx,
            self.cores.len()
        );
        assert!(
            lcd_idx < self.lcd_slaves.len(),
            "couple_lcd: lcd_idx {} out of range (lcd_slaves.len()={})",
            lcd_idx,
            self.lcd_slaves.len()
        );
        self.lcd_couplings.push((controller_core_idx, lcd_idx));
    }

    /// Push a TAS3108 slave into the chain.  Returns the
    /// slave's index in `tas3108_slaves` for use by
    /// `couple_tas3108`.
    pub fn push_tas3108(&mut self, slave: Tas3108) -> usize {
        let idx = self.tas3108_slaves.len();
        self.tas3108_slaves.push(slave);
        idx
    }

    /// Wire a TAS3108 slave (by index in `tas3108_slaves`)
    /// to a master core's MSSP I²C bus.  After each
    /// `execute_core_step`, every Start/Stop/RepeatedStart/
    /// TxByte completion on `master_core_idx`'s MSSP is
    /// routed to this slave.  A single slave may be
    /// coupled to multiple masters (multi-master bus); a
    /// single master may have multiple slaves coupled.
    pub fn couple_tas3108(
        &mut self,
        master_core_idx: usize,
        slave_idx: usize,
    ) {
        assert!(
            master_core_idx < self.cores.len(),
            "master_core_idx {} out of range ({} cores)",
            master_core_idx,
            self.cores.len()
        );
        assert!(
            slave_idx < self.tas3108_slaves.len(),
            "slave_idx {} out of range ({} slaves)",
            slave_idx,
            self.tas3108_slaves.len()
        );
        self.tas3108_couplings.push((master_core_idx, slave_idx));
    }

    /// Wire source-core EUSART TX to destination-core
    /// EUSART RX.  Phase-3.5 will dispatch byte
    /// propagation through `pinnet.uart` on each
    /// CoreInstructionComplete event.
    pub fn couple_uart(
        &mut self,
        src_core: usize,
        src_tx_pin: PinId,
        dst_core: usize,
        dst_rx_pin: PinId,
    ) {
        self.pinnet
            .couple_uart(src_core, src_tx_pin, dst_core, dst_rx_pin);
    }

    /// Wire a general-purpose source-core pin to a
    /// destination-core pin.  Used for MCLR/RA0 wakeup,
    /// LCD strobes, button-matrix rows, etc.
    pub fn couple_pin(
        &mut self,
        src_core: usize,
        src_pin: PinId,
        dst_core: usize,
        dst_pin: PinId,
    ) {
        self.pinnet
            .couple_pin(src_core, src_pin, dst_core, dst_pin);
    }

    /// Wire a master-mode I²C bus on `master_core` to a
    /// virtual slave (e.g. the TAS3108 DSP model).
    pub fn couple_i2c_slave(
        &mut self,
        master_core: usize,
        master_sda: PinId,
        master_scl: PinId,
        slave_id: u32,
    ) {
        self.pinnet
            .couple_i2c_slave(master_core, master_sda, master_scl, slave_id);
    }

    /// Add a core to the chain with a fresh `Stack` and
    /// the variant's nominal `ClockDomain` (no drift).
    /// Returns the core's index.  Use
    /// `push_core_with_clock` to start a core with a
    /// non-zero drift_ppm.
    pub fn push_core(&mut self, core: Core) -> usize {
        let variant = core.variant();
        self.push_core_with_clock(core, ClockDomain::new(variant))
    }

    /// Add a core with an explicit `ClockDomain` (e.g. for
    /// tests that exercise drift).  Returns the core's
    /// index.
    pub fn push_core_with_clock(
        &mut self,
        core: Core,
        clock: ClockDomain,
    ) -> usize {
        let idx = self.cores.len();
        self.cores.push(core);
        self.stacks.push(Stack::new());
        self.clocks.push(clock);
        self.boot_epochs.push(0);
        idx
    }

    /// Universal-clock ticks-per-Tcy for `core_idx`.
    /// Wraps `peripherals::osc::ticks_per_tcy` for
    /// convenience.
    pub fn ticks_per_tcy(&self, core_idx: usize) -> u32 {
        osc::ticks_per_tcy(self.cores[core_idx].variant())
    }

    /// Advance the universal clock by `n_ticks`, draining
    /// every event whose deadline `<= current_tick + n_ticks`.
    /// Phase-3 sub-tasks fill in the actual handler bodies;
    /// the skeleton just advances the tick and consumes any
    /// pending events without dispatch.
    pub fn step_ticks(&mut self, n_ticks: u64) {
        let target = self.current_tick.saturating_add(n_ticks);
        while let Some(next) = self.events.peek() {
            if next.tick > target {
                break;
            }
            let event = self.events.pop().expect("peek/pop consistency");
            // Advance the universal clock to the event's
            // firing tick BEFORE dispatching so handlers
            // observe a coherent `current_tick`.  Phase-3.2+
            // handlers will rely on this for pin-network
            // propagation timing and peripheral deadline
            // routing.
            self.current_tick = event.tick;
            self.dispatch_event(event);
        }
        // After draining all due events, jump to the target
        // even if it's later than the last fired event.
        self.current_tick = target;
    }

    /// Step the chain in fixed-size chunks until either
    /// `predicate(self)` returns true OR the cumulative
    /// budget reaches `max_ticks`.  Returns the number of
    /// universal ticks actually advanced.
    ///
    /// Mirrors gpsim's
    /// `src/dlcp_fw/sim/chain_gpsim::SingleMainChainHarness::run_until_*`
    /// "step in chunks, peek for convergence" pattern.
    /// Useful for tests that need "wait until something
    /// happens" semantics: no need to pre-allocate a fixed
    /// multi-second budget when the convergence event might
    /// happen 100x sooner.
    ///
    /// Behavior contracts:
    ///   * `predicate` is evaluated BEFORE each chunk, so a
    ///     condition that's already true at entry returns
    ///     immediately (advances 0 ticks).
    ///   * On the final chunk the call may overshoot the
    ///     pre-`step_ticks` cursor by less than `chunk_ticks`
    ///     -- the harness clamps the last chunk to the
    ///     remaining budget so the total advance never
    ///     exceeds `max_ticks`.
    ///   * If `predicate` never becomes true within
    ///     `max_ticks`, the call returns after the budget
    ///     is exhausted.
    ///   * Panics if `chunk_ticks` is 0 (would be an
    ///     infinite loop on a never-true predicate).
    pub fn run_until(
        &mut self,
        chunk_ticks: u64,
        max_ticks: u64,
        mut predicate: impl FnMut(&Chain) -> bool,
    ) -> u64 {
        assert!(chunk_ticks > 0, "chunk_ticks must be > 0 to make progress");
        let start_tick = self.current_tick;
        loop {
            if predicate(self) {
                return self.current_tick - start_tick;
            }
            let advanced = self.current_tick - start_tick;
            if advanced >= max_ticks {
                return advanced;
            }
            let chunk = chunk_ticks.min(max_ticks - advanced);
            let pre = self.current_tick;
            self.step_ticks(chunk);
            // Defensive: `step_ticks` saturates at `u64::MAX`,
            // so a caller that starts with `current_tick`
            // already at `u64::MAX` (or near it with a huge
            // budget) would otherwise see the loop never make
            // progress AND never reach `max_ticks`.  Bail out
            // if a chunk advanced 0 ticks -- caller's budget
            // is effectively exhausted.  Codex review of
            // 9275e6f surfaced this LOW boundary case.
            if self.current_tick == pre {
                return advanced;
            }
        }
    }

    /// Dispatch one drained event.  Phase-3.5 wires:
    ///   * `CoreInstructionComplete`: execute one
    ///     instruction on the named core, deliver any
    ///     completed TX bytes directly to wired peer RXs,
    ///     reschedule the next completion event.
    ///   * `UartByteDelivery`: a queue-driven path that
    ///     `drain_completed_tx_bytes` does NOT use today
    ///     (delivery is synchronous from the source's
    ///     step) -- the variant + dispatch arm are
    ///     retained for Phase-4 dual-run if bit-level
    ///     propagation latency is later modelled.  Until
    ///     that wiring lands, the arm is unreachable from
    ///     normal dispatch.
    /// `PinPropagation` (general-purpose pin events) and
    /// `PeripheralDeadline` remain stubs until subsequent
    /// P3.x sub-tasks fill them in.
    fn dispatch_event(&mut self, event: Event) {
        match event.kind {
            EventKind::CoreInstructionComplete(core_idx) => {
                self.execute_core_step(core_idx);
            }
            EventKind::UartByteDelivery {
                uart_coupling_idx,
                byte,
            } => {
                self.deliver_uart_byte(uart_coupling_idx, byte);
            }
            EventKind::PinPropagation(_) => {
                // General-purpose pin events deferred to
                // P3.7 alongside the late-boot recovery
                // test that exercises MCLR / RA0 wakeup.
            }
            EventKind::PeripheralDeadline { .. } => {
                // Peripherals currently advance via
                // `core.advance_cycles -> tick_tcy`; the
                // queue-driven path is reserved for
                // peripherals whose deadline outruns the
                // executor (EEPROM 12 000-Tcy write, etc.)
                // -- to be wired alongside multi-core
                // EEPROM-write-time parity in P3.7.
            }
        }
    }

    /// Deliver a UART byte from a source-core's EUSART
    /// TX to the wired destination-core's EUSART RX.  The
    /// `uart_coupling_idx` indexes `pinnet.uart`; the byte
    /// is loaded into RCREG + sets RCIF on the destination
    /// (gated on the destination's RCSTA.SPEN AND CREN).
    fn deliver_uart_byte(&mut self, uart_coupling_idx: usize, byte: u8) {
        let coupling = match self.pinnet.uart.get(uart_coupling_idx) {
            Some(c) => c.clone(),
            None => return,
        };
        // Record the delivery in tx_history BEFORE the
        // destination-side write so the history reflects
        // wire-time ordering even if a future change adds
        // a destination-side `Result` that early-returns.
        // Recording on attempts (rather than only on
        // accepted bytes) matches gpsim ground-truth
        // semantics: gpsim's UART trace records bits on the
        // wire, regardless of whether the destination's
        // SPEN/CREN gate accepts them.
        self.uart_tx_history.push(UartByteRecord {
            tick: self.current_tick,
            src_core: coupling.src_core,
            dst_core: coupling.dst_core,
            byte,
        });
        // Borrow-checker: take a single &mut Core for the
        // destination, then split-borrow `peripherals` and
        // `memory` -- they're disjoint pub fields so the
        // compiler accepts the simultaneous &mut on each.
        let dst_core = &mut self.cores[coupling.dst_core];
        let memory = &mut dst_core.memory;
        let eusart = &mut dst_core.peripherals.eusart;
        eusart.deliver_rx_byte(byte, memory);
    }

    /// Execute one instruction on `core_idx`, deliver any
    /// EUSART TX bytes that completed shifting during the
    /// step directly to wired peer cores' EUSART RXs (no
    /// queue round-trip; see `drain_completed_tx_bytes`
    /// for the same-tick race rationale), and schedule the
    /// next `CoreInstructionComplete` event at the drifted-
    /// tick boundary derived from
    /// [`ClockDomain::apply_drift`].
    pub fn execute_core_step(&mut self, core_idx: usize) {
        let core = &mut self.cores[core_idx];
        let stack = &mut self.stacks[core_idx];
        // Best-effort: errors propagate as a panic for
        // now -- a real chain would distinguish "fatal"
        // cores (unknown opcode -> halt) from "warm
        // halt" (firmware-driven SLEEP) and surface them
        // to the test harness.  Phase-3.5 minimal scope
        // keeps the panic so test failures are obvious.
        let _ = step(core, stack)
            .unwrap_or_else(|e| panic!("exec::step failed on core {core_idx}: {e:?}"));
        self.drain_completed_tx_bytes(core_idx);
        self.dispatch_i2c_to_coupled_slaves(core_idx);
        self.dispatch_lcd_pins_to_coupled_slaves(core_idx);
        self.schedule_next_core_step(core_idx);
    }

    /// Sample the controller core's LCD-driving pins and
    /// feed the observation to every coupled HD44780 slave.
    /// Per V1.71 CONTROL's `lcd_char_write`: RS = LATA[5],
    /// E = LATB[4], D4..D7 = PORTB[3:0].  The LCD model's
    /// internal E-falling-edge detector pairs nibbles into
    /// bytes and dispatches to the HD44780 instruction
    /// decoder.  Task #34.
    fn dispatch_lcd_pins_to_coupled_slaves(&mut self, controller_core_idx: usize) {
        // Snapshot which LCDs this controller drives (avoid
        // borrow conflict with the mut self.lcd_slaves below).
        let coupled: Vec<usize> = self
            .lcd_couplings
            .iter()
            .filter_map(|&(c, l)| if c == controller_core_idx { Some(l) } else { None })
            .collect();
        if coupled.is_empty() {
            return;
        }
        // PIC18 SFR addresses (architectural, same on K20
        // and 2455).
        const LATA_ADDR: u16 = 0xF89;
        const LATB_ADDR: u16 = 0xF8A;
        const PORTB_ADDR: u16 = 0xF81;
        let core = &self.cores[controller_core_idx];
        let lata = core.memory.read_raw(Address::from_raw(LATA_ADDR));
        let latb = core.memory.read_raw(Address::from_raw(LATB_ADDR));
        let portb = core.memory.read_raw(Address::from_raw(PORTB_ADDR));
        let rs = (lata >> 5) & 1 != 0;
        let e = (latb >> 4) & 1 != 0;
        let nibble = portb & 0x0F;
        for slave_idx in coupled {
            self.lcd_slaves[slave_idx].observe_pins(rs, e, nibble);
        }
    }

    /// Drain the master core's MSSP `last_bus_event` (set
    /// by `complete_start` / `complete_stop` /
    /// `complete_repeated_start` / `complete_tx_byte` /
    /// `complete_rx_byte` during the most-recent tick) and
    /// route it to every TAS3108 slave coupled to this
    /// master.  For TxByte events, if any slave ACKs the
    /// transmitted byte, override the master's ACKSTAT to
    /// 0 (cleared) so the firmware sees "slave ACKed".
    /// Default `complete_tx_byte` already left ACKSTAT=1
    /// (NACK), so a no-slave-coupling path keeps the
    /// existing bus-less behavior.
    fn dispatch_i2c_to_coupled_slaves(&mut self, master_core_idx: usize) {
        let event = match self.cores[master_core_idx]
            .peripherals
            .mssp
            .take_last_bus_event()
        {
            Some(e) => e,
            None => return,
        };
        // Snapshot which slaves are coupled to this master
        // (avoid borrow conflict with the mut self.cores
        // memory access below).
        let coupled_slave_indices: Vec<usize> = self
            .tas3108_couplings
            .iter()
            .filter_map(|&(mc, si)| if mc == master_core_idx { Some(si) } else { None })
            .collect();
        // Drive each coupled slave's I²C state machine.
        // For TxByte, also override ACKSTAT if any slave
        // ACKs.  Other events (Start/Stop/RepeatedStart)
        // are pure state transitions on the slave; no
        // master-side memory effect today.
        let mut any_slave_acked = false;
        for slave_idx in coupled_slave_indices {
            let slave = &mut self.tas3108_slaves[slave_idx];
            match event {
                I2cBusEvent::Start => slave.on_start(),
                I2cBusEvent::RepeatedStart => slave.on_repeated_start(),
                I2cBusEvent::Stop => slave.on_stop(),
                I2cBusEvent::TxByte(byte) => {
                    if slave.consume_tx_byte(byte) {
                        any_slave_acked = true;
                    }
                }
                I2cBusEvent::RxByte => {
                    // Phase-3.5+: a coupled slave drives the
                    // RX byte into SSPBUF.  V3.1's chain
                    // doesn't read the DSP, so we leave the
                    // SSPBUF byte at whatever `complete_rx_byte`
                    // left it (random / zero).  Track as
                    // future work alongside task #24.
                }
            }
        }
        if let I2cBusEvent::TxByte(_) = event {
            if any_slave_acked {
                Mssp::override_acked(&mut self.cores[master_core_idx].memory);
            }
        }
    }

    /// Pull any bytes that the source-core EUSART
    /// completed shifting since the last drain, and
    /// deliver them directly to the wired destination
    /// cores' EUSART RCREGs.
    ///
    /// Direct delivery (not through the event queue) is
    /// chosen so a same-tick peer `CoreInstructionComplete`
    /// scheduled BEFORE this drain doesn't race the byte:
    /// queue tie-break is push-order, so a freshly-pushed
    /// `UartByteDelivery` would fire AFTER the peer
    /// already-queued instruction at the same tick, and
    /// the peer would read stale RCREG.  Direct delivery
    /// commits the byte before the next dispatch loop
    /// iteration sees it.  Phase-4 dual-run can re-route
    /// through the queue with an explicit propagation
    /// delay if bit-level timing fidelity demands it.
    fn drain_completed_tx_bytes(&mut self, src_core_idx: usize) {
        // Snapshot which UART couplings source from this
        // core (by index).  We need the snapshot up-front
        // because we'll mutably borrow the source core's
        // EUSART next.
        let matching_couplings: Vec<usize> = self
            .pinnet
            .uart
            .iter()
            .enumerate()
            .filter_map(|(idx, c)| {
                if c.src_core == src_core_idx {
                    Some(idx)
                } else {
                    None
                }
            })
            .collect();
        if matching_couplings.is_empty() {
            // Nothing wired -- still drain the FIFO so it
            // doesn't accumulate and force-deliver
            // already-aged bytes when a coupling lands
            // later.
            let core = &mut self.cores[src_core_idx];
            while core.peripherals.eusart.take_completed_tx_byte().is_some() {}
            return;
        }
        // Drain bytes from the source core's EUSART into
        // a local Vec first (split-borrow: the &mut on
        // self.cores conflicts with the later destination-
        // core borrow).
        let bytes: Vec<u8> = {
            let src_core = &mut self.cores[src_core_idx];
            let eusart = &mut src_core.peripherals.eusart;
            let mut acc = Vec::new();
            while let Some(byte) = eusart.take_completed_tx_byte() {
                acc.push(byte);
            }
            acc
        };
        // Deliver each byte directly to every matching
        // coupling's destination core.  The
        // UartByteDelivery event variant is retained in
        // the EventKind enum for Phase-4 dual-run delayed
        // propagation, but Phase-3.5 minimum-viable uses
        // the synchronous path.
        for byte in bytes {
            for &coupling_idx in &matching_couplings {
                self.deliver_uart_byte(coupling_idx, byte);
            }
        }
    }

    /// Schedule a `CoreInstructionComplete` event for the
    /// given core at its next instruction-complete tick,
    /// derived from the core's current Tcy count + the
    /// per-core drifted ticks/Tcy + the boot-offset epoch.
    /// Without the epoch, a late-booted core's first
    /// instruction would fire at boot_offset, then the
    /// SECOND would schedule at `cycles * factor` --
    /// before boot_offset for any non-trivial offset --
    /// causing the queue to fire it immediately and
    /// effectively collapsing the boot delay.  Tracking
    /// the per-core epoch keeps the relative-to-boot
    /// scheduling semantic intact.
    pub fn schedule_next_core_step(&mut self, core_idx: usize) {
        let tcy = self.cores[core_idx].cycles();
        let factor = self.clocks[core_idx].nominal_ticks_per_tcy as u64;
        let nominal_tick = tcy.saturating_mul(factor);
        let drifted_tick = self.clocks[core_idx].apply_drift(nominal_tick);
        let epoch = self.boot_epochs[core_idx];
        let absolute_tick = epoch.saturating_add(drifted_tick);
        self.events
            .push(absolute_tick, EventKind::CoreInstructionComplete(core_idx));
    }

    /// Apply POR to every core in the chain.  Helper for
    /// Phase-3.5 fixture builders that need each core's
    /// SFRs at K20_POR before any cross-core stimulus runs.
    pub fn apply_reset_all(&mut self, source: ResetSource) {
        for idx in 0..self.cores.len() {
            apply_reset(&mut self.cores[idx], &mut self.stacks[idx], source);
        }
        // Clear the UART byte-delivery history so a
        // re-bootstrap doesn't carry pre-reset traffic
        // forward into a fresh run.  Cycle counters and
        // queued events are cleared by
        // `schedule_initial_steps` (callers typically pair
        // `apply_reset_all` with that) -- this drop is
        // independent so a future `apply_reset_all`-only
        // path stays consistent.
        self.uart_tx_history.clear();
    }

    /// Bootstrap each core's first `CoreInstructionComplete`
    /// event onto the queue at the boot-offset tick.  Also
    /// records the offset as the per-core epoch so all
    /// subsequent `schedule_next_core_step` calls add it
    /// to their absolute tick (preserving the boot delay
    /// across the whole run instead of collapsing back to
    /// tick 0 after the first instruction).  The
    /// `boot_offsets[idx]` slot supplies the offset for
    /// `cores[idx]`; vec must be the same length as
    /// `cores`.
    ///
    /// Re-bootstrap safety: any pending events in the
    /// queue are dropped first and per-core cycle counters
    /// are reset to 0.  This makes the call safe to use
    /// post-MCLR re-bootstrap mid-run (e.g. P3.7's late-
    /// boot recovery test), not just for the initial
    /// chain bring-up.
    pub fn schedule_initial_steps(&mut self, boot_offsets: &[u64]) {
        assert_eq!(
            boot_offsets.len(),
            self.cores.len(),
            "boot_offsets length must match number of cores"
        );
        // Drop any pre-existing events so a re-bootstrap
        // doesn't fire stale events at outdated ticks.
        self.events = EventQueue::new();
        // Reset per-core cycle counters so subsequent
        // schedule_next_core_step computations are
        // relative to this fresh epoch.  Memory / stack /
        // peripheral state is left to the caller (typically
        // `apply_reset_all` precedes this).
        for core in self.cores.iter_mut() {
            core.reset_cycles_for_test();
        }
        // Reset the universal-clock head so step_ticks(N)
        // advances from the new epoch rather than carrying
        // pre-reset history forward.
        self.current_tick = 0;
        for (idx, &offset) in boot_offsets.iter().enumerate() {
            self.boot_epochs[idx] = offset;
            self.events
                .push(offset, EventKind::CoreInstructionComplete(idx));
        }
    }
}

impl Default for Chain {
    fn default() -> Self {
        Chain::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::memory::Variant;

    #[test]
    fn empty_chain_step_ticks_advances_clock_only() {
        let mut chain = Chain::new();
        assert_eq!(chain.current_tick, 0);
        chain.step_ticks(1000);
        assert_eq!(chain.current_tick, 1000);
        chain.step_ticks(500);
        assert_eq!(chain.current_tick, 1500);
    }

    #[test]
    fn run_until_returns_immediately_when_predicate_already_true() {
        let mut chain = Chain::new();
        let ticks = chain.run_until(100, 10_000, |_| true);
        assert_eq!(ticks, 0, "predicate-already-true must advance 0 ticks");
        assert_eq!(chain.current_tick, 0);
    }

    #[test]
    fn run_until_runs_to_max_when_predicate_never_true() {
        let mut chain = Chain::new();
        let ticks = chain.run_until(100, 10_000, |_| false);
        assert_eq!(ticks, 10_000);
        assert_eq!(chain.current_tick, 10_000);
    }

    #[test]
    fn run_until_returns_early_when_predicate_becomes_true_mid_run() {
        let mut chain = Chain::new();
        // Predicate fires when current_tick reaches 5000.
        let ticks = chain.run_until(100, 100_000, |c| c.current_tick >= 5000);
        // The call must have advanced AT LEAST 5000 and AT
        // MOST 5000 + 99 ticks (predicate is checked before
        // each chunk, and the check at 5100 fires AFTER the
        // chunk that brought us to 5100; but the check at
        // 5000 fires BEFORE the chunk that would have
        // advanced past it).  Actually: predicate is checked
        // first; if false, advance one chunk.  So at iter 0
        // tick=0; iter 1 tick=100; ...; iter 50 tick=5000 ->
        // predicate true -> return 5000.
        assert_eq!(ticks, 5000);
        assert_eq!(chain.current_tick, 5000);
    }

    #[test]
    fn run_until_clamps_final_chunk_to_remaining_budget() {
        let mut chain = Chain::new();
        // chunk_ticks=300, max_ticks=1000 -> last chunk is
        // clamped to 100 (1000 - 900).  No overshoot.
        let ticks = chain.run_until(300, 1000, |_| false);
        assert_eq!(ticks, 1000, "final chunk must clamp to budget remainder");
    }

    #[test]
    #[should_panic(expected = "chunk_ticks must be > 0")]
    fn run_until_chunk_ticks_zero_panics() {
        let mut chain = Chain::new();
        let _ = chain.run_until(0, 1000, |_| false);
    }

    /// Codex review of 9275e6f: at the `u64::MAX` boundary
    /// `step_ticks` saturates and subsequent chunks make
    /// no progress.  Without the no-progress break,
    /// `run_until` would spin forever when the predicate
    /// stays false.
    #[test]
    fn run_until_breaks_when_step_ticks_saturates_at_u64_max() {
        let mut chain = Chain::new();
        // Pin the chain right against the u64 ceiling.
        chain.current_tick = u64::MAX - 100;
        // Ask for far more budget than the remaining
        // representable ticks (100) -- step_ticks will
        // saturate at u64::MAX after one chunk and stop
        // making progress.
        let advanced = chain.run_until(1000, 1_000_000, |_| false);
        // The actual advance is at most 100 ticks (the
        // remaining headroom); the no-progress break must
        // fire on the second chunk and return.
        assert!(
            advanced <= 100,
            "must not advance beyond u64::MAX boundary; got {advanced}"
        );
        assert_eq!(chain.current_tick, u64::MAX);
    }

    #[test]
    fn push_core_assigns_sequential_indices() {
        let mut chain = Chain::new();
        let i0 = chain.push_core(Core::new(Variant::Pic18F25K20));
        let i1 = chain.push_core(Core::new(Variant::Pic18F2455));
        assert_eq!(i0, 0);
        assert_eq!(i1, 1);
    }

    #[test]
    fn ticks_per_tcy_matches_per_variant_factor() {
        let mut chain = Chain::new();
        chain.push_core(Core::new(Variant::Pic18F25K20));
        chain.push_core(Core::new(Variant::Pic18F2455));
        assert_eq!(chain.ticks_per_tcy(0), 16);
        assert_eq!(chain.ticks_per_tcy(1), 12);
    }

    #[test]
    fn step_ticks_drains_due_events_in_order() {
        let mut chain = Chain::new();
        chain.events.push(50, EventKind::PinPropagation(1));
        chain.events.push(20, EventKind::PinPropagation(2));
        chain.events.push(80, EventKind::PinPropagation(3));
        chain.step_ticks(60);
        // Events at 20 and 50 fired (no-op dispatch); event
        // at 80 is still scheduled.
        assert_eq!(chain.events.len(), 1);
        assert_eq!(chain.current_tick, 60);
    }

    #[test]
    fn step_ticks_does_not_overshoot() {
        let mut chain = Chain::new();
        chain.events.push(100, EventKind::PinPropagation(1));
        chain.step_ticks(50);
        // Event at 100 NOT yet drained.
        assert_eq!(chain.events.len(), 1);
        // Step further; now drains.
        chain.step_ticks(60);
        assert_eq!(chain.current_tick, 110);
        assert_eq!(chain.events.len(), 0);
    }

    /// Coupling-API smoke: each `couple_*` call records
    /// one entry in the appropriate `pinnet` vec.
    #[test]
    fn couple_uart_records_in_pinnet() {
        let mut chain = Chain::new();
        chain.push_core(Core::new(Variant::Pic18F25K20));
        chain.push_core(Core::new(Variant::Pic18F2455));
        chain.couple_uart(
            0,
            crate::pinnet::default_tx_pin(),
            1,
            crate::pinnet::default_rx_pin(),
        );
        assert_eq!(chain.pinnet.uart.len(), 1);
        assert_eq!(chain.pinnet.uart[0].src_core, 0);
        assert_eq!(chain.pinnet.uart[0].dst_core, 1);
    }

    #[test]
    fn couple_pin_records_in_pinnet() {
        let mut chain = Chain::new();
        chain.push_core(Core::new(Variant::Pic18F25K20));
        chain.push_core(Core::new(Variant::Pic18F2455));
        let src = crate::pinnet::PinId {
            port: crate::pinnet::PortLetter::C,
            bit: 0,
        };
        let dst = crate::pinnet::PinId {
            port: crate::pinnet::PortLetter::A,
            bit: 0,
        };
        chain.couple_pin(0, src, 1, dst);
        assert_eq!(chain.pinnet.pin.len(), 1);
    }

    #[test]
    fn couple_i2c_slave_records_in_pinnet() {
        let mut chain = Chain::new();
        chain.push_core(Core::new(Variant::Pic18F2455));
        let sda = crate::pinnet::PinId {
            port: crate::pinnet::PortLetter::C,
            bit: 4,
        };
        let scl = crate::pinnet::PinId {
            port: crate::pinnet::PortLetter::C,
            bit: 3,
        };
        chain.couple_i2c_slave(0, sda, scl, 7);
        assert_eq!(chain.pinnet.i2c.len(), 1);
        assert_eq!(chain.pinnet.i2c[0].slave_id, 7);
    }

    #[test]
    fn schedule_next_core_step_uses_universal_tick() {
        let mut chain = Chain::new();
        let idx = chain.push_core(Core::new(Variant::Pic18F25K20));
        // Hand-set a Tcy count.
        chain.cores[idx].advance_cycles(100);
        chain.schedule_next_core_step(idx);
        let event = chain.events.peek().unwrap();
        // K20 ticks_per_tcy = 16; 100 Tcy * 16 = 1600 ticks.
        assert_eq!(event.tick, 1600);
        assert_eq!(
            event.kind,
            EventKind::CoreInstructionComplete(idx),
        );
    }

    /// Drift-aware scheduling: a core with +20 000 ppm
    /// drift schedules its 100-Tcy boundary 20 000 ppm
    /// later than the nominal 1600-tick mark.
    #[test]
    fn schedule_next_core_step_applies_drift() {
        let mut chain = Chain::new();
        let idx = chain.push_core_with_clock(
            Core::new(Variant::Pic18F25K20),
            ClockDomain::with_drift_ppm(Variant::Pic18F25K20, 20_000),
        );
        chain.cores[idx].advance_cycles(100);
        chain.schedule_next_core_step(idx);
        let event = chain.events.peek().unwrap();
        // 100 Tcy * 16 ticks/Tcy = 1600 nominal.  With +2 %
        // drift: 1600 * 1.02 = 1632.
        assert_eq!(event.tick, 1632);
    }

    /// Build a flash with a single BRA -1 self-loop at
    /// PC=0; bootstraps an executor to run forever.  Used
    /// by the multicore tests below to confirm the chain's
    /// dispatch path actually advances the named core.
    fn build_self_loop_flash() -> Vec<u8> {
        let mut flash = vec![0u8; 32 * 1024];
        flash[0] = 0xFF;
        flash[1] = 0xD7; // BRA -1
        flash
    }

    /// Single-core dispatch: schedule the first
    /// CoreInstructionComplete at tick 0; step_ticks(N)
    /// drains it, runs `exec::step`, reschedules.
    /// After enough ticks the core's cycle counter
    /// advances.  K20 BRA = 2 Tcy * 16 ticks/Tcy = 32
    /// universal ticks per BRA iteration.  step_ticks(1000)
    /// runs ~31 BRA iterations -> ~62 Tcy.
    #[test]
    fn single_core_dispatch_advances_cycle_counter() {
        let mut chain = Chain::new();
        let mut core = Core::new(Variant::Pic18F25K20);
        core.flash_mut().copy_from_slice(&build_self_loop_flash());
        let idx = chain.push_core(core);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0]);
        chain.step_ticks(1000);
        let cycles = chain.cores[idx].cycles();
        assert!(
            (50..75).contains(&cycles),
            "core cycles should reflect ~62 Tcy after 1000 universal ticks (got {cycles})"
        );
    }

    /// Two cores running concurrently: a K20 (16 ticks/Tcy)
    /// and a 2455 (12 ticks/Tcy) both with self-loop BRA
    /// firmware.  After 1000 universal ticks, each should
    /// have advanced its own Tcy counter according to its
    /// per-core ticks/Tcy factor.  K20: ~31 BRAs; 2455:
    /// ~41 BRAs.
    #[test]
    fn two_cores_advance_at_their_own_clock_rates() {
        let mut chain = Chain::new();
        let mut k20 = Core::new(Variant::Pic18F25K20);
        k20.flash_mut().copy_from_slice(&build_self_loop_flash());
        let i_k20 = chain.push_core(k20);
        let mut p2455 = Core::new(Variant::Pic18F2455);
        p2455.flash_mut().copy_from_slice(&build_self_loop_flash());
        let i_2455 = chain.push_core(p2455);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0, 0]);
        chain.step_ticks(1000);
        let k20_cy = chain.cores[i_k20].cycles();
        let p2455_cy = chain.cores[i_2455].cycles();
        // K20: BRA = 2 Tcy * 16 ticks = 32 ticks/iter ->
        // 1000/32 ≈ 31 iterations -> ~62 cycles.
        assert!(
            (50..75).contains(&k20_cy),
            "K20 should be ~62 cycles, got {k20_cy}"
        );
        // 2455: BRA = 2 Tcy * 12 ticks = 24 ticks/iter ->
        // 1000/24 ≈ 41 iterations -> ~82 cycles.
        assert!(
            (75..100).contains(&p2455_cy),
            "2455 should be ~82 cycles, got {p2455_cy}"
        );
        // 2455 must have advanced more cycles than K20
        // because its clock is faster (12 vs 16 ticks/Tcy).
        assert!(p2455_cy > k20_cy, "2455 should outpace K20");
    }

    /// Boot-offset honored: a core with boot_offset=500
    /// doesn't step before universal tick 500 but does step
    /// after.
    #[test]
    fn boot_offset_delays_first_step() {
        let mut chain = Chain::new();
        let mut core = Core::new(Variant::Pic18F25K20);
        core.flash_mut().copy_from_slice(&build_self_loop_flash());
        let idx = chain.push_core(core);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[500]);
        // Step to tick 400 -- before boot offset.  Core
        // shouldn't have advanced.
        chain.step_ticks(400);
        assert_eq!(chain.cores[idx].cycles(), 0);
        // Step past boot offset.  Core should now run.
        chain.step_ticks(600);
        assert!(chain.cores[idx].cycles() > 0);
    }

    /// Regression: re-bootstrap mid-run drops stale events
    /// and resets cycle counters so the new boot epoch
    /// arithmetic is correct.  Without the fix, the queue
    /// would carry pre-MCLR events and the per-core
    /// cycles counter would keep its pre-reset value,
    /// causing schedule_next_core_step to compute ticks
    /// relative to a stale epoch.
    #[test]
    fn schedule_initial_steps_drops_stale_events_and_resets_cycles() {
        let mut chain = Chain::new();
        let mut core = Core::new(Variant::Pic18F25K20);
        core.flash_mut().copy_from_slice(&build_self_loop_flash());
        let idx = chain.push_core(core);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0]);
        // Run 1000 ticks to accumulate cycles + queue
        // state.
        chain.step_ticks(1000);
        assert!(chain.cores[idx].cycles() > 0);
        assert!(chain.events.len() > 0);

        // Re-bootstrap (simulating MCLR + new epoch).
        chain.apply_reset_all(ResetSource::Mclr);
        chain.schedule_initial_steps(&[2000]);

        // Cycles reset; queue holds exactly one new event
        // at tick 2000; current_tick reset.
        assert_eq!(chain.cores[idx].cycles(), 0);
        assert_eq!(chain.events.len(), 1);
        assert_eq!(chain.current_tick, 0);
        assert_eq!(chain.boot_epochs[idx], 2000);
    }

    /// End-to-end UART chain: source core transmits a
    /// byte; chain dispatch propagates it to the wired
    /// destination core's EUSART RX (RCREG + RCIF).
    #[test]
    fn uart_byte_propagates_from_src_tx_to_dst_rx() {
        // Build a flash that runs the V1.71 EUSART setup
        // + a TXREG=0x55 write, then loops on BRA -1.
        // Reuse the existing peripheral_eusart_parity
        // demo encoding inline here -- 11 setup
        // instructions + a 960-Tcy frame on the source.
        let mut flash_src = vec![0u8; 32 * 1024];
        let prog: &[(u32, [u8; 2])] = &[
            (0x0000, [0x05, 0x0E]),       // MOVLW 0x05
            (0x0002, [0xAF, 0x6E]),       // MOVWF SPBRG (a=0)
            (0x0004, [0x20, 0x0E]),       // MOVLW 0x20 (TXEN)
            (0x0006, [0xAC, 0x6E]),       // MOVWF TXSTA
            (0x0008, [0x80, 0x0E]),       // MOVLW 0x80 (SPEN)
            (0x000A, [0xAB, 0x6E]),       // MOVWF RCSTA
            (0x000C, [0x40, 0x0E]),       // MOVLW 0x40
            (0x000E, [0xB8, 0x6E]),       // MOVWF BAUDCON
            (0x0010, [0x55, 0x0E]),       // MOVLW 0x55
            (0x0012, [0xAD, 0x6E]),       // MOVWF TXREG
            (0x0014, [0xFF, 0xD7]),       // BRA -1
        ];
        for (a, bytes) in prog {
            flash_src[*a as usize] = bytes[0];
            flash_src[*a as usize + 1] = bytes[1];
        }
        // Destination flash: enable RX (SPEN | CREN) then
        // BRA loop.
        let mut flash_dst = vec![0u8; 32 * 1024];
        let dst_prog: &[(u32, [u8; 2])] = &[
            (0x0000, [0x90, 0x0E]),       // MOVLW 0x90 (SPEN|CREN)
            (0x0002, [0xAB, 0x6E]),       // MOVWF RCSTA
            (0x0004, [0xFF, 0xD7]),       // BRA -1
        ];
        for (a, bytes) in dst_prog {
            flash_dst[*a as usize] = bytes[0];
            flash_dst[*a as usize + 1] = bytes[1];
        }

        let mut chain = Chain::new();
        let mut src = Core::new(Variant::Pic18F25K20);
        src.flash_mut().copy_from_slice(&flash_src);
        let i_src = chain.push_core(src);
        let mut dst = Core::new(Variant::Pic18F25K20);
        dst.flash_mut().copy_from_slice(&flash_dst);
        let i_dst = chain.push_core(dst);
        chain.couple_uart(
            i_src,
            crate::pinnet::default_tx_pin(),
            i_dst,
            crate::pinnet::default_rx_pin(),
        );
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0, 0]);

        // Step long enough for both cores to set up + the
        // 960-Tcy frame to drain.  K20 setup ~11 cycles =
        // 11 * 16 = 176 ticks; frame = 960 Tcy = 15360
        // ticks.  Give it 30 000.
        chain.step_ticks(30_000);

        // Destination's RCREG should hold 0x55.
        let rcreg = chain.cores[i_dst].memory.read_raw(
            crate::memory::Address::from_raw(0xFAE),
        );
        assert_eq!(rcreg, 0x55, "destination RCREG must hold the propagated byte");
        // PIR1.RCIF (bit 5) must be set.
        let pir1 = chain.cores[i_dst].memory.read_raw(
            crate::memory::Address::from_raw(0xF9E),
        );
        assert_eq!(pir1 & (1 << 5), 1 << 5, "destination RCIF must assert");
    }

    /// Regression: `drain_completed_tx_bytes` -- the path
    /// that was actually changed -- must commit completed
    /// TX bytes to the destination's RCREG synchronously
    /// AND must NOT enqueue a `UartByteDelivery` event in
    /// the queue.  Prior to this fix, the drain pushed a
    /// `UartByteDelivery` at `current_tick` that lost the
    /// seq tie-break to an already-queued peer
    /// `CoreInstructionComplete` (which then polled stale
    /// RCREG/RCIF).
    ///
    /// This test inspects state DURING drain rather than
    /// after `step_ticks`, because `step_ticks` would also
    /// dispatch any queued `UartByteDelivery` event before
    /// returning -- letting the OLD code path pass a
    /// post-`step_ticks` queue scan.  Instead, we:
    ///   1. inject a completed-TX byte directly into the
    ///      source EUSART (via the test escape hatch),
    ///   2. call `chain.drain_completed_tx_bytes(src_idx)`
    ///      directly so we own the moment between drain
    ///      and any subsequent dispatch,
    ///   3. assert RCREG is set AND zero
    ///      `UartByteDelivery` events are queued.
    /// On the d916ffa (queue-based) path, step (3) would
    /// observe one queued event and fail.
    #[test]
    fn drain_completed_tx_bytes_does_not_enqueue_uart_byte_delivery_event() {
        let mut chain = Chain::new();
        let i_src = chain.push_core(Core::new(Variant::Pic18F25K20));
        let mut dst = Core::new(Variant::Pic18F25K20);
        // RCSTA = 0xFAB; bits 0x90 = SPEN | CREN -- enable
        // RX so `deliver_rx_byte` accepts the byte.  No
        // executor stepping is required for this test --
        // we exercise the chain-level drain path in
        // isolation.
        dst.memory.write_raw(
            crate::memory::Address::from_raw(0xFAB),
            0x90,
        );
        let i_dst = chain.push_core(dst);
        chain.couple_uart(
            i_src,
            crate::pinnet::default_tx_pin(),
            i_dst,
            crate::pinnet::default_rx_pin(),
        );

        // Inject a byte into the source EUSART's
        // completed-TX FIFO via the test escape hatch
        // (mirrors what `tick_tcy` would do at frame
        // completion).  No event is queued yet.
        chain.cores[i_src]
            .peripherals
            .eusart
            .push_completed_tx_byte_for_test(0xDE);

        let queued_before = chain
            .events
            .iter()
            .filter(|e| matches!(e.kind, EventKind::UartByteDelivery { .. }))
            .count();
        assert_eq!(queued_before, 0, "precondition: no UartByteDelivery queued");

        // Drive the drain directly.  On the OLD queue-based
        // path, this call would push a `UartByteDelivery`
        // event into `chain.events` at `current_tick`.  On
        // the NEW direct-delivery path, the byte commits
        // into the destination's memory synchronously and
        // no event is enqueued.
        chain.drain_completed_tx_bytes(i_src);

        // (a) byte committed to destination RCREG (0xFAE)
        // and PIR1.RCIF asserted (0xF9E bit 5).
        let rcreg = chain.cores[i_dst].memory.read_raw(
            crate::memory::Address::from_raw(0xFAE),
        );
        assert_eq!(rcreg, 0xDE, "destination RCREG must hold the byte after drain");
        let pir1 = chain.cores[i_dst].memory.read_raw(
            crate::memory::Address::from_raw(0xF9E),
        );
        assert_eq!(pir1 & (1 << 5), 1 << 5, "destination RCIF must assert after drain");

        // (b) NO `UartByteDelivery` event was enqueued by
        // the drain.  Locks in the synchronous-delivery
        // contract.  This is the assertion that distinguishes
        // the new path from the d916ffa queue-based path.
        let queued_after = chain
            .events
            .iter()
            .filter(|e| matches!(e.kind, EventKind::UartByteDelivery { .. }))
            .count();
        assert_eq!(
            queued_after, 0,
            "drain_completed_tx_bytes must not enqueue UartByteDelivery events; \
             synchronous delivery is required to avoid the same-tick seq race"
        );
    }

    /// `Chain::uart_tx_history` records every successful
    /// `deliver_uart_byte` call with the (tick, src_core,
    /// dst_core, byte) tuple, and `apply_reset_all` clears
    /// the history so a re-bootstrap starts fresh.
    #[test]
    fn uart_tx_history_records_deliveries_and_clears_on_reset() {
        let mut chain = Chain::new();
        let i_src = chain.push_core(Core::new(Variant::Pic18F25K20));
        let mut dst = Core::new(Variant::Pic18F25K20);
        // RCSTA = 0xFAB; SPEN | CREN = 0x90 -- enable RX so
        // `deliver_rx_byte` accepts the byte.
        dst.memory.write_raw(
            crate::memory::Address::from_raw(0xFAB),
            0x90,
        );
        let i_dst = chain.push_core(dst);
        chain.couple_uart(
            i_src,
            crate::pinnet::default_tx_pin(),
            i_dst,
            crate::pinnet::default_rx_pin(),
        );

        chain.current_tick = 4242;
        assert!(
            chain.uart_tx_history.is_empty(),
            "history starts empty"
        );
        chain.deliver_uart_byte(0, 0xC3);
        chain.current_tick = 4243;
        chain.deliver_uart_byte(0, 0xA5);

        assert_eq!(chain.uart_tx_history.len(), 2);
        assert_eq!(
            chain.uart_tx_history[0],
            UartByteRecord {
                tick: 4242,
                src_core: i_src,
                dst_core: i_dst,
                byte: 0xC3,
            }
        );
        assert_eq!(
            chain.uart_tx_history[1],
            UartByteRecord {
                tick: 4243,
                src_core: i_src,
                dst_core: i_dst,
                byte: 0xA5,
            }
        );

        // Reset clears the history.
        chain.apply_reset_all(ResetSource::PowerOn);
        assert!(
            chain.uart_tx_history.is_empty(),
            "apply_reset_all must clear uart_tx_history"
        );
    }

    /// Regression: late-booted core stays delayed across
    /// MULTIPLE instructions.  Prior to the boot-epoch fix,
    /// the second instruction would schedule at
    /// `cycles * factor = 32` (in the past) which the
    /// queue would fire immediately, collapsing the
    /// boot-offset delay.  After the fix, all subsequent
    /// instructions land at `boot_offset + cycles * factor`
    /// so the core stays at its delayed cadence.
    #[test]
    fn boot_offset_persists_across_multiple_instructions() {
        let mut chain = Chain::new();
        let mut core = Core::new(Variant::Pic18F25K20);
        core.flash_mut().copy_from_slice(&build_self_loop_flash());
        let idx = chain.push_core(core);
        chain.apply_reset_all(ResetSource::PowerOn);
        // Boot offset = 1500 (well past where a non-
        // delayed core would have completed many BRAs).
        chain.schedule_initial_steps(&[1500]);
        // Step to tick 1000 -- still before boot.  Core
        // hasn't run.
        chain.step_ticks(1000);
        assert_eq!(chain.cores[idx].cycles(), 0);
        // Step to tick 2500.  Core has been running for
        // 2500 - 1500 = 1000 ticks.  At 32 ticks/BRA
        // -> 31 iterations -> 62 cycles.
        chain.step_ticks(1500);
        let cycles = chain.cores[idx].cycles();
        assert!(
            (50..75).contains(&cycles),
            "boot-delayed core should advance ~62 cycles in 1000 post-boot ticks (got {cycles})"
        );
        // Critically: also verify the chain's
        // current_tick reflects the boot-offset-respecting
        // dispatch, not a collapsed catch-up.  current_tick
        // is the most recent event's firing tick OR the
        // step_ticks target -- after step_ticks(1500), the
        // last event we fired must be >= 1500 (when the
        // first instruction completes), not 0 or 32.
        assert!(
            chain.current_tick >= 1500,
            "current_tick should be >= boot offset 1500 (got {})",
            chain.current_tick
        );
    }

    /// `dsp_ping`-shaped chain test: the master core writes
    /// 0x68 to SSPBUF (after enabling the I²C peripheral).
    /// MSSP completes the TxByte after 9 SCL periods; the
    /// chain dispatcher routes the resulting `I2cBusEvent`
    /// to a coupled TAS3108 slave; the slave ACKs because
    /// 0x68 matches its write address; the chain overrides
    /// the master's SSPCON2.ACKSTAT bit to 0 (cleared).
    /// Without the slave coupling the master would see
    /// ACKSTAT=1 (NACK) -- the bus-less default.
    #[test]
    fn coupled_tas3108_acks_master_tx_byte_overrides_ackstat() {
        // Build a tiny flash: enable I²C master mode, set
        // SSPADD for a fast bit period, write 0x68 to
        // SSPBUF, then BRA -1 forever.  K20 is fine for
        // this -- we don't care about variant since SFR
        // semantics are identical.
        // SFR addresses: SSPCON1=0xFC6, SSPCON2=0xFC5,
        // SSPADD=0xFC8, SSPBUF=0xFC9.
        // Layout in flash[byte_addr]:
        //   0x00  MOVLW 0x28          (0E 28 at little-endian
        //                              => bytes [0x28, 0x0E])
        //   0x02  MOVWF SSPCON1       (0xC6 in low-FSR slot)
        //                              => MOVWF f,a syntax:
        //                              opcode=011011aa ffff_ffff
        //                              with a=0 access, f=0xC6
        //                              -> word=0x6EC6 -> bytes [0xC6, 0x6E]
        //   0x04  MOVLW 0x01
        //   0x06  MOVWF SSPADD (0xC8) -> word=0x6EC8 -> [0xC8, 0x6E]
        //   0x08  MOVLW 0x68
        //   0x0A  MOVWF SSPBUF (0xC9) -> word=0x6EC9 -> [0xC9, 0x6E]
        //   0x0C  BRA -1              -> 0xD7FF -> [0xFF, 0xD7]
        let mut flash = vec![0u8; 32 * 1024];
        let prog: &[(u32, [u8; 2])] = &[
            (0x0000, [0x28, 0x0E]),       // MOVLW 0x28 (SSPEN | SSPM=I2C master)
            (0x0002, [0xC6, 0x6E]),       // MOVWF SSPCON1
            (0x0004, [0x01, 0x0E]),       // MOVLW 0x01 (SSPADD: 2-Tcy bit period)
            (0x0006, [0xC8, 0x6E]),       // MOVWF SSPADD
            (0x0008, [0x68, 0x0E]),       // MOVLW 0x68 (TAS3108 write addr)
            (0x000A, [0xC9, 0x6E]),       // MOVWF SSPBUF
            (0x000C, [0xFF, 0xD7]),       // BRA -1 (loop forever)
        ];
        for (a, bytes) in prog {
            flash[*a as usize] = bytes[0];
            flash[*a as usize + 1] = bytes[1];
        }

        let mut chain = Chain::new();
        let mut master = Core::new(Variant::Pic18F25K20);
        master.flash_mut().copy_from_slice(&flash);
        let i_master = chain.push_core(master);
        let i_slave = chain.push_tas3108(crate::peripherals::tas3108::Tas3108::default());
        chain.couple_tas3108(i_master, i_slave);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0]);

        // Step long enough for: 6 setup instructions (~6 Tcy
        // = 96 ticks K20) + the 9-period TxByte (9 * 2 Tcy
        // = 18 Tcy = 288 ticks) + a few BRA loops.  500
        // ticks is plenty.
        chain.step_ticks(500);

        // The slave must have ACKed the byte 0x68 (its
        // address).
        assert!(
            chain.tas3108_slaves[i_slave].bytes_acked >= 1,
            "TAS3108 slave should have ACKed at least one byte (got acked={})",
            chain.tas3108_slaves[i_slave].bytes_acked,
        );

        // Master's SSPCON2.ACKSTAT (bit 6) must now be 0
        // (cleared by chain dispatch's `Mssp::override_acked`)
        // -- without the coupling the default
        // `complete_tx_byte` would have left it at 1.
        let con2 = chain.cores[i_master].memory.read_raw(
            crate::memory::Address::from_raw(0xFC5),
        );
        assert_eq!(
            con2 & (1 << 6),
            0,
            "ACKSTAT must be cleared by chain dispatch after slave ACK; SSPCON2=0x{:02X}",
            con2,
        );
    }

    /// Multi-byte chain transaction shaped after V3.1's
    /// `volume_dsp_write` (lst:7838).  V3.1 itself sends
    /// 4 data bytes after the subaddress; this test exercises
    /// the dispatch with a smaller 2-data-byte burst (the
    /// state-machine path is identical -- the slave sequential-
    /// write auto-increment fires once per data byte regardless
    /// of count).  Sequence: START + 0x68 + 0x30 + 0xDE +
    /// 0xAD + STOP.  Verifies the chain dispatch routes
    /// Start/Stop correctly, sequences multiple TxByte events
    /// through the slave's state machine, and the data lands
    /// at the right subaddresses.  Uses SSPCON2.SEN/PEN to
    /// fire Start/Stop through the actual MSSP state machine.
    #[test]
    fn coupled_tas3108_handles_volume_dsp_write_burst() {
        // Program:
        //   MOVLW 0x28; MOVWF SSPCON1     (enable I2C master)
        //   MOVLW 0x01; MOVWF SSPADD       (fast bit period)
        //   BSF SSPCON2, 0                 (SEN = start)
        //   <wait>: BTFSC SSPCON2, 0; BRA -2  (poll until Start completes)
        //   MOVLW 0x68; MOVWF SSPBUF       (write addr)
        //   <wait>: BTFSC SSPSTAT, 0; BRA -2  (poll BF clear)
        //   MOVLW 0x30; MOVWF SSPBUF       (subaddr)
        //   <wait>: BTFSC SSPSTAT, 0; BRA -2
        //   MOVLW 0xDE; MOVWF SSPBUF
        //   <wait>: BTFSC SSPSTAT, 0; BRA -2
        //   MOVLW 0xAD; MOVWF SSPBUF
        //   <wait>: BTFSC SSPSTAT, 0; BRA -2
        //   BSF SSPCON2, 2                 (PEN = stop)
        //   BRA -1                          (done -- self-loop idiom)
        //
        // BRA -2 (`0xD7FE`) targets `(PC + 2) + 2*(-2) =
        // PC - 2`, branching back to the immediately-prior
        // BTFSC.  BRA -1 (`0xD7FF`) self-loops at the BRA
        // itself (the standard "stay here forever" idiom).
        //
        // Encoding cheat-sheet:
        //   MOVLW k:        0x0Ekk -> [kk, 0x0E]
        //   MOVWF f, a=0:   0x6E__ where __ = f<7:0>
        //   BSF f, b, a=0:  0x80__ + (b<<9) where __ = f<7:0>
        //                   for SSPCON2 (0xC5):
        //                     bit0 (SEN): 0x80C5 -> [0xC5, 0x80]
        //                     bit2 (PEN): 0x84C5 -> [0xC5, 0x84]
        //   BTFSC f, b, a=0: 0xB0__ + (b<<9) where __ = f<7:0>
        //                    SSPCON2 bit0 (SEN poll): 0xB0C5 -> [0xC5, 0xB0]
        //                    SSPSTAT (0xC7) bit0 (BF poll): 0xB0C7 -> [0xC7, 0xB0]
        //   BRA -1:         0xD7FF -> [0xFF, 0xD7]
        let mut flash = vec![0u8; 32 * 1024];
        let prog: &[(u32, [u8; 2])] = &[
            (0x0000, [0x28, 0x0E]),       // MOVLW 0x28 (SSPEN | I2C master)
            (0x0002, [0xC6, 0x6E]),       // MOVWF SSPCON1
            (0x0004, [0x01, 0x0E]),       // MOVLW 0x01 (SSPADD)
            (0x0006, [0xC8, 0x6E]),       // MOVWF SSPADD
            (0x0008, [0xC5, 0x80]),       // BSF SSPCON2, 0 (SEN = start)
            (0x000A, [0xC5, 0xB0]),       // BTFSC SSPCON2, 0 (poll until SEN clears)
            (0x000C, [0xFE, 0xD7]),       // BRA -2 (back to BTFSC)
            (0x000E, [0x68, 0x0E]),       // MOVLW 0x68
            (0x0010, [0xC9, 0x6E]),       // MOVWF SSPBUF
            (0x0012, [0xC7, 0xB0]),       // BTFSC SSPSTAT, 0 (poll BF)
            (0x0014, [0xFE, 0xD7]),       // BRA -2 (back to BTFSC)
            (0x0016, [0x30, 0x0E]),       // MOVLW 0x30
            (0x0018, [0xC9, 0x6E]),       // MOVWF SSPBUF
            (0x001A, [0xC7, 0xB0]),
            (0x001C, [0xFE, 0xD7]),       // BRA -2
            (0x001E, [0xDE, 0x0E]),       // MOVLW 0xDE
            (0x0020, [0xC9, 0x6E]),       // MOVWF SSPBUF
            (0x0022, [0xC7, 0xB0]),
            (0x0024, [0xFE, 0xD7]),       // BRA -2
            (0x0026, [0xAD, 0x0E]),       // MOVLW 0xAD
            (0x0028, [0xC9, 0x6E]),       // MOVWF SSPBUF
            (0x002A, [0xC7, 0xB0]),
            (0x002C, [0xFE, 0xD7]),       // BRA -2
            (0x002E, [0xC5, 0x84]),       // BSF SSPCON2, 2 (PEN = stop)
            (0x0030, [0xFF, 0xD7]),       // BRA -1 (done)
        ];
        for (a, bytes) in prog {
            flash[*a as usize] = bytes[0];
            flash[*a as usize + 1] = bytes[1];
        }

        let mut chain = Chain::new();
        let mut master = Core::new(Variant::Pic18F25K20);
        master.flash_mut().copy_from_slice(&flash);
        let i_master = chain.push_core(master);
        let i_slave = chain.push_tas3108(crate::peripherals::tas3108::Tas3108::default());
        chain.couple_tas3108(i_master, i_slave);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0]);

        // Step long enough for: setup (~6 instr) + Start
        // (~2 SCL periods = 4 Tcy) + 4 TxBytes (each 9 SCL
        // periods = 18 Tcy) + Stop + a few BRA loops.
        // Generous budget.
        chain.step_ticks(20_000);

        // The slave must have ACKed exactly 4 bytes (addr +
        // subaddr + 2 data); no NACKs because address
        // matched and all data went through.
        assert_eq!(
            chain.tas3108_slaves[i_slave].bytes_acked, 4,
            "slave must ACK 4 bytes (addr + subaddr + 2 data); got acked={}",
            chain.tas3108_slaves[i_slave].bytes_acked,
        );
        assert_eq!(chain.tas3108_slaves[i_slave].bytes_nacked, 0);

        // Data bytes must land at subaddresses 0x30 and 0x31.
        assert_eq!(chain.tas3108_slaves[i_slave].read_subaddr(0x30), 0xDE);
        assert_eq!(chain.tas3108_slaves[i_slave].read_subaddr(0x31), 0xAD);
    }

    /// Two slaves coupled to one master, master addresses
    /// only one (slave A at 0x68); slave B (0x6A) must
    /// NACK and stay quiet for the rest of the transaction
    /// even when later data bytes match its address.
    /// Locks in the Phase::Ignored contract from codex
    /// review LOW #1.
    #[test]
    fn two_coupled_slaves_only_addressed_one_acks() {
        // Program: enable I2C master, START, write 0x68
        // (slave A's addr), write 0x6A (data byte equal to
        // slave B's addr), STOP.  Slave B must NOT
        // re-awaken on the 0x6A data byte.
        let mut flash = vec![0u8; 32 * 1024];
        let prog: &[(u32, [u8; 2])] = &[
            (0x0000, [0x28, 0x0E]),       // MOVLW 0x28
            (0x0002, [0xC6, 0x6E]),       // MOVWF SSPCON1
            (0x0004, [0x01, 0x0E]),
            (0x0006, [0xC8, 0x6E]),       // MOVWF SSPADD
            (0x0008, [0xC5, 0x80]),       // BSF SSPCON2, 0 (SEN)
            (0x000A, [0xC5, 0xB0]),       // BTFSC SSPCON2, 0
            (0x000C, [0xFE, 0xD7]),       // BRA -2 (back to BTFSC)
            (0x000E, [0x68, 0x0E]),       // MOVLW 0x68 (slave A)
            (0x0010, [0xC9, 0x6E]),       // MOVWF SSPBUF
            (0x0012, [0xC7, 0xB0]),       // BTFSC SSPSTAT, 0
            (0x0014, [0xFE, 0xD7]),       // BRA -2
            (0x0016, [0x6A, 0x0E]),       // MOVLW 0x6A (slave B's addr as data)
            (0x0018, [0xC9, 0x6E]),       // MOVWF SSPBUF
            (0x001A, [0xC7, 0xB0]),
            (0x001C, [0xFE, 0xD7]),       // BRA -2
            (0x001E, [0xC5, 0x84]),       // BSF SSPCON2, 2 (PEN)
            (0x0020, [0xFF, 0xD7]),       // BRA -1 (done)
        ];
        for (a, bytes) in prog {
            flash[*a as usize] = bytes[0];
            flash[*a as usize + 1] = bytes[1];
        }

        let mut chain = Chain::new();
        let mut master = Core::new(Variant::Pic18F25K20);
        master.flash_mut().copy_from_slice(&flash);
        let i_master = chain.push_core(master);
        let i_a = chain.push_tas3108(crate::peripherals::tas3108::Tas3108::new(false)); // 0x68
        let i_b = chain.push_tas3108(crate::peripherals::tas3108::Tas3108::new(true));  // 0x6A
        chain.couple_tas3108(i_master, i_a);
        chain.couple_tas3108(i_master, i_b);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0]);
        chain.step_ticks(20_000);

        // Slave A (0x68): ACKed address byte AND the 0x6A
        // data byte (per its sequential-write semantics).
        // bytes_acked = 2.  bytes_nacked = 0.
        assert_eq!(chain.tas3108_slaves[i_a].bytes_acked, 2);
        assert_eq!(chain.tas3108_slaves[i_a].bytes_nacked, 0);

        // Slave B (0x6A): NACKed 0x68 (not its address);
        // then received 0x6A as a payload byte, but Phase::Ignored
        // means it stays quiet -- bytes_nacked counts the
        // NACK on 0x68 + the dropped 0x6A payload byte.
        // bytes_acked = 0.
        assert_eq!(
            chain.tas3108_slaves[i_b].bytes_acked, 0,
            "slave B must NOT ACK any byte in this transaction; got acked={}",
            chain.tas3108_slaves[i_b].bytes_acked,
        );
        assert!(chain.tas3108_slaves[i_b].bytes_nacked >= 1);
    }

    /// Without a coupled TAS3108, the master's ACKSTAT
    /// stays at 1 (NACK -- bus-less default).  Locks in
    /// the contract that the override is a chain-dispatch
    /// effect, not an MSSP-side default.
    #[test]
    fn uncoupled_master_tx_byte_keeps_default_nack() {
        let mut flash = vec![0u8; 32 * 1024];
        // Same setup-and-TX program as the coupled test;
        // no slave wired to the chain.
        let prog: &[(u32, [u8; 2])] = &[
            (0x0000, [0x28, 0x0E]),
            (0x0002, [0xC6, 0x6E]),
            (0x0004, [0x01, 0x0E]),
            (0x0006, [0xC8, 0x6E]),
            (0x0008, [0x68, 0x0E]),
            (0x000A, [0xC9, 0x6E]),
            (0x000C, [0xFF, 0xD7]),
        ];
        for (a, bytes) in prog {
            flash[*a as usize] = bytes[0];
            flash[*a as usize + 1] = bytes[1];
        }
        let mut chain = Chain::new();
        let mut master = Core::new(Variant::Pic18F25K20);
        master.flash_mut().copy_from_slice(&flash);
        let i_master = chain.push_core(master);
        chain.apply_reset_all(ResetSource::PowerOn);
        chain.schedule_initial_steps(&[0]);
        chain.step_ticks(500);

        let con2 = chain.cores[i_master].memory.read_raw(
            crate::memory::Address::from_raw(0xFC5),
        );
        assert_eq!(
            con2 & (1 << 6),
            1 << 6,
            "uncoupled master must see ACKSTAT=1 (NACK); SSPCON2=0x{:02X}",
            con2,
        );
    }
}
