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

#ifndef MODULES_I2C_REGFILE_H_
#define MODULES_I2C_REGFILE_H_

/* IN_MODULE should be defined for modules */
#define IN_MODULE

#include "../src/modules.h"
#include "../src/i2c-ee.h"

class Register;

namespace I2CRegFile_Modules {

class I2CRegFile : public i2c_slave, public Module {
public:
  explicit I2CRegFile(const char *_name);
  ~I2CRegFile();

  static Module *construct(const char *new_name);
  void create_iopin_map();
  bool match_address() override;
  void put_data(unsigned int data) override;
  unsigned int get_data() override;
  void slave_transmit(bool yes) override;

private:
  static constexpr unsigned int kRegisterCount = 256;

  Register **m_registers;
  gpsimObject *m_slave_address_attr;
  unsigned int m_reg_addr;

  enum io_state_t {
    RX_REG_ADDR = 1,
    RX_REG_DATA,
    TX_REG_DATA
  } io_state;
};

} // end of namespace I2CRegFile_Modules

#endif // MODULES_I2C_REGFILE_H_
