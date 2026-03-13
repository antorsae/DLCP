include ../make.regression


SCRIPT = 16f873.lkr

all : p16f873.cod 

%.cod : %.o
	gplink --map -s $(SCRIPT) -o $@ $<


sim: sim_p16f873

