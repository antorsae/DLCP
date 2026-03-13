# WDT module regression test
#
#

include ../make.regression


all :   tmr1_16f628.cod tmr1_16f88.cod


p%.cod : p%.o
	gplink --map -s $*.lkr -o $@  $<

tmr1_%.cod : tmr1_%.o
	gplink --map  -o $@  $<

wdt_%.cod : wdt_%.o
	gplink --map -s $*.lkr -o $@  $<

nwdt_%.cod : nwdt_%.o
	gplink --map -s $*.lkr -o $@  $<


sim: sim_p16f628

