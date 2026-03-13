
#EXTENDED_INSTRUCTIONS=1

include ../make.regression


SCRIPT = 18f2455.lkr

PROJECT = instructions
OBJECTS =  $(PROJECT).o
OUTPUT = $(PROJECT).hex
COD = $(PROJECT).cod
STC = $(PROJECT).stc

all : miss.cod

miss.cod: miss.o 12f508_g.lkr 
	gplink --map  -s 12f508_g.lkr -o miss.cod miss.o

miss.o:	miss.asm miss.h

miss.h:
	cp sub.h miss.h
sim: 
