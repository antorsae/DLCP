
#EXTENDED_INSTRUCTIONS=1

include ../make.regression


SCRIPT = 18f2455.lkr

PROJECT = instructions
OBJECTS =  $(PROJECT).o
OUTPUT = $(PROJECT).hex
COD = $(PROJECT).cod
STC = $(PROJECT).stc

all : reset.cod eusart_2455.cod eusart_4455.cod q.cod q2455.cod dc628.cod stack.cod stack_reset.cod p16f505.cod spp_4455.cod p16f886.cod test_pwm2.cod tmr4.cod debug.cod

tmr4.cod:  tmr4.o
	gplink --map -o tmr4.cod tmr4.o

p16f886.cod:  p16f886.o
	gplink -o p16f886.cod p16f886.o

test_pwm2.cod:  test_pwm2.o
	gplink -o test_pwm2.cod test_pwm2.o

reset.cod: reset.o $(SCRIPT)
	gplink --map  -s $(SCRIPT) -o reset.cod reset.o

stack.cod: stack.o $(SCRIPT)
	gplink --map  -s $(SCRIPT) -o stack.cod stack.o

stack_reset.cod: stack_reset.o $(SCRIPT)
	gplink --map  -s $(SCRIPT) -o stack_reset.cod stack_reset.o

q2455.cod: q2455.o $(SCRIPT)
	gplink --map  -s $(SCRIPT) -o q2455.cod q2455.o

q.cod: q.o 12f508_g.lkr p16f505.cod
	gplink --map  -s 12f508_g.lkr -o q.cod q.o

p16f505.cod: p16f505.o
	gplink --map  -s 16f505_g.lkr -o p16f505.cod p16f505.o

dc628.cod: dc628.o 16f628.lkr
	gplink --map  -s 16f628.lkr -o dc628.cod dc628.o

eusart_2455.cod: eusart_2455.o 18f2455.lkr
	gplink --map -s 18f2455.lkr -o eusart_2455.cod eusart_2455.o

eusart_4455.cod: eusart_4455.o 18f2455.lkr
	gplink --map -s 18f2455.lkr -o eusart_4455.cod eusart_4455.o

spp_4455.cod: spp_4455.o 18f2455.lkr
	gplink --map -s 18f2455.lkr -o spp_4455.cod  spp_4455.o

debug.cod: debug.o
	gplink --map -q -o debug.cod debug.o

sim: 
