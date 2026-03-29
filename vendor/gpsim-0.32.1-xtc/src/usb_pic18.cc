/*
 * usb_pic18.cc — Minimal PIC18 USB SIE simulation for HID testing.
 */

#include <glib.h>
#include "usb_pic18.h"
#include "processor.h"
#include "pir.h"
#include "trace.h"

#include <iostream>
#include <cstring>

/* SFR absolute addresses for PIC18F2455/2550 */
static constexpr unsigned SFR_UCON  = 0x0F6D;
static constexpr unsigned SFR_UIR   = 0x0F68;
static constexpr unsigned SFR_UIE   = 0x0F69;
static constexpr unsigned SFR_USTAT = 0x0F6C;
static constexpr unsigned SFR_UADDR = 0x0F6E;
static constexpr unsigned SFR_UCFG  = 0x0F6F;
static constexpr unsigned SFR_UEP0  = 0x0F70;

/* BDT base in Bank 4 RAM */
static constexpr unsigned BDT_BASE  = 0x0400;
static constexpr unsigned BD_SIZE   = 4;

/* -----------------------------------------------------------
 * PIC18USB core
 * ----------------------------------------------------------- */

PIC18USB::PIC18USB(Processor *cpu, PIR *pir2)
    : m_cpu(cpu), m_pir2(pir2)
{
}

PIC18USB::~PIC18USB()
{
    remove_host_symbols();
}

/* --- Bank 4 RAM access --- */

uint8_t PIC18USB::read_usb_ram(uint16_t addr) const
{
    if (!m_cpu) return 0;
    return m_cpu->registers[addr]->get_value() & 0xFF;
}

void PIC18USB::write_usb_ram(uint16_t addr, uint8_t val)
{
    if (!m_cpu) return;
    m_cpu->registers[addr]->put_value(val);
}

UsbBd PIC18USB::read_bd(unsigned bd_index) const
{
    unsigned base = BDT_BASE + bd_index * BD_SIZE;
    UsbBd bd;
    bd.stat = read_usb_ram(base);
    bd.cnt  = read_usb_ram(base + 1);
    bd.adrl = read_usb_ram(base + 2);
    bd.adrh = read_usb_ram(base + 3);
    return bd;
}

void PIC18USB::write_bd(unsigned bd_index, const UsbBd &bd)
{
    unsigned base = BDT_BASE + bd_index * BD_SIZE;
    write_usb_ram(base,     bd.stat);
    write_usb_ram(base + 1, bd.cnt);
    write_usb_ram(base + 2, bd.adrl);
    write_usb_ram(base + 3, bd.adrh);
}

/* --- SFR helpers --- */

uint8_t PIC18USB::read_sfr(unsigned addr) const
{
    if (!m_cpu) return 0;
    return m_cpu->registers[addr]->get_value() & 0xFF;
}

void PIC18USB::write_sfr(unsigned addr, uint8_t val)
{
    if (!m_cpu) return;
    /* Use put_value() for internal writes — bypasses custom put() logic
     * like UIR's write-1-to-clear.  This is the SIE writing to the
     * register, not the firmware. */
    m_cpu->registers[addr]->put_value(val);
}

void PIC18USB::set_sfr_bit(unsigned addr, uint8_t mask)
{
    /* Read current value, OR in the bits, write back via put_value() */
    uint8_t cur = read_sfr(addr);
    m_cpu->registers[addr]->put_value(cur | mask);
}

void PIC18USB::clear_sfr_bit(unsigned addr, uint8_t mask)
{
    uint8_t cur = read_sfr(addr);
    m_cpu->registers[addr]->put_value(cur & ~mask);
}

/* --- BD index mapping for UCFG.PPB mode 01 ---
 * Mode 01 (ping-pong on EP0 OUT only):
 *   BD0 = EP0 OUT even
 *   BD1 = EP0 OUT odd
 *   BD2 = EP0 IN
 *   BD3 = EP1 OUT
 *   BD4 = EP1 IN
 *   BD5 = EP2 OUT ... etc.
 *
 * For EPn>0: BD index = 3 + (ep-1)*2 + (is_in ? 1 : 0)
 */
