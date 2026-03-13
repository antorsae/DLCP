/*
   Copyright (C) 2026

This file is part of gpsim.

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.
*/

#include <cstdio>

#include "../config.h"

#include "../src/gpsim_time.h"
#include "../src/packages.h"
#include "../src/registers.h"
#include "../src/stimuli.h"
#include "../src/symbol.h"
#include "../src/value.h"
#include "i2c-regfile.h"

static const guint64 kPersistentSclHoldCycles = 0x100000000ULL;


class I2CRegFileAddressAttribute : public Integer {
public:
  explicit I2CRegFileAddressAttribute(I2CRegFile_Modules::I2CRegFile *regfile)
    : Integer("Slave_Address", 0x34, "I2C 7-bit slave address"), m_regfile(regfile)
  {
    gint64 v;
    Integer::get(v);
    set(v);
  }

  void set(gint64 v) override
  {
    const unsigned int address = static_cast<unsigned int>(v) & 0x7f;
    Integer::set(static_cast<gint64>(address));
    if (m_regfile) {
      m_regfile->i2c_slave_address = (address << 1);
    }
  }

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


class I2CRegFileAddressNackCountAttribute : public Integer {
public:
  explicit I2CRegFileAddressNackCountAttribute(I2CRegFile_Modules::I2CRegFile *regfile)
    : Integer("Address_Nack_Count", 0, "Number of address phases to NACK before resuming ACK"),
      m_regfile(regfile)
  {
  }

  void set(gint64 v) override;

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


class I2CRegFileAddressStretchSCLCyclesAttribute : public Integer {
public:
  explicit I2CRegFileAddressStretchSCLCyclesAttribute(I2CRegFile_Modules::I2CRegFile *regfile)
    : Integer("Address_Stretch_SCL_Cycles", 0, "Hold SCL low for N cycles after each address match"),
      m_regfile(regfile)
  {
  }

  void set(gint64 v) override;

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


class I2CRegFileDataNackCountAttribute : public Integer {
public:
  explicit I2CRegFileDataNackCountAttribute(I2CRegFile_Modules::I2CRegFile *regfile)
    : Integer("Data_Nack_Count", 0, "Number of data-phase bytes to NACK before resuming ACK"),
      m_regfile(regfile)
  {
  }

  void set(gint64 v) override;

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


class I2CRegFileDataStuckSdaCyclesAttribute : public Integer {
public:
  explicit I2CRegFileDataStuckSdaCyclesAttribute(I2CRegFile_Modules::I2CRegFile *regfile)
    : Integer("Data_Stuck_SDA_Cycles", 0, "Hold SDA low for N cycles after each data-phase byte"),
      m_regfile(regfile)
  {
  }

  void set(gint64 v) override;

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


class I2CRegFileHoldSCLLowAttribute : public Integer {
public:
  explicit I2CRegFileHoldSCLLowAttribute(I2CRegFile_Modules::I2CRegFile *regfile)
    : Integer("Hold_SCL_Low", 0, "Hold SCL low until cleared (stuck-bus fault)"),
      m_regfile(regfile)
  {
  }

  void set(gint64 v) override;

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


class I2CRegFileStretchSCLCyclesAttribute : public Integer {
public:
  explicit I2CRegFileStretchSCLCyclesAttribute(I2CRegFile_Modules::I2CRegFile *regfile)
    : Integer("Stretch_SCL_Cycles", 0, "Hold SCL low for the requested number of cycles, then release"),
      m_regfile(regfile)
  {
  }

  void set(gint64 v) override;

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


class I2CRegFileSclApplyTrigger : public TriggerObject {
public:
  explicit I2CRegFileSclApplyTrigger(I2CRegFile_Modules::I2CRegFile *regfile)
    : m_regfile(regfile)
  {
  }

  void callback() override;

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


class I2CRegFileStretchReleaseTrigger : public TriggerObject {
public:
  explicit I2CRegFileStretchReleaseTrigger(I2CRegFile_Modules::I2CRegFile *regfile)
    : m_regfile(regfile)
  {
  }

  void callback() override;

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


class I2CRegFileSdaApplyTrigger : public TriggerObject {
public:
  explicit I2CRegFileSdaApplyTrigger(I2CRegFile_Modules::I2CRegFile *regfile)
    : m_regfile(regfile)
  {
  }

