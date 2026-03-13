GPSIM_PATH ?= ../../../../artifacts/tools/gpsim-xtc/bin

include ../make.regression

all: p18f25k20.cod

p%.cod: p%.o
	gplink -q --map -o $@ $<

sim: sim_p18f25k20

.PHONY: all clean sim
