	list    p=16f628 

#define PORT (porta & 0x03) == 0x03
look	macro  port, comment
	.direct "a", "port, comment"
	endm

	look PORT, \"the black cat\"

	end