unsigned PIC18USB::bd_index_for_ep(unsigned ep, bool is_in) const
{
    if (ep == 0)
    {
        if (is_in)
            return 2;  /* EP0 IN */
        /* EP0 OUT: ping-pong */
        return m_ep0_out_even ? 0 : 1;
    }
    return 3 + (ep - 1) * 2 + (is_in ? 1 : 0);
}

/* --- USTAT FIFO --- */

void PIC18USB::push_ustat(uint8_t ustat_val)
{
    m_ustat_fifo.push_back(ustat_val);
}

uint8_t PIC18USB::ustat_read() const
{
    if (m_ustat_fifo.empty())
        return 0;
    return m_ustat_fifo.front();
}

void PIC18USB::fire_trnif()
{
    set_sfr_bit(SFR_UIR, UsbBits::TRNIF);

    /* If UIE.TRNIE is set, fire PIR2.USBIF */
    uint8_t uie = read_sfr(SFR_UIE);
    if (uie & UsbBits::TRNIF)
    {
        if (m_pir2)
            m_pir2->set_usbif();
    }
}

/* --- Token completion --- */

void PIC18USB::complete_token(unsigned bd_idx, uint8_t pid, uint8_t count, uint8_t ustat_val)
{
    UsbBd bd = read_bd(bd_idx);
    /* Clear UOWN (give back to CPU), set PID bits in stat[5:2] */
    bd.stat = (bd.stat & 0xC3) | ((pid & 0x0F) << 2);
    bd.stat &= ~UsbBits::BD_UOWN;  /* CPU owns it now */
    bd.cnt = count;
    write_bd(bd_idx, bd);

    push_ustat(ustat_val);
    fire_trnif();

    /* Increment transaction counter */
    if (m_trn_count_attr)
    {
        gint64 c = 0;
        m_trn_count_attr->get(c);
        m_trn_count_attr->set(static_cast<gint64>(c + 1));
    }
}

/* --- Host operations --- */

void PIC18USB::do_bus_reset()
{
    /* Clear UADDR */
    write_sfr(SFR_UADDR, 0);

    /* Reset ping-pong to even */
    m_ep0_out_even = true;

    /* Flush USTAT FIFO */
    m_ustat_fifo.clear();

    /* Set URSTIF */
    set_sfr_bit(SFR_UIR, UsbBits::URSTIF);

    /* Fire interrupt if enabled */
    uint8_t uie = read_sfr(SFR_UIE);
    if (uie & UsbBits::URSTIF)
    {
        if (m_pir2)
            m_pir2->set_usbif();
    }

    if (m_host_result_attr)
        m_host_result_attr->set(static_cast<gint64>(0));
}

void PIC18USB::do_ep0_setup()
{
    unsigned bd_idx = bd_index_for_ep(0, false);
    UsbBd bd = read_bd(bd_idx);

    if (!bd.uown())
    {
        /* EP0 OUT not armed by firmware */
        if (m_host_result_attr)
            m_host_result_attr->set(static_cast<gint64>(-1));
        return;
    }

    /* SETUP token uses PID=0x0D (SETUP) */
    /* USTAT for EP0 OUT: EP=0, DIR=0, PPBI depends on ping-pong */
    uint8_t ustat_val = (m_ep0_out_even ? 0x00 : 0x04);

    /* 8-byte SETUP packet is already in the BD buffer (host wrote it) */
    complete_token(bd_idx, 0x0D, 8, ustat_val);

    /* Toggle ping-pong for EP0 OUT */
    m_ep0_out_even = !m_ep0_out_even;

    /* Clear PKTDIS (SIE automatically sets it on SETUP) */
    /* Actually, the SIE sets PKTDIS; the firmware clears it after processing */
    set_sfr_bit(SFR_UCON, UsbBits::PKTDIS);

    if (m_host_result_attr)
        m_host_result_attr->set(static_cast<gint64>(0));
}

void PIC18USB::do_ep0_in()
{
    unsigned bd_idx = bd_index_for_ep(0, true);
    UsbBd bd = read_bd(bd_idx);

    if (!bd.uown())
    {
        if (m_host_result_attr)
            m_host_result_attr->set(static_cast<gint64>(-1));
        return;
    }

    /* IN token: SIE sends data from buffer, host reads it */
    /* USTAT for EP0 IN: EP=0, DIR=1 (IN), PPBI=0 */
    uint8_t ustat_val = 0x04;  /* bit 2 = DIR (IN) ... actually: */
    /* USTAT format: [EP3:EP0][DIR][PPBI][0][0] */
    /* EP0 IN: EP=0000, DIR=1, PPBI=0 → 0x04 */
    ustat_val = 0x04;

    complete_token(bd_idx, 0x09, bd.cnt, ustat_val);

    if (m_host_result_attr)
        m_host_result_attr->set(static_cast<gint64>(0));
}

