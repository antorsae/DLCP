# P12f1822, P16F1823  processor regression tests
#
#

include ../make.regression


all :  p16f716.cod p16c716.cod p16c712.cod pwm_712.cod pwm_f716.cod



%.cod : %.o
	gplink --map -o $@  $<

sim: sim_p16f716 sim_p16c716 sim_p16c712 sim_pwm_712 sim_pwm_f716

