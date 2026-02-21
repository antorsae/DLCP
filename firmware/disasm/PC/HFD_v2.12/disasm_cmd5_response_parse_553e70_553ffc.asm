
firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe:	file format coff-i386

Disassembly of section CODE:

00401000 <CODE>:
  553e70: d7                           	xlatb
  553e71: e8 d2 db 00 00               	call	0x561a48 <CODE+0x160a48>
  553e76: e9 ac 05 00 00               	jmp	0x554427 <CODE+0x153427>
  553e7b: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553e80: 8b 00                        	mov	eax, dword ptr [eax]
  553e82: b2 01                        	mov	dl, 0x1
  553e84: 8b 08                        	mov	ecx, dword ptr [eax]
  553e86: ff 51 64                     	call	dword ptr [ecx + 0x64]
  553e89: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553e8e: 8b 00                        	mov	eax, dword ptr [eax]
  553e90: b2 2a                        	mov	dl, 0x2a
  553e92: e8 5d 9e ef ff               	call	0x44dcf4 <CODE+0x4ccf4>
  553e97: a1 d8 96 56 00               	mov	eax, dword ptr [0x5696d8]
  553e9c: 8b 00                        	mov	eax, dword ptr [eax]
  553e9e: 33 d2                        	xor	edx, edx
  553ea0: e8 c7 63 f0 ff               	call	0x45a26c <CODE+0x5926c>
  553ea5: a1 20 9a 56 00               	mov	eax, dword ptr [0x569a20]
  553eaa: 8b 00                        	mov	eax, dword ptr [eax]
  553eac: e8 47 f3 ff ff               	call	0x5531f8 <CODE+0x1521f8>
  553eb1: e9 71 05 00 00               	jmp	0x554427 <CODE+0x153427>
  553eb6: 8a 47 06                     	mov	al, byte ptr [edi + 0x6]
  553eb9: 88 47 4d                     	mov	byte ptr [edi + 0x4d], al
  553ebc: 8a 47 53                     	mov	al, byte ptr [edi + 0x53]
  553ebf: 3c 03                        	cmp	al, 0x3
  553ec1: 74 04                        	je	0x553ec7 <CODE+0x152ec7>
  553ec3: 3c 01                        	cmp	al, 0x1
  553ec5: 75 06                        	jne	0x553ecd <CODE+0x152ecd>
  553ec7: 8a 47 07                     	mov	al, byte ptr [edi + 0x7]
  553eca: 88 47 4c                     	mov	byte ptr [edi + 0x4c], al
  553ecd: 8a 47 53                     	mov	al, byte ptr [edi + 0x53]
  553ed0: 3c 02                        	cmp	al, 0x2
  553ed2: 74 08                        	je	0x553edc <CODE+0x152edc>
  553ed4: 3c 05                        	cmp	al, 0x5
  553ed6: 74 04                        	je	0x553edc <CODE+0x152edc>
  553ed8: 3c 07                        	cmp	al, 0x7
  553eda: 75 06                        	jne	0x553ee2 <CODE+0x152ee2>
  553edc: 8a 47 08                     	mov	al, byte ptr [edi + 0x8]
  553edf: 88 47 4e                     	mov	byte ptr [edi + 0x4e], al
  553ee2: 8a 47 09                     	mov	al, byte ptr [edi + 0x9]
  553ee5: 88 47 58                     	mov	byte ptr [edi + 0x58], al
  553ee8: 8d 4f 48                     	lea	ecx, [edi + 0x48]
  553eeb: b2 06                        	mov	dl, 0x6
  553eed: 8b c7                        	mov	eax, edi
  553eef: e8 60 0a 00 00               	call	0x554954 <CODE+0x153954>
  553ef4: 8a 47 0e                     	mov	al, byte ptr [edi + 0xe]
  553ef7: 88 47 50                     	mov	byte ptr [edi + 0x50], al
  553efa: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  553eff: 8b 00                        	mov	eax, dword ptr [eax]
  553f01: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  553f05: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  553f0b: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f11: 8a 4f 0f                     	mov	cl, byte ptr [edi + 0xf]
  553f14: 88 8c c2 28 10 00 00         	mov	byte ptr [edx + 8*eax + 0x1028], cl
  553f1b: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  553f21: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f27: 8a 4f 10                     	mov	cl, byte ptr [edi + 0x10]
  553f2a: 88 8c c2 58 20 00 00         	mov	byte ptr [edx + 8*eax + 0x2058], cl
  553f31: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  553f37: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f3d: 8a 4f 11                     	mov	cl, byte ptr [edi + 0x11]
  553f40: 88 8c c2 88 30 00 00         	mov	byte ptr [edx + 8*eax + 0x3088], cl
  553f47: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  553f4d: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f53: 8a 4f 13                     	mov	cl, byte ptr [edi + 0x13]
  553f56: 88 8c c2 b8 40 00 00         	mov	byte ptr [edx + 8*eax + 0x40b8], cl
  553f5d: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  553f63: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f69: 8a 4f 14                     	mov	cl, byte ptr [edi + 0x14]
  553f6c: 88 8c c2 e8 50 00 00         	mov	byte ptr [edx + 8*eax + 0x50e8], cl
  553f73: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  553f79: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  553f7f: 8a 4f 15                     	mov	cl, byte ptr [edi + 0x15]
  553f82: 88 8c c2 18 61 00 00         	mov	byte ptr [edx + 8*eax + 0x6118], cl
  553f89: 8a 47 23                     	mov	al, byte ptr [edi + 0x23]
  553f8c: 3c fe                        	cmp	al, -0x2
  553f8e: 73 05                        	jae	0x553f95 <CODE+0x152f95>
  553f90: 88 47 70                     	mov	byte ptr [edi + 0x70], al
  553f93: eb 04                        	jmp	0x553f99 <CODE+0x152f99>
  553f95: c6 47 70 00                  	mov	byte ptr [edi + 0x70], 0x0
  553f99: 8a 47 17                     	mov	al, byte ptr [edi + 0x17]
  553f9c: 88 47 5e                     	mov	byte ptr [edi + 0x5e], al
  553f9f: 8a 47 18                     	mov	al, byte ptr [edi + 0x18]
  553fa2: 88 47 5f                     	mov	byte ptr [edi + 0x5f], al
  553fa5: 8a 47 19                     	mov	al, byte ptr [edi + 0x19]
  553fa8: 88 47 60                     	mov	byte ptr [edi + 0x60], al
  553fab: 8a 47 1a                     	mov	al, byte ptr [edi + 0x1a]
  553fae: 88 47 61                     	mov	byte ptr [edi + 0x61], al
  553fb1: 8a 47 1b                     	mov	al, byte ptr [edi + 0x1b]
  553fb4: 88 47 62                     	mov	byte ptr [edi + 0x62], al
  553fb7: 8a 47 1c                     	mov	al, byte ptr [edi + 0x1c]
  553fba: 88 47 63                     	mov	byte ptr [edi + 0x63], al
  553fbd: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  553fc2: 8b 00                        	mov	eax, dword ptr [eax]
  553fc4: e8 07 b5 00 00               	call	0x55f4d0 <CODE+0x15e4d0>
  553fc9: a1 8c 96 56 00               	mov	eax, dword ptr [0x56968c]
  553fce: 8b 00                        	mov	eax, dword ptr [eax]
  553fd0: 8b d7                        	mov	edx, edi
  553fd2: e8 d5 1d 00 00               	call	0x555dac <CODE+0x154dac>
  553fd7: a1 84 95 56 00               	mov	eax, dword ptr [0x569584]
  553fdc: 8b 00                        	mov	eax, dword ptr [eax]
  553fde: 83 b8 2c 03 00 00 00         	cmp	dword ptr [eax + 0x32c], 0x0
  553fe5: 0f 84 3c 04 00 00            	je	0x554427 <CODE+0x153427>
  553feb: a1 84 95 56 00               	mov	eax, dword ptr [0x569584]
  553ff0: 8b 00                        	mov	eax, dword ptr [eax]
  553ff2: e8 51 b9 ff ff               	call	0x54f948 <CODE+0x14e948>
  553ff7: e9 2b 04 00 00               	jmp	0x554427 <CODE+0x153427>