  void callback() override;

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


class I2CRegFileSdaReleaseTrigger : public TriggerObject {
public:
  explicit I2CRegFileSdaReleaseTrigger(I2CRegFile_Modules::I2CRegFile *regfile)
    : m_regfile(regfile)
  {
  }

  void callback() override;

private:
  I2CRegFile_Modules::I2CRegFile *m_regfile;
};


namespace I2CRegFile_Modules {

I2CRegFile::I2CRegFile(const char *_name)
  : i2c_slave(),
    Module(_name, "i2c_regfile"),
    m_registers(new Register *[kRegisterCount]),
    m_slave_address_attr(new I2CRegFileAddressAttribute(this)),
    m_address_nack_count_attr(new I2CRegFileAddressNackCountAttribute(this)),
    m_address_stretch_scl_cycles_attr(new I2CRegFileAddressStretchSCLCyclesAttribute(this)),
    m_data_nack_count_attr(new I2CRegFileDataNackCountAttribute(this)),
    m_data_stuck_sda_cycles_attr(new I2CRegFileDataStuckSdaCyclesAttribute(this)),
    m_hold_scl_low_attr(new I2CRegFileHoldSCLLowAttribute(this)),
    m_stretch_scl_cycles_attr(new I2CRegFileStretchSCLCyclesAttribute(this)),
    m_reg_addr(0),
    m_address_nack_count(0),
    m_address_stretch_scl_cycles(0),
    m_data_nack_count(0),
    m_data_stuck_sda_cycles(0),
    m_hold_scl_low(false),
    m_timed_scl_hold_active(false),
    m_requested_sda_release(true),
    m_timed_sda_hold_active(false),
    m_timed_scl_release_cycle(0),
    m_timed_sda_release_cycle(0),
    m_scl_apply_trigger(new I2CRegFileSclApplyTrigger(this)),
    m_stretch_release_trigger(new I2CRegFileStretchReleaseTrigger(this)),
    m_sda_apply_trigger(new I2CRegFileSdaApplyTrigger(this)),
    m_sda_release_trigger(new I2CRegFileSdaReleaseTrigger(this)),
    io_state(RX_REG_ADDR)
{
  char reg_name[16];
  for (unsigned int i = 0; i < kRegisterCount; ++i) {
    snprintf(reg_name, sizeof(reg_name), "reg%02x", i);
    m_registers[i] = new Register(this, reg_name, "I2C register-file byte");
    m_registers[i]->address = i;
    m_registers[i]->value.put(0);
    addSymbol(m_registers[i]);
  }
  addSymbol(m_slave_address_attr);
  addSymbol(m_address_nack_count_attr);
  addSymbol(m_address_stretch_scl_cycles_attr);
  addSymbol(m_data_nack_count_attr);
  addSymbol(m_data_stuck_sda_cycles_attr);
  addSymbol(m_hold_scl_low_attr);
  addSymbol(m_stretch_scl_cycles_attr);
}


I2CRegFile::~I2CRegFile()
{
  get_cycles().clear_break(m_scl_apply_trigger);
  get_cycles().clear_break(m_stretch_release_trigger);
  get_cycles().clear_break(m_sda_apply_trigger);
  get_cycles().clear_break(m_sda_release_trigger);
  for (unsigned int i = 0; i < kRegisterCount; ++i) {
    removeSymbol(m_registers[i]);
    delete m_registers[i];
  }
  delete [] m_registers;

  removeSymbol(m_slave_address_attr);
  delete m_slave_address_attr;
  removeSymbol(m_address_nack_count_attr);
  delete m_address_nack_count_attr;
  removeSymbol(m_address_stretch_scl_cycles_attr);
  delete m_address_stretch_scl_cycles_attr;
  removeSymbol(m_data_nack_count_attr);
  delete m_data_nack_count_attr;
  removeSymbol(m_data_stuck_sda_cycles_attr);
  delete m_data_stuck_sda_cycles_attr;
  removeSymbol(m_hold_scl_low_attr);
  delete m_hold_scl_low_attr;
  removeSymbol(m_stretch_scl_cycles_attr);
  delete m_stretch_scl_cycles_attr;
  delete m_scl_apply_trigger;
  delete m_stretch_release_trigger;
  delete m_sda_apply_trigger;
  delete m_sda_release_trigger;

  removeSymbol((IOPIN *)scl);
  removeSymbol((IOPIN *)sda);
  sda = nullptr;
  scl = nullptr;
}


bool I2CRegFile::receive_data_byte(unsigned int data)
{
  if (m_data_stuck_sda_cycles != 0) {
    start_timed_sda_hold(m_data_stuck_sda_cycles);
  }

  if (m_data_nack_count != 0) {
    m_data_nack_count--;
    m_data_nack_count_attr->Integer::set(static_cast<gint64>(m_data_nack_count));
    return false;
  }

  put_data(data);
  return true;
}


void I2CRegFile::put_data(unsigned int data)
{
  switch (io_state) {
  case RX_REG_ADDR:
    m_reg_addr = data & 0xff;
    io_state = RX_REG_DATA;
    break;

  case RX_REG_DATA:
    m_registers[m_reg_addr]->put(data & 0xff);
    m_reg_addr = (m_reg_addr + 1) & 0xff;
    break;

  case TX_REG_DATA:
    break;
  }
}


unsigned int I2CRegFile::get_data()
{
  const unsigned int data = m_registers[m_reg_addr]->get();
  m_reg_addr = (m_reg_addr + 1) & 0xff;
  return data;
}


void I2CRegFile::slave_transmit(bool yes)
{
  io_state = yes ? TX_REG_DATA : RX_REG_ADDR;
}


bool I2CRegFile::match_address()
{
  if ((xfr_data & 0xfe) != i2c_slave_address) {
    return false;
  }

  if (m_address_nack_count != 0) {
    m_address_nack_count--;
    m_address_nack_count_attr->Integer::set(static_cast<gint64>(m_address_nack_count));
    return false;
  }

  if (m_address_stretch_scl_cycles != 0) {
    start_timed_scl_hold(m_address_stretch_scl_cycles);
  }

  return true;
}


Module *I2CRegFile::construct(const char *_new_name)
{
  I2CRegFile *regfile = new I2CRegFile(_new_name);
  regfile->create_iopin_map();
  return regfile;
}


void I2CRegFile::create_iopin_map()
{
  addSymbol((IOPIN *)sda);
  addSymbol((IOPIN *)scl);
  package = new Package(8);
  package->assign_pin(5, (IOPIN *)(sda));
  package->assign_pin(6, (IOPIN *)(scl));
}


void I2CRegFile::release_timed_scl_hold()
{
  m_timed_scl_hold_active = false;
  m_timed_scl_release_cycle = 0;
  m_stretch_scl_cycles_attr->Integer::set(0);
  schedule_scl_drive_update();
}


void I2CRegFile::set_address_nack_count(unsigned int count)
{
  m_address_nack_count = count;
}


void I2CRegFile::set_address_stretch_scl_cycles(guint64 cycles)
{
  m_address_stretch_scl_cycles = cycles;
}


void I2CRegFile::set_data_nack_count(unsigned int count)
{
  m_data_nack_count = count;
}


void I2CRegFile::set_data_stuck_sda_cycles(guint64 cycles)
{
  m_data_stuck_sda_cycles = cycles;
}


void I2CRegFile::set_hold_scl_low(bool hold_low)
{
  m_hold_scl_low = hold_low;
  get_cycles().clear_break(m_stretch_release_trigger);
  if (hold_low) {
    m_timed_scl_hold_active = true;
    m_timed_scl_release_cycle = get_cycles().get() + kPersistentSclHoldCycles;
    get_cycles().set_break(m_timed_scl_release_cycle, m_stretch_release_trigger);
  } else {
    m_timed_scl_hold_active = false;
    m_timed_scl_release_cycle = 0;
    m_stretch_scl_cycles_attr->Integer::set(0);
  }
  schedule_scl_drive_update();
}


void I2CRegFile::start_timed_scl_hold(guint64 cycles)
{
  get_cycles().clear_break(m_stretch_release_trigger);
  if (cycles == 0) {
    m_timed_scl_hold_active = false;
    m_timed_scl_release_cycle = 0;
    schedule_scl_drive_update();
    return;
  }

  m_timed_scl_hold_active = true;
  m_timed_scl_release_cycle = get_cycles().get() + cycles;
  schedule_scl_drive_update();
  get_cycles().set_break(m_timed_scl_release_cycle, m_stretch_release_trigger);
}


void I2CRegFile::apply_scl_drive()
{
  update_scl_drive();
}


void I2CRegFile::release_timed_sda_hold()
{
  m_timed_sda_hold_active = false;
  m_timed_sda_release_cycle = 0;
  schedule_sda_drive_update();
}


void I2CRegFile::start_timed_sda_hold(guint64 cycles)
{
  get_cycles().clear_break(m_sda_release_trigger);
  if (cycles == 0) {
    m_timed_sda_hold_active = false;
    m_timed_sda_release_cycle = 0;
    schedule_sda_drive_update();
    return;
  }

  m_timed_sda_hold_active = true;
  m_timed_sda_release_cycle = get_cycles().get() + cycles;
  schedule_sda_drive_update();
  get_cycles().set_break(m_timed_sda_release_cycle, m_sda_release_trigger);
}


void I2CRegFile::apply_sda_drive()
{
  update_sda_drive();
}


void I2CRegFile::set_sda_driving_state(bool new_state)
{
  m_requested_sda_release = new_state;
  update_sda_drive();
}


void I2CRegFile::update_scl_drive()
{
  const bool drive_low = m_hold_scl_low || m_timed_scl_hold_active;
  set_scl_driving_state(!drive_low);
}


void I2CRegFile::schedule_scl_drive_update()
{
  get_cycles().clear_break(m_scl_apply_trigger);
  get_cycles().set_break(get_cycles().get() + 1, m_scl_apply_trigger);
}


void I2CRegFile::update_sda_drive()
{
  const bool effective_release = !m_timed_sda_hold_active && m_requested_sda_release;
  i2c_slave::set_sda_driving_state(effective_release);
}


void I2CRegFile::schedule_sda_drive_update()
{
  get_cycles().clear_break(m_sda_apply_trigger);
  get_cycles().set_break(get_cycles().get() + 1, m_sda_apply_trigger);
}

} // end of namespace I2CRegFile_Modules


void I2CRegFileAddressNackCountAttribute::set(gint64 v)
{
  const unsigned int count = v <= 0 ? 0U : static_cast<unsigned int>(v);
  Integer::set(static_cast<gint64>(count));
  if (m_regfile) {
    m_regfile->set_address_nack_count(count);
  }
}


void I2CRegFileAddressStretchSCLCyclesAttribute::set(gint64 v)
{
  const guint64 cycles = v <= 0 ? 0U : static_cast<guint64>(v);
  Integer::set(static_cast<gint64>(cycles));
  if (m_regfile) {
    m_regfile->set_address_stretch_scl_cycles(cycles);
  }
}


void I2CRegFileDataNackCountAttribute::set(gint64 v)
{
  const unsigned int count = v <= 0 ? 0U : static_cast<unsigned int>(v);
  Integer::set(static_cast<gint64>(count));
  if (m_regfile) {
    m_regfile->set_data_nack_count(count);
  }
}


void I2CRegFileDataStuckSdaCyclesAttribute::set(gint64 v)
{
  const guint64 cycles = v <= 0 ? 0U : static_cast<guint64>(v);
  Integer::set(static_cast<gint64>(cycles));
  if (m_regfile) {
    m_regfile->set_data_stuck_sda_cycles(cycles);
  }
}


void I2CRegFileHoldSCLLowAttribute::set(gint64 v)
{
  const bool hold_low = v != 0;
  Integer::set(hold_low ? 1 : 0);
  if (m_regfile) {
    m_regfile->set_hold_scl_low(hold_low);
  }
}


void I2CRegFileStretchSCLCyclesAttribute::set(gint64 v)
{
  const guint64 cycles = v <= 0 ? 0U : static_cast<guint64>(v);
  Integer::set(static_cast<gint64>(cycles));
  if (m_regfile) {
    m_regfile->start_timed_scl_hold(cycles);
  }
}


void I2CRegFileSclApplyTrigger::callback()
{
  if (m_regfile) {
    m_regfile->apply_scl_drive();
  }
}


void I2CRegFileStretchReleaseTrigger::callback()
{
  if (m_regfile) {
    m_regfile->release_timed_scl_hold();
  }
}


void I2CRegFileSdaApplyTrigger::callback()
{
  if (m_regfile) {
    m_regfile->apply_sda_drive();
  }
}


void I2CRegFileSdaReleaseTrigger::callback()
{
  if (m_regfile) {
    m_regfile->release_timed_sda_hold();
  }
}
