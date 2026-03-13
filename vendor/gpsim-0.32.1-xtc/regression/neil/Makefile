include ../make.regression


all : q.cod debouncer.cod

q.cod : q.o
	gplink --map -s 16f690_g.lkr -o $@  $^

debouncer.cod : debouncer.o
	gplink --map -s 16f690_g.lkr -o $@  $^


