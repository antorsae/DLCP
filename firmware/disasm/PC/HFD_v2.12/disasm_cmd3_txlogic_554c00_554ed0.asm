
firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe:	file format coff-i386

Disassembly of section CODE:

00401000 <CODE>:
  554c00: 7b 3b                        	jnp	0x554c3d <CODE+0x153c3d>
  554c02: c2 7d 1c                     	ret	0x1c7d
  554c05: 8a 14 24                     	mov	dl, byte ptr [esp]
  554c08: 42                           	inc	edx
  554c09: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554c0e: 8b 00                        	mov	eax, dword ptr [eax]
  554c10: 8a 4f 4f                     	mov	cl, byte ptr [edi + 0x4f]
  554c13: e8 38 03 00 00               	call	0x554f50 <CODE+0x153f50>
  554c18: c6 47 26 00                  	mov	byte ptr [edi + 0x26], 0x0
  554c1c: e9 9f 00 00 00               	jmp	0x554cc0 <CODE+0x153cc0>
  554c21: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554c26: 8b 00                        	mov	eax, dword ptr [eax]
  554c28: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  554c2e: 8b 80 08 02 00 00            	mov	eax, dword ptr [eax + 0x208]
  554c34: ba 01 00 00 00               	mov	edx, 0x1
  554c39: e8 7a ce ee ff               	call	0x441ab8 <CODE+0x40ab8>
  554c3e: ba 58 4e 55 00               	mov	edx, 0x554e58
  554c43: e8 cc cd ee ff               	call	0x441a14 <CODE+0x40a14>
  554c48: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554c4d: 8b 00                        	mov	eax, dword ptr [eax]
  554c4f: c6 80 5c 09 70 00 09         	mov	byte ptr [eax + 0x70095c], 0x9
  554c56: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  554c5b: 8b 00                        	mov	eax, dword ptr [eax]
  554c5d: 80 78 53 01                  	cmp	byte ptr [eax + 0x53], 0x1
  554c61: 0f 94 c0                     	sete	al
  554c64: 3c 01                        	cmp	al, 0x1
  554c66: 75 36                        	jne	0x554c9e <CODE+0x153c9e>
  554c68: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  554c6d: 8b 00                        	mov	eax, dword ptr [eax]
  554c6f: 80 78 54 02                  	cmp	byte ptr [eax + 0x54], 0x2
  554c73: 0f 97 c0                     	seta	al
  554c76: 3c 01                        	cmp	al, 0x1
  554c78: 74 36                        	je	0x554cb0 <CODE+0x153cb0>
  554c7a: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  554c7f: 8b 00                        	mov	eax, dword ptr [eax]
  554c81: 80 78 54 02                  	cmp	byte ptr [eax + 0x54], 0x2
  554c85: 0f 94 c0                     	sete	al
  554c88: 3c 01                        	cmp	al, 0x1
  554c8a: 75 12                        	jne	0x554c9e <CODE+0x153c9e>
  554c8c: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  554c91: 8b 00                        	mov	eax, dword ptr [eax]
  554c93: 80 78 55 05                  	cmp	byte ptr [eax + 0x55], 0x5
  554c97: 0f 97 c0                     	seta	al
  554c9a: 3c 01                        	cmp	al, 0x1
  554c9c: 74 12                        	je	0x554cb0 <CODE+0x153cb0>
  554c9e: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  554ca3: 8b 00                        	mov	eax, dword ptr [eax]
  554ca5: 80 78 53 01                  	cmp	byte ptr [eax + 0x53], 0x1
  554ca9: 0f 95 c0                     	setne	al
  554cac: 3c 01                        	cmp	al, 0x1
  554cae: 75 10                        	jne	0x554cc0 <CODE+0x153cc0>
  554cb0: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554cb5: 8b 00                        	mov	eax, dword ptr [eax]
  554cb7: b1 09                        	mov	cl, 0x9
  554cb9: b2 03                        	mov	dl, 0x3
  554cbb: e8 90 02 00 00               	call	0x554f50 <CODE+0x153f50>
  554cc0: c6 05 58 b3 57 00 00         	mov	byte ptr [0x57b358], 0x0
  554cc7: e9 5d 01 00 00               	jmp	0x554e29 <CODE+0x153e29>
  554ccc: 8a 47 53                     	mov	al, byte ptr [edi + 0x53]
  554ccf: 3c 02                        	cmp	al, 0x2
  554cd1: 74 08                        	je	0x554cdb <CODE+0x153cdb>
  554cd3: 3c 05                        	cmp	al, 0x5
  554cd5: 74 04                        	je	0x554cdb <CODE+0x153cdb>
  554cd7: 3c 07                        	cmp	al, 0x7
  554cd9: 75 7e                        	jne	0x554d59 <CODE+0x153d59>
  554cdb: 33 c0                        	xor	eax, eax
  554cdd: 8a 04 24                     	mov	al, byte ptr [esp]
  554ce0: 83 e8 06                     	sub	eax, 0x6
  554ce3: 33 d2                        	xor	edx, edx
  554ce5: 8a 57 7b                     	mov	dl, byte ptr [edi + 0x7b]
  554ce8: 3b c2                        	cmp	eax, edx
  554cea: 7d 1c                        	jge	0x554d08 <CODE+0x153d08>
  554cec: 8a 14 24                     	mov	dl, byte ptr [esp]
  554cef: 42                           	inc	edx
  554cf0: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554cf5: 8b 00                        	mov	eax, dword ptr [eax]
  554cf7: 8a 4f 4f                     	mov	cl, byte ptr [edi + 0x4f]
  554cfa: e8 51 02 00 00               	call	0x554f50 <CODE+0x153f50>
  554cff: c6 47 26 00                  	mov	byte ptr [edi + 0x26], 0x0
  554d03: e9 21 01 00 00               	jmp	0x554e29 <CODE+0x153e29>
  554d08: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554d0d: 8b 00                        	mov	eax, dword ptr [eax]
  554d0f: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  554d15: 8b 80 08 02 00 00            	mov	eax, dword ptr [eax + 0x208]
  554d1b: ba 01 00 00 00               	mov	edx, 0x1
  554d20: e8 93 cd ee ff               	call	0x441ab8 <CODE+0x40ab8>
  554d25: ba 58 4e 55 00               	mov	edx, 0x554e58
  554d2a: e8 e5 cc ee ff               	call	0x441a14 <CODE+0x40a14>
  554d2f: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554d34: 8b 00                        	mov	eax, dword ptr [eax]
  554d36: c6 80 5c 09 70 00 09         	mov	byte ptr [eax + 0x70095c], 0x9
  554d3d: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554d42: 8b 00                        	mov	eax, dword ptr [eax]
  554d44: b1 09                        	mov	cl, 0x9
  554d46: b2 03                        	mov	dl, 0x3
  554d48: e8 03 02 00 00               	call	0x554f50 <CODE+0x153f50>
  554d4d: c6 05 58 b3 57 00 00         	mov	byte ptr [0x57b358], 0x0
  554d54: e9 d0 00 00 00               	jmp	0x554e29 <CODE+0x153e29>
  554d59: 3c 04                        	cmp	al, 0x4
  554d5b: 75 52                        	jne	0x554daf <CODE+0x153daf>
  554d5d: 33 c0                        	xor	eax, eax
  554d5f: 8a 04 24                     	mov	al, byte ptr [esp]
  554d62: 83 e8 07                     	sub	eax, 0x7
  554d65: 83 f8 06                     	cmp	eax, 0x6
  554d68: 7d 1c                        	jge	0x554d86 <CODE+0x153d86>
  554d6a: 8a 14 24                     	mov	dl, byte ptr [esp]
  554d6d: 42                           	inc	edx
  554d6e: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554d73: 8b 00                        	mov	eax, dword ptr [eax]
  554d75: 8a 4f 4f                     	mov	cl, byte ptr [edi + 0x4f]
  554d78: e8 d3 01 00 00               	call	0x554f50 <CODE+0x153f50>
  554d7d: c6 47 26 00                  	mov	byte ptr [edi + 0x26], 0x0
  554d81: e9 a3 00 00 00               	jmp	0x554e29 <CODE+0x153e29>
  554d86: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554d8b: 8b 00                        	mov	eax, dword ptr [eax]
  554d8d: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  554d93: 8b 80 08 02 00 00            	mov	eax, dword ptr [eax + 0x208]
  554d99: ba 01 00 00 00               	mov	edx, 0x1
  554d9e: e8 15 cd ee ff               	call	0x441ab8 <CODE+0x40ab8>
  554da3: ba 58 4e 55 00               	mov	edx, 0x554e58
  554da8: e8 67 cc ee ff               	call	0x441a14 <CODE+0x40a14>
  554dad: eb 7a                        	jmp	0x554e29 <CODE+0x153e29>
  554daf: 3c 03                        	cmp	al, 0x3
  554db1: 75 76                        	jne	0x554e29 <CODE+0x153e29>
  554db3: 33 c0                        	xor	eax, eax
  554db5: 8a 04 24                     	mov	al, byte ptr [esp]
  554db8: 83 e8 06                     	sub	eax, 0x6
  554dbb: 33 d2                        	xor	edx, edx
  554dbd: 8a 57 7b                     	mov	dl, byte ptr [edi + 0x7b]
  554dc0: 3b c2                        	cmp	eax, edx
  554dc2: 7d 19                        	jge	0x554ddd <CODE+0x153ddd>
  554dc4: 8a 14 24                     	mov	dl, byte ptr [esp]
  554dc7: 42                           	inc	edx
  554dc8: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554dcd: 8b 00                        	mov	eax, dword ptr [eax]
  554dcf: 8a 4f 4f                     	mov	cl, byte ptr [edi + 0x4f]
  554dd2: e8 79 01 00 00               	call	0x554f50 <CODE+0x153f50>
  554dd7: c6 47 26 00                  	mov	byte ptr [edi + 0x26], 0x0
  554ddb: eb 4c                        	jmp	0x554e29 <CODE+0x153e29>
  554ddd: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554de2: 8b 00                        	mov	eax, dword ptr [eax]
  554de4: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  554dea: 8b 80 08 02 00 00            	mov	eax, dword ptr [eax + 0x208]
  554df0: ba 01 00 00 00               	mov	edx, 0x1
  554df5: e8 be cc ee ff               	call	0x441ab8 <CODE+0x40ab8>
  554dfa: ba 58 4e 55 00               	mov	edx, 0x554e58
  554dff: e8 10 cc ee ff               	call	0x441a14 <CODE+0x40a14>
  554e04: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  554e09: 8b 00                        	mov	eax, dword ptr [eax]
  554e0b: c6 80 5c 09 70 00 09         	mov	byte ptr [eax + 0x70095c], 0x9
  554e12: a1 64 97 56 00               	mov	eax, dword ptr [0x569764]
  554e17: 8b 00                        	mov	eax, dword ptr [eax]
  554e19: b1 09                        	mov	cl, 0x9
  554e1b: b2 03                        	mov	dl, 0x3
  554e1d: e8 2e 01 00 00               	call	0x554f50 <CODE+0x153f50>
  554e22: c6 05 58 b3 57 00 00         	mov	byte ptr [0x57b358], 0x0
  554e29: 88 5f 27                     	mov	byte ptr [edi + 0x27], bl
  554e2c: 59                           	pop	ecx
  554e2d: 5a                           	pop	edx
  554e2e: 5d                           	pop	ebp
  554e2f: 5f                           	pop	edi
  554e30: 5e                           	pop	esi
  554e31: 5b                           	pop	ebx
  554e32: c3                           	ret
  554e33: 00 9a 99 99 99 99            	add	byte ptr [edx - 0x66666667], bl
  554e39: 99                           	cdq
  554e3a: 99                           	cdq
  554e3b: a9 02 40 00 00               	test	eax, 0x4002
  554e40: 66 66 66 66 66 66 66 aa      	stosb	byte ptr es:[edi], al
  554e48: 03 40 00                     	add	eax, dword ptr [eax]
  554e4b: 00 00                        	add	byte ptr [eax], al
  554e4d: 00 00                        	add	byte ptr [eax], al
  554e4f: 4b                           	dec	ebx
  554e50: ff ff                        	<unknown>
  554e52: ff ff                        	<unknown>
  554e54: 16                           	push	ss
  554e55: 00 00                        	add	byte ptr [eax], al
  554e57: 00 46 69                     	add	byte ptr [esi + 0x69], al
  554e5a: 6c                           	insb	byte ptr es:[edi], dx
  554e5b: 74 65                        	je	0x554ec2 <CODE+0x153ec2>
  554e5d: 72 20                        	jb	0x554e7f <CODE+0x153e7f>
  554e5f: 75 70                        	jne	0x554ed1 <CODE+0x153ed1>
  554e61: 64 61                        	popal
  554e63: 74 65                        	je	0x554eca <CODE+0x153eca>
  554e65: 20 63 6f                     	and	byte ptr [ebx + 0x6f], ah
  554e68: 6d                           	insd	dword ptr es:[edi], dx
  554e69: 70 6c                        	jo	0x554ed7 <CODE+0x153ed7>
  554e6b: 65 74 65                     	je	0x554ed3 <CODE+0x153ed3>
  554e6e: 00 00                        	add	byte ptr [eax], al
  554e70: 53                           	push	ebx
  554e71: 56                           	push	esi
  554e72: 8b d9                        	mov	ebx, ecx
  554e74: c1 eb 18                     	shr	ebx, 0x18
  554e77: 8b f2                        	mov	esi, edx
  554e79: 81 e6 ff 00 00 00            	and	esi, 0xff
  554e7f: 88 5c 30 25                  	mov	byte ptr [eax + esi + 0x25], bl
  554e83: 8b d9                        	mov	ebx, ecx
  554e85: c1 eb 10                     	shr	ebx, 0x10
  554e88: 8b f2                        	mov	esi, edx
  554e8a: 81 e6 ff 00 00 00            	and	esi, 0xff
  554e90: 88 5c 30 26                  	mov	byte ptr [eax + esi + 0x26], bl
  554e94: 8b d9                        	mov	ebx, ecx
  554e96: c1 eb 08                     	shr	ebx, 0x8
  554e99: 88 5c 30 27                  	mov	byte ptr [eax + esi + 0x27], bl
  554e9d: 88 4c 30 28                  	mov	byte ptr [eax + esi + 0x28], cl
  554ea1: 5e                           	pop	esi
  554ea2: 5b                           	pop	ebx
  554ea3: c3                           	ret
  554ea4: 53                           	push	ebx
  554ea5: 56                           	push	esi
  554ea6: be 6c b3 57 00               	mov	esi, 0x57b36c
  554eab: 8b c2                        	mov	eax, edx
  554ead: b2 08                        	mov	dl, 0x8
  554eaf: 0f b7 0e                     	movzx	ecx, word ptr [esi]
  554eb2: c1 e9 0d                     	shr	ecx, 0xd
  554eb5: f6 c1 01                     	test	cl, 0x1
  554eb8: 0f 95 c1                     	setne	cl
  554ebb: 66 d1 26                     	shl	word ptr [esi]
  554ebe: 8b d8                        	mov	ebx, eax
  554ec0: 80 e3 01                     	and	bl, 0x1
  554ec3: 81 e3 ff 00 00 00            	and	ebx, 0xff
  554ec9: 66 01 1e                     	add	word ptr [esi], bx
  554ecc: 25 ff 00 00 00               	and	eax, 0xff
