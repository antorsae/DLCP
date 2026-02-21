
firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe:	file format coff-i386

Disassembly of section CODE:

00401000 <CODE>:
  556fcb: 8b 83 74 03 00 00            	mov	eax, dword ptr [ebx + 0x374]
  556fd1: 33 d2                        	xor	edx, edx
  556fd3: 89 90 20 01 00 00            	mov	dword ptr [eax + 0x120], edx
  556fd9: 89 90 24 01 00 00            	mov	dword ptr [eax + 0x124], edx
  556fdf: 8b 83 70 03 00 00            	mov	eax, dword ptr [ebx + 0x370]
  556fe5: 33 d2                        	xor	edx, edx
  556fe7: 89 90 20 01 00 00            	mov	dword ptr [eax + 0x120], edx
  556fed: 89 90 24 01 00 00            	mov	dword ptr [eax + 0x124], edx
  556ff3: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  556ff9: 8b 12                        	mov	edx, dword ptr [edx]
  556ffb: 8a 52 4e                     	mov	dl, byte ptr [edx + 0x4e]
  556ffe: 80 ea 02                     	sub	dl, 0x2
  557001: 74 0f                        	je	0x557012 <CODE+0x156012>
  557003: fe ca                        	dec	dl
  557005: 74 24                        	je	0x55702b <CODE+0x15602b>
  557007: 80 ea 02                     	sub	dl, 0x2
  55700a: 74 3b                        	je	0x557047 <CODE+0x156047>
  55700c: fe ca                        	dec	dl
  55700e: 74 4d                        	je	0x55705d <CODE+0x15605d>
  557010: eb 62                        	jmp	0x557074 <CODE+0x156074>
  557012: ba 01 00 00 00               	mov	edx, 0x1
  557017: e8 b8 2b ee ff               	call	0x439bd4 <CODE+0x38bd4>
  55701c: 33 d2                        	xor	edx, edx
  55701e: 8b 83 74 03 00 00            	mov	eax, dword ptr [ebx + 0x374]
  557024: e8 ab 2b ee ff               	call	0x439bd4 <CODE+0x38bd4>
  557029: eb 49                        	jmp	0x557074 <CODE+0x156074>
  55702b: ba 01 00 00 00               	mov	edx, 0x1
  557030: e8 9f 2b ee ff               	call	0x439bd4 <CODE+0x38bd4>
  557035: ba 01 00 00 00               	mov	edx, 0x1
  55703a: 8b 83 74 03 00 00            	mov	eax, dword ptr [ebx + 0x374]
  557040: e8 8f 2b ee ff               	call	0x439bd4 <CODE+0x38bd4>
  557045: eb 2d                        	jmp	0x557074 <CODE+0x156074>
  557047: 33 d2                        	xor	edx, edx
  557049: e8 86 2b ee ff               	call	0x439bd4 <CODE+0x38bd4>
  55704e: 33 d2                        	xor	edx, edx
  557050: 8b 83 74 03 00 00            	mov	eax, dword ptr [ebx + 0x374]
  557056: e8 79 2b ee ff               	call	0x439bd4 <CODE+0x38bd4>
  55705b: eb 17                        	jmp	0x557074 <CODE+0x156074>
  55705d: 33 d2                        	xor	edx, edx
  55705f: e8 70 2b ee ff               	call	0x439bd4 <CODE+0x38bd4>
  557064: ba 01 00 00 00               	mov	edx, 0x1
  557069: 8b 83 74 03 00 00            	mov	eax, dword ptr [ebx + 0x374]
  55706f: e8 60 2b ee ff               	call	0x439bd4 <CODE+0x38bd4>
  557074: 8b 83 74 03 00 00            	mov	eax, dword ptr [ebx + 0x374]
  55707a: 89 98 24 01 00 00            	mov	dword ptr [eax + 0x124], ebx
  557080: c7 80 20 01 00 00 f4 71 55 00	mov	dword ptr [eax + 0x120], 0x5571f4
  55708a: 8b 83 70 03 00 00            	mov	eax, dword ptr [ebx + 0x370]
  557090: 89 98 24 01 00 00            	mov	dword ptr [eax + 0x124], ebx
  557096: c7 80 20 01 00 00 f4 71 55 00	mov	dword ptr [eax + 0x120], 0x5571f4
  5570a0: 8b d3                        	mov	edx, ebx
  5570a2: 8b c3                        	mov	eax, ebx
  5570a4: e8 4b 01 00 00               	call	0x5571f4 <CODE+0x1561f4>
  5570a9: eb 57                        	jmp	0x557102 <CODE+0x156102>
  5570ab: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  5570b1: 3c 03                        	cmp	al, 0x3
  5570b3: 75 4d                        	jne	0x557102 <CODE+0x156102>
  5570b5: 8b 83 fc 02 00 00            	mov	eax, dword ptr [ebx + 0x2fc]
  5570bb: e8 ac 36 f0 ff               	call	0x45a76c <CODE+0x5976c>
  5570c0: 8b 83 0c 03 00 00            	mov	eax, dword ptr [ebx + 0x30c]
  5570c6: e8 a1 36 f0 ff               	call	0x45a76c <CODE+0x5976c>
  5570cb: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  5570d1: e8 8e 36 f0 ff               	call	0x45a764 <CODE+0x59764>
  5570d6: 8b 83 68 03 00 00            	mov	eax, dword ptr [ebx + 0x368]
  5570dc: e8 83 36 f0 ff               	call	0x45a764 <CODE+0x59764>
  5570e1: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  5570e7: e8 78 36 f0 ff               	call	0x45a764 <CODE+0x59764>
  5570ec: 8b 83 24 03 00 00            	mov	eax, dword ptr [ebx + 0x324]
  5570f2: e8 6d 36 f0 ff               	call	0x45a764 <CODE+0x59764>
  5570f7: 8b 83 28 03 00 00            	mov	eax, dword ptr [ebx + 0x328]
  5570fd: e8 62 36 f0 ff               	call	0x45a764 <CODE+0x59764>
  557102: 5b                           	pop	ebx
  557103: c3                           	ret
  557104: ff ff                        	<unknown>
  557106: ff ff                        	<unknown>
  557108: 04 00                        	add	al, 0x0
  55710a: 00 00                        	add	byte ptr [eax], al
  55710c: 4c                           	dec	esp
  55710d: 65 66 74 00                  	je	0x557111 <CODE+0x156111>
  557111: 00 00                        	add	byte ptr [eax], al
  557113: 00 ff                        	add	bh, bh
  557115: ff ff                        	<unknown>
  557117: ff 03                        	inc	dword ptr [ebx]
  557119: 00 00                        	add	byte ptr [eax], al
  55711b: 00 53 75                     	add	byte ptr [ebx + 0x75], dl
  55711e: 62 00                        	bound	eax, dword ptr [eax]
  557120: ff ff                        	<unknown>
  557122: ff ff                        	<unknown>
  557124: 07                           	pop	es
  557125: 00 00                        	add	byte ptr [eax], al
  557127: 00 4d 69                     	add	byte ptr [ebp + 0x69], cl
  55712a: 64 2f                        	das
  55712c: 53                           	push	ebx
  55712d: 75 62                        	jne	0x557191 <CODE+0x156191>
  55712f: 00 ff                        	add	bh, bh
  557131: ff ff                        	<unknown>
  557133: ff 04 00                     	inc	dword ptr [eax + eax]
  557136: 00 00                        	add	byte ptr [eax], al
  557138: 53                           	push	ebx
  557139: 69 64 65 00 00 00 00 ff      	imul	esp, dword ptr [ebp + 2*eiz], 0xff000000
  557141: ff ff                        	<unknown>
  557143: ff 05 00 00 00 52            	inc	dword ptr [0x52000000]
  557149: 69 67 68 74 00 00 00         	imul	esp, dword ptr [edi + 0x68], 0x74
  557150: 53                           	push	ebx
  557151: 8b d8                        	mov	ebx, eax
  557153: 8b c3                        	mov	eax, ebx
  557155: e8 aa 1d 00 00               	call	0x558f04 <CODE+0x157f04>
  55715a: 84 c0                        	test	al, al
  55715c: 74 0c                        	je	0x55716a <CODE+0x15616a>
  55715e: a1 70 96 56 00               	mov	eax, dword ptr [0x569670]
  557163: 8b 00                        	mov	eax, dword ptr [eax]
  557165: e8 72 36 f2 ff               	call	0x47a7dc <CODE+0x797dc>
  55716a: 5b                           	pop	ebx
  55716b: c3                           	ret
  55716c: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  557172: 8b 12                        	mov	edx, dword ptr [edx]
  557174: 92                           	xchg	eax, edx
  557175: e8 42 af 00 00               	call	0x5620bc <CODE+0x1610bc>
  55717a: c3                           	ret
  55717b: 90                           	nop
  55717c: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  557182: 8b 12                        	mov	edx, dword ptr [edx]
  557184: 92                           	xchg	eax, edx
  557185: e8 8a d2 00 00               	call	0x564414 <CODE+0x163414>
  55718a: c3                           	ret
  55718b: 90                           	nop
  55718c: 6a 05                        	push	0x5
  55718e: 6a 00                        	push	0x0
  557190: 6a 00                        	push	0x0
  557192: 68 a4 71 55 00               	push	0x5571a4
  557197: 68 b0 71 55 00               	push	0x5571b0
  55719c: 6a 00                        	push	0x0
  55719e: e8 75 be ed ff               	call	0x433018 <CODE+0x32018>
  5571a3: c3                           	ret
  5571a4: 72 65                        	jb	0x55720b <CODE+0x15620b>
  5571a6: 61                           	popal
  5571a7: 64 6d                        	insd	dword ptr es:[edi], dx
  5571a9: 65 2e 74 78                  	je	0x557225 <CODE+0x156225>
  5571ad: 74 00                        	je	0x5571af <CODE+0x1561af>
  5571af: 00 6f 70                     	add	byte ptr [edi + 0x70], ch
  5571b2: 65 6e                        	outsb	dx, byte ptr gs:[esi]
  5571b4: 00 00                        	add	byte ptr [eax], al
  5571b6: 00 00                        	add	byte ptr [eax], al
  5571b8: 8b 80 68 03 00 00            	mov	eax, dword ptr [eax + 0x368]
  5571be: 8a 80 18 02 00 00            	mov	al, byte ptr [eax + 0x218]
  5571c4: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  5571ca: 8b 12                        	mov	edx, dword ptr [edx]
  5571cc: 88 42 57                     	mov	byte ptr [edx + 0x57], al
  5571cf: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5571d4: 8b 00                        	mov	eax, dword ptr [eax]
  5571d6: 80 78 05 06                  	cmp	byte ptr [eax + 0x5], 0x6
  5571da: 74 0e                        	je	0x5571ea <CODE+0x1561ea>
  5571dc: 33 c9                        	xor	ecx, ecx
  5571de: b2 05                        	mov	dl, 0x5
  5571e0: a1 88 b4 57 00               	mov	eax, dword ptr [0x57b488]
  5571e5: e8 66 dd ff ff               	call	0x554f50 <CODE+0x153f50>
  5571ea: c3                           	ret
  5571eb: 90                           	nop
  5571ec: e8 0b 00 00 00               	call	0x5571fc <CODE+0x1561fc>
  5571f1: c3                           	ret
  5571f2: 8b c0                        	mov	eax, eax
  5571f4: e8 03 00 00 00               	call	0x5571fc <CODE+0x1561fc>
  5571f9: c3                           	ret
  5571fa: 8b c0                        	mov	eax, eax
  5571fc: c6 05 8d b4 57 00 01         	mov	byte ptr [0x57b48d], 0x1
  557203: 8b 90 70 03 00 00            	mov	edx, dword ptr [eax + 0x370]
  557209: 8b 92 18 02 00 00            	mov	edx, dword ptr [edx + 0x218]
  55720f: 83 ea 01                     	sub	edx, 0x1
  557212: 72 0b                        	jb	0x55721f <CODE+0x15621f>
  557214: 0f 84 91 00 00 00            	je	0x5572ab <CODE+0x1562ab>
  55721a: e9 23 01 00 00               	jmp	0x557342 <CODE+0x156342>
  55721f: 8b 90 74 03 00 00            	mov	edx, dword ptr [eax + 0x374]
  557225: 83 ba 18 02 00 00 00         	cmp	dword ptr [edx + 0x218], 0x0
  55722c: 75 0c                        	jne	0x55723a <CODE+0x15623a>
  55722e: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  557234: 8b 12                        	mov	edx, dword ptr [edx]
  557236: c6 42 4e 05                  	mov	byte ptr [edx + 0x4e], 0x5
  55723a: 8b 80 74 03 00 00            	mov	eax, dword ptr [eax + 0x374]
  557240: 83 b8 18 02 00 00 01         	cmp	dword ptr [eax + 0x218], 0x1
  557247: 75 0b                        	jne	0x557254 <CODE+0x156254>
  557249: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  55724e: 8b 00                        	mov	eax, dword ptr [eax]
  557250: c6 40 4e 06                  	mov	byte ptr [eax + 0x4e], 0x6
  557254: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  557259: 8b 00                        	mov	eax, dword ptr [eax]
  55725b: 8b 80 44 09 70 00            	mov	eax, dword ptr [eax + 0x700944]
  557261: e8 0e f4 ea ff               	call	0x406674 <CODE+0x5674>
  557266: 85 c0                        	test	eax, eax
  557268: 0f 84 d4 00 00 00            	je	0x557342 <CODE+0x156342>
  55726e: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  557273: 8b 00                        	mov	eax, dword ptr [eax]
  557275: 8b 80 44 09 70 00            	mov	eax, dword ptr [eax + 0x700944]
  55727b: 8b 00                        	mov	eax, dword ptr [eax]
  55727d: 8b 40 04                     	mov	eax, dword ptr [eax + 0x4]
  557280: 33 d2                        	xor	edx, edx
  557282: 8b 08                        	mov	ecx, dword ptr [eax]
  557284: ff 91 cc 00 00 00            	call	dword ptr [ecx + 0xcc]
  55728a: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55728f: 8b 00                        	mov	eax, dword ptr [eax]
  557291: 8b 80 44 09 70 00            	mov	eax, dword ptr [eax + 0x700944]
  557297: 8b 40 04                     	mov	eax, dword ptr [eax + 0x4]
  55729a: 8b 00                        	mov	eax, dword ptr [eax]
  55729c: 33 d2                        	xor	edx, edx
  55729e: 8b 08                        	mov	ecx, dword ptr [eax]
  5572a0: ff 91 cc 00 00 00            	call	dword ptr [ecx + 0xcc]
  5572a6: e9 97 00 00 00               	jmp	0x557342 <CODE+0x156342>
  5572ab: 8b 90 74 03 00 00            	mov	edx, dword ptr [eax + 0x374]
  5572b1: 83 ba 18 02 00 00 00         	cmp	dword ptr [edx + 0x218], 0x0
  5572b8: 75 0c                        	jne	0x5572c6 <CODE+0x1562c6>
  5572ba: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  5572c0: 8b 12                        	mov	edx, dword ptr [edx]
  5572c2: c6 42 4e 02                  	mov	byte ptr [edx + 0x4e], 0x2
  5572c6: 8b 80 74 03 00 00            	mov	eax, dword ptr [eax + 0x374]
  5572cc: 83 b8 18 02 00 00 01         	cmp	dword ptr [eax + 0x218], 0x1
  5572d3: 75 0b                        	jne	0x5572e0 <CODE+0x1562e0>
  5572d5: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5572da: 8b 00                        	mov	eax, dword ptr [eax]
  5572dc: c6 40 4e 03                  	mov	byte ptr [eax + 0x4e], 0x3
  5572e0: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5572e5: 8b 00                        	mov	eax, dword ptr [eax]
  5572e7: 8b 80 44 09 70 00            	mov	eax, dword ptr [eax + 0x700944]
  5572ed: e8 82 f3 ea ff               	call	0x406674 <CODE+0x5674>
  5572f2: 85 c0                        	test	eax, eax
  5572f4: 74 4c                        	je	0x557342 <CODE+0x156342>
  5572f6: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5572fb: 8b 00                        	mov	eax, dword ptr [eax]
  5572fd: 8b 80 44 09 70 00            	mov	eax, dword ptr [eax + 0x700944]
  557303: 8b 00                        	mov	eax, dword ptr [eax]
  557305: 8b 40 04                     	mov	eax, dword ptr [eax + 0x4]
  557308: b2 01                        	mov	dl, 0x1
  55730a: 8b 08                        	mov	ecx, dword ptr [eax]
  55730c: ff 91 cc 00 00 00            	call	dword ptr [ecx + 0xcc]
  557312: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  557317: 8b 00                        	mov	eax, dword ptr [eax]
  557319: 8b 80 44 09 70 00            	mov	eax, dword ptr [eax + 0x700944]
  55731f: 8b 40 04                     	mov	eax, dword ptr [eax + 0x4]
  557322: 8b 00                        	mov	eax, dword ptr [eax]
  557324: 33 d2                        	xor	edx, edx
  557326: 8b 08                        	mov	ecx, dword ptr [eax]
  557328: ff 91 cc 00 00 00            	call	dword ptr [ecx + 0xcc]
  55732e: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  557334: 8b 12                        	mov	edx, dword ptr [edx]
  557336: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55733b: 8b 00                        	mov	eax, dword ptr [eax]
  55733d: e8 ce b4 00 00               	call	0x562810 <CODE+0x161810>
  557342: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  557347: 8b 00                        	mov	eax, dword ptr [eax]
  557349: 80 78 05 06                  	cmp	byte ptr [eax + 0x5], 0x6
  55734d: 74 0e                        	je	0x55735d <CODE+0x15635d>
  55734f: 33 c9                        	xor	ecx, ecx
  557351: b2 05                        	mov	dl, 0x5
  557353: a1 88 b4 57 00               	mov	eax, dword ptr [0x57b488]
  557358: e8 f3 db ff ff               	call	0x554f50 <CODE+0x153f50>
  55735d: c3                           	ret
  55735e: 8b c0                        	mov	eax, eax
