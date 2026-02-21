
firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe:	file format coff-i386

Disassembly of section CODE:

00401000 <CODE>:
  5574a4: 53                           	push	ebx
  5574a5: 56                           	push	esi
  5574a6: 51                           	push	ecx
  5574a7: 8b d8                        	mov	ebx, eax
  5574a9: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5574ae: 8b 00                        	mov	eax, dword ptr [eax]
  5574b0: 8a 40 53                     	mov	al, byte ptr [eax + 0x53]
  5574b3: 3a 05 94 b4 57 00            	cmp	al, byte ptr [0x57b494]
  5574b9: 0f 95 c0                     	setne	al
  5574bc: 3c 01                        	cmp	al, 0x1
  5574be: 74 1b                        	je	0x5574db <CODE+0x1564db>
  5574c0: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5574c5: 8b 00                        	mov	eax, dword ptr [eax]
  5574c7: 8a 40 54                     	mov	al, byte ptr [eax + 0x54]
  5574ca: 3a 05 8f b4 57 00            	cmp	al, byte ptr [0x57b48f]
  5574d0: 0f 95 c0                     	setne	al
  5574d3: 3c 01                        	cmp	al, 0x1
  5574d5: 0f 85 91 10 00 00            	jne	0x55856c <CODE+0x15756c>
  5574db: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5574e0: 8b 00                        	mov	eax, dword ptr [eax]
  5574e2: 8b 80 3c 09 70 00            	mov	eax, dword ptr [eax + 0x70093c]
  5574e8: 85 c0                        	test	eax, eax
  5574ea: 74 31                        	je	0x55751d <CODE+0x15651d>
  5574ec: 8b 15 fc 98 56 00            	mov	edx, dword ptr [0x5698fc]
  5574f2: 33 d2                        	xor	edx, edx
  5574f4: e8 eb b6 ee ff               	call	0x442be4 <CODE+0x41be4>
  5574f9: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5574fe: 8b 00                        	mov	eax, dword ptr [eax]
  557500: 8b 80 f8 04 00 00            	mov	eax, dword ptr [eax + 0x4f8]
  557506: 8b 80 08 02 00 00            	mov	eax, dword ptr [eax + 0x208]
  55750c: ba 01 00 00 00               	mov	edx, 0x1
  557511: e8 a2 a5 ee ff               	call	0x441ab8 <CODE+0x40ab8>
  557516: 33 d2                        	xor	edx, edx
  557518: e8 f7 a4 ee ff               	call	0x441a14 <CODE+0x40a14>
  55751d: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  557522: 8b 00                        	mov	eax, dword ptr [eax]
  557524: 0f b6 40 53                  	movzx	eax, byte ptr [eax + 0x53]
  557528: 83 f8 07                     	cmp	eax, 0x7
  55752b: 0f 87 02 0e 00 00            	ja	0x558333 <CODE+0x157333>
  557531: ff 24 85 38 75 55 00         	jmp	dword ptr [4*eax + 0x557538]
  557538: 33 83 55 00 58 75            	xor	eax, dword ptr [ebx + 0x75580055]
  55753e: 55                           	push	ebp
  55753f: 00 79 7a                     	add	byte ptr [ecx + 0x7a], bh
  557542: 55                           	push	ebp
  557543: 00 ee                        	add	dh, ch
  557545: 7e 55                        	jle	0x55759c <CODE+0x15659c>
  557547: 00 33                        	add	byte ptr [ebx], dh
  557549: 83 55 00 79                  	adc	dword ptr [ebp], 0x79
  55754d: 7a 55                        	jp	0x5575a4 <CODE+0x1565a4>
  55754f: 00 33                        	add	byte ptr [ebx], dh
  557551: 83 55 00 79                  	adc	dword ptr [ebp], 0x79
  557555: 7a 55                        	jp	0x5575ac <CODE+0x1565ac>
  557557: 00 a1 80 94 56 00            	add	byte ptr [ecx + 0x569480], ah
  55755d: 8b 00                        	mov	eax, dword ptr [eax]
  55755f: 8a 40 7b                     	mov	al, byte ptr [eax + 0x7b]
  557562: 88 04 24                     	mov	byte ptr [esp], al
  557565: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55756a: 8b 00                        	mov	eax, dword ptr [eax]
  55756c: 8b 80 1c 03 00 00            	mov	eax, dword ptr [eax + 0x31c]
  557572: 8b 80 28 02 00 00            	mov	eax, dword ptr [eax + 0x228]
  557578: 8b 10                        	mov	edx, dword ptr [eax]
  55757a: ff 52 44                     	call	dword ptr [edx + 0x44]
  55757d: 0f b6 34 24                  	movzx	esi, byte ptr [esp]
  557581: 4e                           	dec	esi
  557582: 85 f6                        	test	esi, esi
  557584: 7c 1e                        	jl	0x5575a4 <CODE+0x1565a4>
  557586: 46                           	inc	esi
  557587: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  55758c: 8b 00                        	mov	eax, dword ptr [eax]
  55758e: 8b 80 1c 03 00 00            	mov	eax, dword ptr [eax + 0x31c]
  557594: 8b 80 28 02 00 00            	mov	eax, dword ptr [eax + 0x228]
  55759a: 33 d2                        	xor	edx, edx
  55759c: 8b 08                        	mov	ecx, dword ptr [eax]
  55759e: ff 51 38                     	call	dword ptr [ecx + 0x38]
  5575a1: 4e                           	dec	esi
  5575a2: 75 e3                        	jne	0x557587 <CODE+0x156587>
  5575a4: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5575a9: 8b 00                        	mov	eax, dword ptr [eax]
  5575ab: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  5575af: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  5575b5: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  5575bb: 8b 0d 80 94 56 00            	mov	ecx, dword ptr [0x569480]
  5575c1: 8b 09                        	mov	ecx, dword ptr [ecx]
  5575c3: 0f b6 89 82 00 00 00         	movzx	ecx, byte ptr [ecx + 0x82]
  5575ca: 69 c9 e8 03 00 00            	imul	ecx, ecx, 0x3e8
  5575d0: 89 8c c2 2c 10 00 00         	mov	dword ptr [edx + 8*eax + 0x102c], ecx
  5575d7: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  5575dd: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  5575e3: 8b 0d 80 94 56 00            	mov	ecx, dword ptr [0x569480]
  5575e9: 8b 09                        	mov	ecx, dword ptr [ecx]
  5575eb: 0f b6 89 83 00 00 00         	movzx	ecx, byte ptr [ecx + 0x83]
  5575f2: 69 c9 e8 03 00 00            	imul	ecx, ecx, 0x3e8
  5575f8: 89 8c c2 5c 20 00 00         	mov	dword ptr [edx + 8*eax + 0x205c], ecx
  5575ff: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  557605: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  55760b: 33 c9                        	xor	ecx, ecx
  55760d: 89 8c c2 8c 30 00 00         	mov	dword ptr [edx + 8*eax + 0x308c], ecx
  557614: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  55761a: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  557620: 8b 0d 80 94 56 00            	mov	ecx, dword ptr [0x569480]
  557626: 8b 09                        	mov	ecx, dword ptr [ecx]
  557628: 0f b6 49 7c                  	movzx	ecx, byte ptr [ecx + 0x7c]
  55762c: 89 4c c2 18                  	mov	dword ptr [edx + 8*eax + 0x18], ecx
  557630: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  557636: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  55763c: 8b 0d 80 94 56 00            	mov	ecx, dword ptr [0x569480]
  557642: 8b 09                        	mov	ecx, dword ptr [ecx]
  557644: 0f b6 49 7d                  	movzx	ecx, byte ptr [ecx + 0x7d]
  557648: 89 8c c2 48 10 00 00         	mov	dword ptr [edx + 8*eax + 0x1048], ecx
  55764f: 8b 15 80 94 56 00            	mov	edx, dword ptr [0x569480]
  557655: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  55765b: 8b 0d 80 94 56 00            	mov	ecx, dword ptr [0x569480]
  557661: 8b 09                        	mov	ecx, dword ptr [ecx]
  557663: 0f b6 49 7e                  	movzx	ecx, byte ptr [ecx + 0x7e]
  557667: 89 8c c2 78 20 00 00         	mov	dword ptr [edx + 8*eax + 0x2078], ecx
  55766e: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  557673: 8b 00                        	mov	eax, dword ptr [eax]
  557675: 8b 80 1c 03 00 00            	mov	eax, dword ptr [eax + 0x31c]
  55767b: 8b 80 28 02 00 00            	mov	eax, dword ptr [eax + 0x228]
  557681: b9 84 85 55 00               	mov	ecx, 0x558584
  557686: 33 d2                        	xor	edx, edx
  557688: 8b 30                        	mov	esi, dword ptr [eax]
  55768a: ff 56 20                     	call	dword ptr [esi + 0x20]
  55768d: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  557692: 8b 00                        	mov	eax, dword ptr [eax]
  557694: 8b 80 1c 03 00 00            	mov	eax, dword ptr [eax + 0x31c]
  55769a: 8b 80 28 02 00 00            	mov	eax, dword ptr [eax + 0x228]
  5576a0: b9 a0 85 55 00               	mov	ecx, 0x5585a0
  5576a5: ba 01 00 00 00               	mov	edx, 0x1
  5576aa: 8b 30                        	mov	esi, dword ptr [eax]
  5576ac: ff 56 20                     	call	dword ptr [esi + 0x20]
  5576af: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  5576b4: 8b 00                        	mov	eax, dword ptr [eax]
  5576b6: 8b 80 1c 03 00 00            	mov	eax, dword ptr [eax + 0x31c]
  5576bc: 8b 80 28 02 00 00            	mov	eax, dword ptr [eax + 0x228]
  5576c2: b9 b8 85 55 00               	mov	ecx, 0x5585b8
  5576c7: ba 02 00 00 00               	mov	edx, 0x2
  5576cc: 8b 30                        	mov	esi, dword ptr [eax]
  5576ce: ff 56 20                     	call	dword ptr [esi + 0x20]
  5576d1: a1 80 94 56 00               	mov	eax, dword ptr [0x569480]
  5576d6: 8b 00                        	mov	eax, dword ptr [eax]
  5576d8: 0f b6 40 58                  	movzx	eax, byte ptr [eax + 0x58]
  5576dc: 69 c0 24 0c 00 00            	imul	eax, eax, 0xc24
  5576e2: 8b 15 88 96 56 00            	mov	edx, dword ptr [0x569688]
  5576e8: c6 84 c2 71 20 00 00 00      	mov	byte ptr [edx + 8*eax + 0x2071], 0x0
  5576f0: 8b 83 fc 02 00 00            	mov	eax, dword ptr [ebx + 0x2fc]
  5576f6: e8 71 30 f0 ff               	call	0x45a76c <CODE+0x5976c>
  5576fb: 8b 83 0c 03 00 00            	mov	eax, dword ptr [ebx + 0x30c]
  557701: e8 66 30 f0 ff               	call	0x45a76c <CODE+0x5976c>
  557706: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  55770c: e8 5b 30 f0 ff               	call	0x45a76c <CODE+0x5976c>
  557711: b2 01                        	mov	dl, 0x1
  557713: 8b 83 1c 03 00 00            	mov	eax, dword ptr [ebx + 0x31c]
  557719: 8b 08                        	mov	ecx, dword ptr [eax]
  55771b: ff 51 64                     	call	dword ptr [ecx + 0x64]
  55771e: 8b 83 68 03 00 00            	mov	eax, dword ptr [ebx + 0x368]
  557724: e8 43 30 f0 ff               	call	0x45a76c <CODE+0x5976c>
  557729: b2 01                        	mov	dl, 0x1
  55772b: 8b 83 68 03 00 00            	mov	eax, dword ptr [ebx + 0x368]
  557731: 8b 08                        	mov	ecx, dword ptr [eax]
  557733: ff 51 64                     	call	dword ptr [ecx + 0x64]
  557736: 8b 83 20 03 00 00            	mov	eax, dword ptr [ebx + 0x320]
  55773c: e8 2b 30 f0 ff               	call	0x45a76c <CODE+0x5976c>
  557741: 8b 93 20 03 00 00            	mov	edx, dword ptr [ebx + 0x320]
  557747: 8b c3                        	mov	eax, ebx
  557749: e8 0e fd ff ff               	call	0x55745c <CODE+0x15645c>
  55774e: a1 fc 98 56 00               	mov	eax, dword ptr [0x5698fc]
  557753: 8b 00                        	mov	eax, dword ptr [eax]
  557755: 8b 80 44 05 00 00            	mov	eax, dword ptr [eax + 0x544]
  55775b: 33 d2                        	xor	edx, edx
  55775d: e8 ae 4f f1 ff               	call	0x46c710 <CODE+0x6b710>
  557762: 8b 83 6c 03 00 00            	mov	eax, dword ptr [ebx + 0x36c]
  557768: e8 f7 2f f0 ff               	call	0x45a764 <CODE+0x59764>
  55776d: 8b 83 70 03 00 00            	mov	eax, dword ptr [ebx + 0x370]
  557773: e8 ec 2f f0 ff               	call	0x45a764 <CODE+0x59764>
  557778: 8b 83 74 03 00 00            	mov	eax, dword ptr [ebx + 0x374]
  55777e: e8 e1 2f f0 ff               	call	0x45a764 <CODE+0x59764>
