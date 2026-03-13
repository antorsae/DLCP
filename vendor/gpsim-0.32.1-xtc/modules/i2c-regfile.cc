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

#include "../src/packages.h"
#include "../src/registers.h"
#include "../src/stimuli.h"
#include "../src/symbol.h"
#include "../src/value.h"
#include "i2c-regfile.h"


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


namespace I2CRegFile_Modules {

I2CRegFile::I2CRegFile(const char *_name)
  : i2c_slave(),
    Module(_name, "i2c_regfile"),
    m_registers(new Register *[kRegisterCount]),
    m_slave_address_attr(new I2CRegFileAddressAttribute(this)),
    m_reg_addr(0),
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
}


I2CRegFile::~I2CRegFile()
{
  for (unsigned int i = 0; i < kRegisterCount; ++i) {
    removeSymbol(m_registers[i]);
    delete m_registers[i];
  }
  delete [] m_registers;

  removeSymbol(m_slave_address_attr);
  delete m_slave_address_attr;

  removeSymbol((IOPIN *)scl);
  removeSymbol((IOPIN *)sda);
  sda = nullptr;
  scl = nullptr;
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
  return ((xfr_data & 0xfe) == i2c_slave_address);
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

} // end of namespace I2CRegFile_Modules