void PIC18USB::do_ep0_out_status()
{
    unsigned bd_idx = bd_index_for_ep(0, false);
    UsbBd bd = read_bd(bd_idx);

    if (!bd.uown())
    {
        if (m_host_result_attr)
            m_host_result_attr->set(static_cast<gint64>(-1));
        return;
    }

    /* Status stage OUT (zero-length) */
    uint8_t ustat_val = (m_ep0_out_even ? 0x00 : 0x04);
    complete_token(bd_idx, 0x01, 0, ustat_val);
    m_ep0_out_even = !m_ep0_out_even;

    if (m_host_result_attr)
        m_host_result_attr->set(static_cast<gint64>(0));
}

void PIC18USB::do_ep_out(unsigned ep, unsigned len)
{
    if (ep == 0)
    {
        do_ep0_setup();
        return;
    }

    unsigned bd_idx = bd_index_for_ep(ep, false);
    UsbBd bd = read_bd(bd_idx);

    if (!bd.uown())
    {
        if (m_host_result_attr)
            m_host_result_attr->set(static_cast<gint64>(-1));
        return;
    }

    /* USTAT: EP in [6:3], DIR=0 (OUT), PPBI=0 → (ep << 3) */
    uint8_t ustat_val = static_cast<uint8_t>((ep & 0x0F) << 3);
    complete_token(bd_idx, 0x01, static_cast<uint8_t>(len & 0xFF), ustat_val);

    if (m_host_result_attr)
        m_host_result_attr->set(static_cast<gint64>(0));
}

void PIC18USB::do_ep_in(unsigned ep)
{
    if (ep == 0)
    {
        do_ep0_in();
        return;
    }

    unsigned bd_idx = bd_index_for_ep(ep, true);
    UsbBd bd = read_bd(bd_idx);

    if (!bd.uown())
    {
        if (m_host_result_attr)
            m_host_result_attr->set(static_cast<gint64>(-1));
        return;
    }

    /* USTAT: EP in [6:3], DIR=1 (IN), PPBI=0 → (ep << 3) | 0x04 */
    uint8_t ustat_val = static_cast<uint8_t>(((ep & 0x0F) << 3) | 0x04);
    complete_token(bd_idx, 0x09, bd.cnt, ustat_val);

    if (m_host_result_attr)
        m_host_result_attr->set(static_cast<gint64>(0));
}

/* --- SFR callbacks --- */

void PIC18USB::on_ucon_write(uint8_t old_val, uint8_t new_val)
{
    /* PPBRST: reset ping-pong pointers */
    if ((new_val & UsbBits::PPBRST) && !(old_val & UsbBits::PPBRST))
    {
        m_ep0_out_even = true;
    }
}

void PIC18USB::on_uir_write(uint8_t new_val)
{
    /* UIR is a "write-1-to-clear" register on PIC18 */
    uint8_t old_val = read_sfr(SFR_UIR);
    uint8_t cleared = old_val & ~new_val;

    /* If TRNIF was cleared, pop the USTAT FIFO */
    if ((old_val & UsbBits::TRNIF) && !(new_val & UsbBits::TRNIF))
    {
        if (!m_ustat_fifo.empty())
            m_ustat_fifo.pop_front();

        /* If more entries in FIFO, reassert TRNIF immediately */
        if (!m_ustat_fifo.empty())
        {
            cleared |= UsbBits::TRNIF;  /* keep TRNIF set */
        }
    }

    /* Write back the cleared value */
    write_sfr(SFR_UIR, cleared);
}

/* --- Host command dispatch --- */

