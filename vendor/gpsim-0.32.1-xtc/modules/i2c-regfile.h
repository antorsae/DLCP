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
class Integer;
class I2CRegFileSclApplyTrigger;
class I2CRegFileStretchReleaseTrigger;
class I2CRegFileSdaApplyTrigger;
class I2CRegFileSdaReleaseTrigger;

namespace I2CRegFile_Modules {

class I2CRegFile : public i2c_slave, public Module {
public:
  explicit I2CRegFile(const char *_name);
  ~I2CRegFile();

  static Module *construct(const char *new_name);
  void create_iopin_map();
  bool match_address() override;
  bool receive_data_byte(unsigned int data) override;
  void put_data(unsigned int data) override;
  unsigned int get_data() override;
  void slave_transmit(bool yes) override;
  void release_timed_scl_hold();
  void release_timed_sda_hold();
  void set_address_nack_count(unsigned int count);
  void set_address_stretch_scl_cycles(guint64 cycles);
  void set_address_stretch_count(int count);
  void set_data_nack_count(unsigned int count);
  void set_data_stuck_sda_cycles(guint64 cycles);
  void set_data_stuck_sda_count(int count);
  void set_hold_scl_low(bool hold_low);
  void start_timed_scl_hold(guint64 cycles);
  void start_timed_sda_hold(guint64 cycles);
  void apply_scl_drive();
  void apply_sda_drive();
  void set_sda_driving_state(bool new_state) override;

private:
  static constexpr unsigned int kRegisterCount = 256;

  Register **m_registers;
  Integer *m_slave_address_attr;
  Integer *m_address_nack_count_attr;
  Integer *m_address_stretch_scl_cycles_attr;
  Integer *m_address_stretch_count_attr;
  Integer *m_data_nack_count_attr;
  Integer *m_data_stuck_sda_cycles_attr;
  Integer *m_data_stuck_sda_count_attr;
  Integer *m_hold_scl_low_attr;
  Integer *m_stretch_scl_cycles_attr;
  unsigned int m_reg_addr;
  unsigned int m_address_nack_count;
  guint64 m_address_stretch_scl_cycles;
  int m_address_stretch_count;
  unsigned int m_data_nack_count;
  guint64 m_data_stuck_sda_cycles;
  int m_data_stuck_sda_count;
  bool m_hold_scl_low;
  bool m_timed_scl_hold_active;
  bool m_requested_sda_release;
  bool m_timed_sda_hold_active;
  guint64 m_timed_scl_release_cycle;
  guint64 m_timed_sda_release_cycle;
  I2CRegFileSclApplyTrigger *m_scl_apply_trigger;
  I2CRegFileStretchReleaseTrigger *m_stretch_release_trigger;
  I2CRegFileSdaApplyTrigger *m_sda_apply_trigger;
  I2CRegFileSdaReleaseTrigger *m_sda_release_trigger;

  enum io_state_t {
    RX_REG_ADDR = 1,
    RX_REG_DATA,
    TX_REG_DATA
  } io_state;

  void update_scl_drive();
  void schedule_scl_drive_update();
  void update_sda_drive();
  void schedule_sda_drive_update();
};

} // end of namespace I2CRegFile_Modules

#endif // MODULES_I2C_REGFILE_H_
