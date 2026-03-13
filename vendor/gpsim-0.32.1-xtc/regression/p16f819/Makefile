include ../make.regression


SCRIPT = 16f819.lkr

all :  a2d_819.cod ccp_819.cod

%.cod : %.o
	gplink --map -s $(SCRIPT) -o $@ $<


sim: sim_a2d_819 sim_ccp_819