void PIC18USB::host_command(unsigned cmd)
{
    gint64 ep = 0, len = 0;
    if (m_host_ep_attr) m_host_ep_attr->get(ep);
    if (m_host_len_attr) m_host_len_attr->get(len);

    switch (static_cast<UsbHostCmd>(cmd))
    {
    case USB_NOP:
        break;
    case USB_BUS_RESET:
        do_bus_reset();
        break;
    case USB_EP0_SETUP:
        do_ep0_setup();
        break;
    case USB_EP0_IN:
        do_ep0_in();
        break;
    case USB_EP0_OUT_STATUS:
        do_ep0_out_status();
        break;
    case USB_EP_OUT:
        do_ep_out(static_cast<unsigned>(ep), static_cast<unsigned>(len));
        break;
    case USB_EP_IN:
        do_ep_in(static_cast<unsigned>(ep));
        break;
    default:
        std::cerr << "PIC18USB: unknown host command " << cmd << std::endl;
        if (m_host_result_attr)
            m_host_result_attr->set(static_cast<gint64>(-2));
        break;
    }

    /* Reset command to NOP */
    if (m_host_cmd_attr)
        m_host_cmd_attr->set(static_cast<gint64>(0));
}

/* --- Triggered attribute: calls host_command() on write --- */

class UsbHostCmdAttr : public Integer
{
public:
    UsbHostCmdAttr(PIC18USB *usb)
        : Integer("usb_host_cmd", 0, "USB host command trigger"), m_usb(usb) {}

    void set(gint64 v) override
    {
        Integer::set(v);
        if (v != 0 && m_usb)
            m_usb->host_command(static_cast<unsigned>(v));
    }
private:
    PIC18USB *m_usb;
};


/* --- Symbol registration --- */

void PIC18USB::register_host_symbols()
{
    if (!m_cpu || m_host_cmd_attr) return;

    m_host_cmd_attr = new UsbHostCmdAttr(this);
    m_host_ep_attr = new Integer("usb_host_ep", 0, "USB host target endpoint");
    m_host_len_attr = new Integer("usb_host_len", 0, "USB host payload length");
    m_host_result_attr = new Integer("usb_host_result", 0, "USB host last result");
    m_trn_count_attr = new Integer("usb_trn_count", 0, "USB transaction count");

    m_cpu->addSymbol(m_host_cmd_attr);
    m_cpu->addSymbol(m_host_ep_attr);
    m_cpu->addSymbol(m_host_len_attr);
    m_cpu->addSymbol(m_host_result_attr);
    m_cpu->addSymbol(m_trn_count_attr);
}

void PIC18USB::remove_host_symbols()
{
    if (!m_cpu) return;

    auto remove = [&](Integer *&attr)
    {
        if (attr)
        {
            m_cpu->removeSymbol(attr);
            delete attr;
            attr = nullptr;
        }
    };

    remove(m_host_cmd_attr);
    remove(m_host_ep_attr);
    remove(m_host_len_attr);
    remove(m_host_result_attr);
    remove(m_trn_count_attr);
}

/* -----------------------------------------------------------
 * Custom SFR register classes
 * ----------------------------------------------------------- */

UCON_REG::UCON_REG(Processor *cpu, const char *name, const char *desc, PIC18USB *usb)
    : sfr_register(cpu, name, desc), m_usb(usb)
{
}

void UCON_REG::put(unsigned int new_value)
{
    uint8_t old = value.get() & 0xFF;
    trace.raw(write_trace.get() | value.get());
    value.put(new_value & 0xFF);
    if (m_usb)
        m_usb->on_ucon_write(old, new_value & 0xFF);
}

UIR_REG::UIR_REG(Processor *cpu, const char *name, const char *desc, PIC18USB *usb)
    : sfr_register(cpu, name, desc), m_usb(usb)
{
}

void UIR_REG::put(unsigned int new_value)
{
    trace.raw(write_trace.get() | value.get());
    /* UIR is write-1-to-clear: delegate to USB module */
    if (m_usb)
        m_usb->on_uir_write(new_value & 0xFF);
    else
        value.put(value.get() & ~(new_value & 0xFF));
}

USTAT_REG::USTAT_REG(Processor *cpu, const char *name, const char *desc, PIC18USB *usb)
    : sfr_register(cpu, name, desc), m_usb(usb)
{
}

unsigned int USTAT_REG::get()
{
    if (m_usb)
        return m_usb->ustat_read();
    return value.get();
}

unsigned int USTAT_REG::get_value()
{
    /* movff uses get_value(), so we must also return the FIFO value here */
    if (m_usb)
        return m_usb->ustat_read();
    return value.get();
}
