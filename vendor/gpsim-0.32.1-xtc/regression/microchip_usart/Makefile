
p16_tprp.cod: p16_tprp.o
	gplink --map -s 16f877.lkr -o $@  $<

p16_tprp.o: p16_tprp.asm
	gpasm -c $<
