include ../make.regression


SCRIPT = 18f452.lkr

PROJECT = tmr3_16bit
OBJECTS =  $(PROJECT).o 
OUTPUT = $(PROJECT).hex
COD = $(PROJECT).cod
STC = $(PROJECT).stc

all : debug.cod d4550.cod d2550.cod d2455.cod

$(OUTPUT) $(COD) : $(OBJECTS) $(SCRIPT)
	gplink --map -s $(SCRIPT) -o $(OUTPUT) $(OBJECTS)

tmr3_18f4550.cod : tmr3_18f4550.o
	gplink --map -s 18f4550_g.lkr -o tmr3_18f4550.cod tmr3_18f4550.o

sim: sim_16bit sim_18f4550

debug.o: debug.asm

d4550.cod: d4550.o
	gplink --map -o d4550.cod d4550.o

d2550.cod: d2550.o
	gplink --map -o d2550.cod d2550.o

d2455.cod: d2455.o
	gplink --map -o d2455.cod d2455.o


debug.cod: debug.o
	gplink --map -o debug.cod debug.o

sim_16bit: tmr3_16bit.cod 
	$(GPSIM) -i -I $(STARTUP_STC) -D STC=$<

sim_18f4550: tmr3_18f4550.cod
	$(GPSIM) -i -I $(STARTUP_STC) -D STC=$<
