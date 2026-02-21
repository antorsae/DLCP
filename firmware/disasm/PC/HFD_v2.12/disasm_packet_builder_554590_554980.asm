
firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe:	file format coff-i386

Disassembly of section CODE:

00401000 <CODE>:
  554590: 53                           	push	ebx
  554591: 56                           	push	esi
  554592: 8b d8                        	mov	ebx, eax
  554594: c6 43 25 00                  	mov	byte ptr [ebx + 0x25], 0x0
  554598: 88 53 26                     	mov	byte ptr [ebx + 0x26], dl
  55459b: 33 c0                        	xor	eax, eax
  55459d: 8a c2                        	mov	al, dl
  55459f: 83 f8 07                     	cmp	eax, 0x7
  5545a2: 7d 1f                        	jge	0x5545c3 <CODE+0x1535c3>
  5545a4: 83 e8 03                     	sub	eax, 0x3
  5545a7: 74 42                        	je	0x5545eb <CODE+0x1535eb>
  5545a9: 48                           	dec	eax
  5545aa: 0f 84 b4 00 00 00            	je	0x554664 <CODE+0x153664>
  5545b0: 48                           	dec	eax
  5545b1: 0f 84 81 01 00 00            	je	0x554738 <CODE+0x153738>
  5545b7: 48                           	dec	eax
  5545b8: 0f 84 bb 02 00 00            	je	0x554879 <CODE+0x153879>
  5545be: e9 8c 03 00 00               	jmp	0x55494f <CODE+0x15394f>
  5545c3: 83 c0 f9                     	add	eax, -0x7
  5545c6: 83 e8 07                     	sub	eax, 0x7
  5545c9: 0f 82 b0 02 00 00            	jb	0x55487f <CODE+0x15387f>
  5545cf: 83 e8 32                     	sub	eax, 0x32
  5545d2: 0f 84 b8 02 00 00            	je	0x554890 <CODE+0x153890>
  5545d8: 48                           	dec	eax
  5545d9: 0f 84 4b 03 00 00            	je	0x55492a <CODE+0x15392a>
  5545df: 48                           	dec	eax
  5545e0: 0f 84 0a 03 00 00            	je	0x5548f0 <CODE+0x1538f0>
  5545e6: e9 64 03 00 00               	jmp	0x55494f <CODE+0x15394f>
  5545eb: 88 4b 27                     	mov	byte ptr [ebx + 0x27], cl
  5545ee: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5545f3: 8b 00                        	mov	eax, dword ptr [eax]
  5545f5: 80 b8 5c 09 70 00 09         	cmp	byte ptr [eax + 0x70095c], 0x9
  5545fc: 0f 85 4d 03 00 00            	jne	0x55494f <CODE+0x15394f>
  554602: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554607: 8b 00                        	mov	eax, dword ptr [eax]
  554609: 8b 80 50 09 70 00            	mov	eax, dword ptr [eax + 0x700950]
  55460f: e8 e0 0c eb ff               	call	0x4052f4 <CODE+0x42f4>
  554614: 85 c0                        	test	eax, eax
  554616: 0f 84 33 03 00 00            	je	0x55494f <CODE+0x15394f>
  55461c: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554621: 8b 00                        	mov	eax, dword ptr [eax]
  554623: 8b 80 50 09 70 00            	mov	eax, dword ptr [eax + 0x700950]
  554629: e8 c6 0c eb ff               	call	0x4052f4 <CODE+0x42f4>
  55462e: 8b d0                        	mov	edx, eax
  554630: 83 c2 03                     	add	edx, 0x3
  554633: 83 ea 03                     	sub	edx, 0x3
  554636: 0f 8c 13 03 00 00            	jl	0x55494f <CODE+0x15394f>
  55463c: 42                           	inc	edx
  55463d: b8 03 00 00 00               	mov	eax, 0x3
  554642: 83 f8 21                     	cmp	eax, 0x21
  554645: 7d 16                        	jge	0x55465d <CODE+0x15365d>
  554647: 8b 0d fc 98 56 00            	mov	ecx, dword ptr [0x5698fc]
  55464d: 8b 09                        	mov	ecx, dword ptr [ecx]
  55464f: 8b 89 50 09 70 00            	mov	ecx, dword ptr [ecx + 0x700950]
  554655: 8a 4c 01 fd                  	mov	cl, byte ptr [ecx + eax - 0x3]
  554659: 88 4c 03 25                  	mov	byte ptr [ebx + eax + 0x25], cl
  55465d: 40                           	inc	eax
  55465e: 4a                           	dec	edx
  55465f: 75 e1                        	jne	0x554642 <CODE+0x153642>
  554661: 5e                           	pop	esi
  554662: 5b                           	pop	ebx
  554663: c3                           	ret
  554664: 88 4b 27                     	mov	byte ptr [ebx + 0x27], cl
  554667: fe c9                        	dec	cl
  554669: 74 09                        	je	0x554674 <CODE+0x153674>
  55466b: fe c9                        	dec	cl
  55466d: 74 2a                        	je	0x554699 <CODE+0x153699>
  55466f: e9 db 02 00 00               	jmp	0x55494f <CODE+0x15394f>
  554674: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554679: 8b 00                        	mov	eax, dword ptr [eax]
  55467b: 8a 80 75 09 70 00            	mov	al, byte ptr [eax + 0x700975]
  554681: 88 43 28                     	mov	byte ptr [ebx + 0x28], al
  554684: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554689: 8b 00                        	mov	eax, dword ptr [eax]
  55468b: 8a 80 74 09 70 00            	mov	al, byte ptr [eax + 0x700974]
  554691: 88 43 29                     	mov	byte ptr [ebx + 0x29], al
  554694: e9 b6 02 00 00               	jmp	0x55494f <CODE+0x15394f>
  554699: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55469e: 8b 00                        	mov	eax, dword ptr [eax]
  5546a0: 8a 80 64 09 70 00            	mov	al, byte ptr [eax + 0x700964]
  5546a6: 88 43 2a                     	mov	byte ptr [ebx + 0x2a], al
  5546a9: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5546ae: 8b 00                        	mov	eax, dword ptr [eax]
  5546b0: 80 b8 64 09 70 00 06         	cmp	byte ptr [eax + 0x700964], 0x6
  5546b7: 75 28                        	jne	0x5546e1 <CODE+0x1536e1>
  5546b9: a1 4c 98 56 00               	mov	eax, dword ptr [0x56984c]
  5546be: 8b 00                        	mov	eax, dword ptr [eax]
  5546c0: 8b 10                        	mov	edx, dword ptr [eax]
  5546c2: ff 92 c8 00 00 00            	call	dword ptr [edx + 0xc8]
  5546c8: 3c 01                        	cmp	al, 0x1
  5546ca: 75 15                        	jne	0x5546e1 <CODE+0x1536e1>
  5546cc: b8 06 00 00 00               	mov	eax, 0x6
  5546d1: c6 44 03 25 00               	mov	byte ptr [ebx + eax + 0x25], 0x0
  5546d6: 40                           	inc	eax
  5546d7: 83 f8 16                     	cmp	eax, 0x16
  5546da: 75 f5                        	jne	0x5546d1 <CODE+0x1536d1>
  5546dc: e9 6e 02 00 00               	jmp	0x55494f <CODE+0x15394f>
  5546e1: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5546e6: 8b 00                        	mov	eax, dword ptr [eax]
  5546e8: 80 b8 64 09 70 00 06         	cmp	byte ptr [eax + 0x700964], 0x6
  5546ef: 0f 85 5a 02 00 00            	jne	0x55494f <CODE+0x15394f>
  5546f5: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5546fa: 8b 00                        	mov	eax, dword ptr [eax]
  5546fc: 8b 80 6c 09 70 00            	mov	eax, dword ptr [eax + 0x70096c]
  554702: e8 ed 0b eb ff               	call	0x4052f4 <CODE+0x42f4>
  554707: 8b d0                        	mov	edx, eax
  554709: 83 c2 06                     	add	edx, 0x6
  55470c: 83 ea 06                     	sub	edx, 0x6
  55470f: 0f 8c 3a 02 00 00            	jl	0x55494f <CODE+0x15394f>
  554715: 42                           	inc	edx
  554716: b8 06 00 00 00               	mov	eax, 0x6
  55471b: 8b 0d fc 98 56 00            	mov	ecx, dword ptr [0x5698fc]
  554721: 8b 09                        	mov	ecx, dword ptr [ecx]
  554723: 8b 89 6c 09 70 00            	mov	ecx, dword ptr [ecx + 0x70096c]
  554729: 8a 4c 01 fa                  	mov	cl, byte ptr [ecx + eax - 0x6]
  55472d: 88 4c 03 25                  	mov	byte ptr [ebx + eax + 0x25], cl
  554731: 40                           	inc	eax
  554732: 4a                           	dec	edx
  554733: 75 e6                        	jne	0x55471b <CODE+0x15371b>
  554735: 5e                           	pop	esi
  554736: 5b                           	pop	ebx
  554737: c3                           	ret
  554738: 8a 43 4c                     	mov	al, byte ptr [ebx + 0x4c]
  55473b: 88 43 27                     	mov	byte ptr [ebx + 0x27], al
  55473e: 8a 43 4e                     	mov	al, byte ptr [ebx + 0x4e]
  554741: 88 43 29                     	mov	byte ptr [ebx + 0x29], al
  554744: 8b 4b 48                     	mov	ecx, dword ptr [ebx + 0x48]
  554747: b2 06                        	mov	dl, 0x6
  554749: 8b c3                        	mov	eax, ebx
  55474b: e8 20 07 00 00               	call	0x554e70 <CODE+0x153e70>
  554750: 8a 43 50                     	mov	al, byte ptr [ebx + 0x50]
  554753: 88 43 2f                     	mov	byte ptr [ebx + 0x2f], al
  554756: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  55475b: 8b 00                        	mov	eax, dword ptr [eax]
  55475d: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  554761: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  554767: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  55476d: 8a 84 c2 28 10 00 00         	mov	al, byte ptr [edx + 8*eax + 0x1028]
  554774: 88 43 30                     	mov	byte ptr [ebx + 0x30], al
  554777: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  55477c: 8b 00                        	mov	eax, dword ptr [eax]
  55477e: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  554782: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  554788: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  55478e: 8a 84 c2 58 20 00 00         	mov	al, byte ptr [edx + 8*eax + 0x2058]
  554795: 88 43 31                     	mov	byte ptr [ebx + 0x31], al
  554798: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  55479d: 8b 00                        	mov	eax, dword ptr [eax]
  55479f: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  5547a3: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  5547a9: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  5547af: 8a 84 c2 88 30 00 00         	mov	al, byte ptr [edx + 8*eax + 0x3088]
  5547b6: 88 43 32                     	mov	byte ptr [ebx + 0x32], al
  5547b9: 8a 43 57                     	mov	al, byte ptr [ebx + 0x57]
  5547bc: 88 43 33                     	mov	byte ptr [ebx + 0x33], al
  5547bf: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5547c4: 8b 00                        	mov	eax, dword ptr [eax]
  5547c6: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  5547ca: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  5547d0: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  5547d6: 8a 84 c2 b8 40 00 00         	mov	al, byte ptr [edx + 8*eax + 0x40b8]
  5547dd: 88 43 34                     	mov	byte ptr [ebx + 0x34], al
  5547e0: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5547e5: 8b 00                        	mov	eax, dword ptr [eax]
  5547e7: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  5547eb: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  5547f1: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  5547f7: 8a 84 c2 e8 50 00 00         	mov	al, byte ptr [edx + 8*eax + 0x50e8]
  5547fe: 88 43 35                     	mov	byte ptr [ebx + 0x35], al
  554801: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  554806: 8b 00                        	mov	eax, dword ptr [eax]
  554808: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  55480c: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  554812: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  554818: 8a 84 c2 18 61 00 00         	mov	al, byte ptr [edx + 8*eax + 0x6118]
  55481f: 88 43 36                     	mov	byte ptr [ebx + 0x36], al
  554822: 8a 43 58                     	mov	al, byte ptr [ebx + 0x58]
  554825: 88 43 37                     	mov	byte ptr [ebx + 0x37], al
  554828: 8a 43 5e                     	mov	al, byte ptr [ebx + 0x5e]
  55482b: 88 43 38                     	mov	byte ptr [ebx + 0x38], al
  55482e: 8a 43 5f                     	mov	al, byte ptr [ebx + 0x5f]
  554831: 88 43 39                     	mov	byte ptr [ebx + 0x39], al
  554834: 8a 43 60                     	mov	al, byte ptr [ebx + 0x60]
  554837: 88 43 3a                     	mov	byte ptr [ebx + 0x3a], al
  55483a: 8a 43 61                     	mov	al, byte ptr [ebx + 0x61]
  55483d: 88 43 3b                     	mov	byte ptr [ebx + 0x3b], al
  554840: 8a 43 62                     	mov	al, byte ptr [ebx + 0x62]
  554843: 88 43 3c                     	mov	byte ptr [ebx + 0x3c], al
  554846: 8a 43 63                     	mov	al, byte ptr [ebx + 0x63]
  554849: 88 43 3d                     	mov	byte ptr [ebx + 0x3d], al
  55484c: 8a 43 64                     	mov	al, byte ptr [ebx + 0x64]
  55484f: 88 43 3e                     	mov	byte ptr [ebx + 0x3e], al
  554852: 8a 43 5a                     	mov	al, byte ptr [ebx + 0x5a]
  554855: 88 43 3f                     	mov	byte ptr [ebx + 0x3f], al
  554858: 8a 43 5b                     	mov	al, byte ptr [ebx + 0x5b]
  55485b: 88 43 40                     	mov	byte ptr [ebx + 0x40], al
  55485e: 8a 43 5c                     	mov	al, byte ptr [ebx + 0x5c]
  554861: 88 43 41                     	mov	byte ptr [ebx + 0x41], al
  554864: 8a 43 5d                     	mov	al, byte ptr [ebx + 0x5d]
  554867: 88 43 42                     	mov	byte ptr [ebx + 0x42], al
  55486a: 8a 43 65                     	mov	al, byte ptr [ebx + 0x65]
  55486d: 88 43 43                     	mov	byte ptr [ebx + 0x43], al
  554870: 8a 43 70                     	mov	al, byte ptr [ebx + 0x70]
  554873: 88 43 44                     	mov	byte ptr [ebx + 0x44], al
  554876: 5e                           	pop	esi
  554877: 5b                           	pop	ebx
  554878: c3                           	ret
  554879: 88 4b 27                     	mov	byte ptr [ebx + 0x27], cl
  55487c: 5e                           	pop	esi
  55487d: 5b                           	pop	ebx
  55487e: c3                           	ret
  55487f: c6 05 58 b3 57 00 01         	mov	byte ptr [0x57b358], 0x1
  554886: 8b c3                        	mov	eax, ebx
  554888: e8 ff 00 00 00               	call	0x55498c <CODE+0x15398c>
  55488d: 5e                           	pop	esi
  55488e: 5b                           	pop	ebx
  55488f: c3                           	ret
  554890: be 03 00 00 00               	mov	esi, 0x3
  554895: a1 58 94 56 00               	mov	eax, dword ptr [0x569458]
  55489a: 8b 53 6c                     	mov	edx, dword ptr [ebx + 0x6c]
  55489d: 8a 04 10                     	mov	al, byte ptr [eax + edx]
  5548a0: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  5548a6: 8b 12                        	mov	edx, dword ptr [edx]
  5548a8: 88 44 32 25                  	mov	byte ptr [edx + esi + 0x25], al
  5548ac: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5548b1: 8b 00                        	mov	eax, dword ptr [eax]
  5548b3: 80 78 55 4d                  	cmp	byte ptr [eax + 0x55], 0x4d
  5548b7: 75 19                        	jne	0x5548d2 <CODE+0x1538d2>
  5548b9: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5548be: 8b 00                        	mov	eax, dword ptr [eax]
  5548c0: 80 78 55 4d                  	cmp	byte ptr [eax + 0x55], 0x4d
  5548c4: 75 1e                        	jne	0x5548e4 <CODE+0x1538e4>
  5548c6: a1 04 92 56 00               	mov	eax, dword ptr [0x569204]
  5548cb: 8b 00                        	mov	eax, dword ptr [eax]
  5548cd: 3b 43 6c                     	cmp	eax, dword ptr [ebx + 0x6c]
  5548d0: 7e 12                        	jle	0x5548e4 <CODE+0x1538e4>
  5548d2: a1 58 94 56 00               	mov	eax, dword ptr [0x569458]
  5548d7: 8b 53 6c                     	mov	edx, dword ptr [ebx + 0x6c]
  5548da: 8a 14 10                     	mov	dl, byte ptr [eax + edx]
  5548dd: 8b c3                        	mov	eax, ebx
  5548df: e8 c0 05 00 00               	call	0x554ea4 <CODE+0x153ea4>
  5548e4: ff 43 6c                     	inc	dword ptr [ebx + 0x6c]
  5548e7: 46                           	inc	esi
  5548e8: 83 fe 21                     	cmp	esi, 0x21
  5548eb: 75 a8                        	jne	0x554895 <CODE+0x153895>
  5548ed: 5e                           	pop	esi
  5548ee: 5b                           	pop	ebx
  5548ef: c3                           	ret
  5548f0: be 03 00 00 00               	mov	esi, 0x3
  5548f5: a1 58 94 56 00               	mov	eax, dword ptr [0x569458]
  5548fa: 8b 53 6c                     	mov	edx, dword ptr [ebx + 0x6c]
  5548fd: 8a 04 10                     	mov	al, byte ptr [eax + edx]
  554900: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  554906: 8b 12                        	mov	edx, dword ptr [edx]
  554908: 88 44 32 25                  	mov	byte ptr [edx + esi + 0x25], al
  55490c: a1 58 94 56 00               	mov	eax, dword ptr [0x569458]
  554911: 8b 53 6c                     	mov	edx, dword ptr [ebx + 0x6c]
  554914: 8a 14 10                     	mov	dl, byte ptr [eax + edx]
  554917: 8b c3                        	mov	eax, ebx
  554919: e8 86 05 00 00               	call	0x554ea4 <CODE+0x153ea4>
  55491e: ff 43 6c                     	inc	dword ptr [ebx + 0x6c]
  554921: 46                           	inc	esi
  554922: 83 fe 21                     	cmp	esi, 0x21
  554925: 75 ce                        	jne	0x5548f5 <CODE+0x1538f5>
  554927: 5e                           	pop	esi
  554928: 5b                           	pop	ebx
  554929: c3                           	ret
  55492a: 0f b7 0d 6c b3 57 00         	movzx	ecx, word ptr [0x57b36c]
  554931: b2 03                        	mov	dl, 0x3
  554933: 8b c3                        	mov	eax, ebx
  554935: e8 36 05 00 00               	call	0x554e70 <CODE+0x153e70>
  55493a: 33 c0                        	xor	eax, eax
  55493c: 89 43 6c                     	mov	dword ptr [ebx + 0x6c], eax
  55493f: 33 c0                        	xor	eax, eax
  554941: a3 64 b3 57 00               	mov	dword ptr [0x57b364], eax
  554946: 66 c7 05 6c b3 57 00 00 00   	mov	word ptr [0x57b36c], 0x0
  55494f: 5e                           	pop	esi
  554950: 5b                           	pop	ebx
  554951: c3                           	ret
  554952: 8b c0                        	mov	eax, eax
  554954: 53                           	push	ebx
  554955: 56                           	push	esi
  554956: 57                           	push	edi
  554957: 8b f2                        	mov	esi, edx
  554959: 81 e6 ff 00 00 00            	and	esi, 0xff
  55495f: 0f b6 74 30 04               	movzx	esi, byte ptr [eax + esi + 0x4]
  554964: c1 e6 18                     	shl	esi, 0x18
  554967: 33 db                        	xor	ebx, ebx
  554969: 8a da                        	mov	bl, dl
  55496b: 0f b6 7c 18 05               	movzx	edi, byte ptr [eax + ebx + 0x5]
  554970: c1 e7 10                     	shl	edi, 0x10
  554973: 03 f7                        	add	esi, edi
  554975: 0f b6 7c 18 06               	movzx	edi, byte ptr [eax + ebx + 0x6]
  55497a: c1 e7 08                     	shl	edi, 0x8
  55497d: 03 f7                        	add	esi, edi
  55497f: 0f b6 44 18 07               	movzx	eax, byte ptr [eax + ebx + 0x7]
