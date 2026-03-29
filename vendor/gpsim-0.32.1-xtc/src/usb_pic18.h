/*
 * usb_pic18.h — Minimal PIC18 USB SIE simulation for HID testing.
 *
 * Token-driven model: the host/test side issues commands (BUS_RESET,
 * EP0_SETUP, EP_OUT, EP_IN, etc.) that manipulate BDTs in Bank 4 RAM,
 * set USTAT, fire TRNIF, and let the firmware's USB ISR handle the rest.
 *
 * No wire-level D+/D- signaling, no SOF, no error recovery.
 */

#ifndef USB_PIC18_H
#define USB_PIC18_H

#include <cstdint>
#include <deque>

#include "value.h"
#include "gpsim_classes.h"
#include "registers.h"

class Processor;
class PIR;
class sfr_register;

/* Buffer Descriptor (BD) — 4 bytes in Bank 4 RAM */
struct UsbBd
{
    uint8_t stat;   /* BDnSTAT: UOWN, DTS, DTSEN, BSTALL + PID/BC */
    uint8_t cnt;    /* BDnCNT: byte count */
    uint8_t adrl;   /* BDnADRL: buffer address low */
    uint8_t adrh;   /* BDnADRH: buffer address high */

    uint16_t addr() const { return adrl | (static_cast<uint16_t>(adrh) << 8); }
    bool uown() const { return (stat & 0x80) != 0; }
};

/* Host command opcodes (written to usb_host_cmd attribute) */
enum UsbHostCmd
{
    USB_NOP             = 0,
    USB_BUS_RESET       = 1,
    USB_EP0_SETUP       = 2,
    USB_EP0_IN          = 3,
    USB_EP0_OUT_STATUS  = 4,
    USB_EP_OUT          = 5,
    USB_EP_IN           = 6,
};

/* SFR bit definitions */
namespace UsbBits
{
    /* UCON */
    constexpr uint8_t USBEN   = 1 << 0;
    constexpr uint8_t PPBRST  = 1 << 1;
    constexpr uint8_t RESUME  = 1 << 2;
    constexpr uint8_t PKTDIS  = 1 << 3;
    constexpr uint8_t SE0     = 1 << 4;

    /* UIR */
    constexpr uint8_t URSTIF  = 1 << 0;
    constexpr uint8_t UERRIF  = 1 << 1;
    constexpr uint8_t ACTVIF  = 1 << 2;
    constexpr uint8_t TRNIF   = 1 << 3;
    constexpr uint8_t IDLEIF  = 1 << 4;
    constexpr uint8_t STALLIF = 1 << 5;
    constexpr uint8_t SOFIF   = 1 << 6;

    /* UCFG */
    constexpr uint8_t PPB0    = 1 << 0;
    constexpr uint8_t PPB1    = 1 << 1;
    constexpr uint8_t FSEN    = 1 << 2;
    constexpr uint8_t UTRDIS  = 1 << 3;
    constexpr uint8_t UPUEN   = 1 << 4;

    /* UEPn */
    constexpr uint8_t EPHSHK  = 1 << 0;
    constexpr uint8_t EPSTALL = 1 << 1;
    constexpr uint8_t EPOUTEN = 1 << 2;
    constexpr uint8_t EPINEN  = 1 << 3;
    constexpr uint8_t EPCONDIS = 1 << 4;

    /* BDnSTAT (SIE mode) */
    constexpr uint8_t BD_UOWN   = 0x80;
    constexpr uint8_t BD_DTS    = 0x40;
    constexpr uint8_t BD_DTSEN  = 0x08;
    constexpr uint8_t BD_BSTALL = 0x04;
}

/*
 * PIC18USB — token-driven USB SIE model.
 *
 * Owns no SFR storage; hooks into the existing sfr_register members
 * in the P18F2455 class for reads/writes.
 */
class PIC18USB
{
public:
    PIC18USB(Processor *cpu, PIR *pir2 = nullptr);
    ~PIC18USB();

    void set_pir2(PIR *p) { m_pir2 = p; }

    /* Called from custom SFR put() methods */
    void on_ucon_write(uint8_t old_val, uint8_t new_val);
    void on_uir_write(uint8_t new_val);

    /* Host command interface (called from attribute write) */
    void host_command(unsigned cmd);

    /* Register host-command attributes with the processor symbol table */
    void register_host_symbols();
    void remove_host_symbols();

    /* USTAT read: returns front of FIFO */
    uint8_t ustat_read() const;

private:
    Processor  *m_cpu;
    PIR        *m_pir2;

    /* USTAT FIFO (max 4 entries on PIC18) */
    std::deque<uint8_t> m_ustat_fifo;

    /* Ping-pong even/odd tracking per endpoint (only EP0 toggles in DLCP) */
    bool m_ep0_out_even = true;

    /* Host command attributes */
    Integer *m_host_cmd_attr   = nullptr;
    Integer *m_host_ep_attr    = nullptr;
    Integer *m_host_len_attr   = nullptr;
    Integer *m_host_result_attr = nullptr;
    Integer *m_trn_count_attr  = nullptr;

    /* Bank 4 RAM helpers */
    UsbBd read_bd(unsigned bd_index) const;
    void write_bd(unsigned bd_index, const UsbBd &bd);
    uint8_t read_usb_ram(uint16_t addr) const;
    void write_usb_ram(uint16_t addr, uint8_t val);

    /* SFR access helpers */
    uint8_t read_sfr(unsigned addr) const;
    void write_sfr(unsigned addr, uint8_t val);
    void set_sfr_bit(unsigned addr, uint8_t mask);
    void clear_sfr_bit(unsigned addr, uint8_t mask);

    /* BD index calculation: UCFG.PPB mode 01 mapping */
    unsigned bd_index_for_ep(unsigned ep, bool is_in) const;

    /* Token completion helpers */
    void complete_token(unsigned bd_idx, uint8_t pid, uint8_t count, uint8_t ustat_val);
    void push_ustat(uint8_t ustat_val);
    void fire_trnif();

    /* Host operations */
    void do_bus_reset();
    void do_ep0_setup();
    void do_ep0_in();
    void do_ep0_out_status();
    void do_ep_out(unsigned ep, unsigned len);
    void do_ep_in(unsigned ep);
};

/* Custom UCON register that notifies PIC18USB on writes */
class UCON_REG : public sfr_register
{
public:
    UCON_REG(Processor *cpu, const char *name, const char *desc, PIC18USB *usb);
    void put(unsigned int new_value) override;

private:
    PIC18USB *m_usb;
};

/* Custom UIR register that notifies PIC18USB on writes (TRNIF clear) */
class UIR_REG : public sfr_register
{
public:
    UIR_REG(Processor *cpu, const char *name, const char *desc, PIC18USB *usb);
    void put(unsigned int new_value) override;

private:
    PIC18USB *m_usb;
};

/* Custom USTAT register that reads from the FIFO */
class USTAT_REG : public sfr_register
{
public:
    USTAT_REG(Processor *cpu, const char *name, const char *desc, PIC18USB *usb);
    unsigned int get() override;

private:
    PIC18USB *m_usb;
};

#endif /* USB_PIC18_H */
