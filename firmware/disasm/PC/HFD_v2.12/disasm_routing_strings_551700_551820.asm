
firmware/stock/PC/HFD_v2.12/Hypex Filter Design 2.12/Hypex Filter Design V2.12.exe:	file format coff-i386

Disassembly of section CODE:

00401000 <CODE>:
  551700: 6e                           	outsb	dx, byte ptr [esi]
  551701: 65 6c                        	insb	byte ptr es:[edi], dx
  551703: 20 31                        	and	byte ptr [ecx], dh
  551705: 00 00                        	add	byte ptr [eax], al
  551707: 00 ff                        	add	bh, bh
  551709: ff ff                        	<unknown>
  55170b: ff 04 00                     	inc	dword ptr [eax + eax]
  55170e: 00 00                        	add	byte ptr [eax], al
  551710: 4c                           	dec	esp
  551711: 65 66 74 00                  	je	0x551715 <CODE+0x150715>
  551715: 00 00                        	add	byte ptr [eax], al
  551717: 00 ff                        	add	bh, bh
  551719: ff ff                        	<unknown>
  55171b: ff 05 00 00 00 52            	inc	dword ptr [0x52000000]
  551721: 69 67 68 74 00 00 00         	imul	esp, dword ptr [edi + 0x68], 0x74
  551728: ff ff                        	<unknown>
  55172a: ff ff                        	<unknown>
  55172c: 07                           	pop	es
  55172d: 00 00                        	add	byte ptr [eax], al
  55172f: 00 4c 2b 52                  	add	byte ptr [ebx + ebp + 0x52], cl
  551733: 2f                           	das
  551734: 4d                           	dec	ebp
  551735: 69 64 00 ff ff ff ff 08      	imul	esp, dword ptr [eax + eax - 0x1], 0x8ffffff
  55173d: 00 00                        	add	byte ptr [eax], al
  55173f: 00 4c 2d 52                  	add	byte ptr [ebp + ebp + 0x52], cl
  551743: 2f                           	das
  551744: 53                           	push	ebx
  551745: 69 64 65 00 00 00 00 ff      	imul	esp, dword ptr [ebp + 2*eiz], 0xff000000
  55174d: ff ff                        	<unknown>
  55174f: ff 09                        	dec	dword ptr [ecx]
  551751: 00 00                        	add	byte ptr [eax], al
  551753: 00 43 68                     	add	byte ptr [ebx + 0x68], al
  551756: 61                           	popal
  551757: 6e                           	outsb	dx, byte ptr [esi]
  551758: 6e                           	outsb	dx, byte ptr [esi]
  551759: 65 6c                        	insb	byte ptr es:[edi], dx
  55175b: 20 32                        	and	byte ptr [edx], dh
  55175d: 00 00                        	add	byte ptr [eax], al
  55175f: 00 ff                        	add	bh, bh
  551761: ff ff                        	<unknown>
  551763: ff 09                        	dec	dword ptr [ecx]
  551765: 00 00                        	add	byte ptr [eax], al
  551767: 00 43 68                     	add	byte ptr [ebx + 0x68], al
  55176a: 61                           	popal
  55176b: 6e                           	outsb	dx, byte ptr [esi]
  55176c: 6e                           	outsb	dx, byte ptr [esi]
  55176d: 65 6c                        	insb	byte ptr es:[edi], dx
  55176f: 20 33                        	and	byte ptr [ebx], dh
  551771: 00 00                        	add	byte ptr [eax], al
  551773: 00 ff                        	add	bh, bh
  551775: ff ff                        	<unknown>
  551777: ff 09                        	dec	dword ptr [ecx]
  551779: 00 00                        	add	byte ptr [eax], al
  55177b: 00 43 68                     	add	byte ptr [ebx + 0x68], al
  55177e: 61                           	popal
  55177f: 6e                           	outsb	dx, byte ptr [esi]
  551780: 6e                           	outsb	dx, byte ptr [esi]
  551781: 65 6c                        	insb	byte ptr es:[edi], dx
  551783: 20 34 00                     	and	byte ptr [eax + eax], dh
  551786: 00 00                        	add	byte ptr [eax], al
  551788: ff ff                        	<unknown>
  55178a: ff ff                        	<unknown>
  55178c: 09 00                        	or	dword ptr [eax], eax
  55178e: 00 00                        	add	byte ptr [eax], al
  551790: 43                           	inc	ebx
  551791: 68 61 6e 6e 65               	push	0x656e6e61
  551796: 6c                           	insb	byte ptr es:[edi], dx
  551797: 20 35 00 00 00 ff            	and	byte ptr [-0x1000000], dh
  55179d: ff ff                        	<unknown>
  55179f: ff 09                        	dec	dword ptr [ecx]
  5517a1: 00 00                        	add	byte ptr [eax], al
  5517a3: 00 43 68                     	add	byte ptr [ebx + 0x68], al
  5517a6: 61                           	popal
  5517a7: 6e                           	outsb	dx, byte ptr [esi]
  5517a8: 6e                           	outsb	dx, byte ptr [esi]
  5517a9: 65 6c                        	insb	byte ptr es:[edi], dx
  5517ab: 20 36                        	and	byte ptr [esi], dh
  5517ad: 00 00                        	add	byte ptr [eax], al
  5517af: 00 ff                        	add	bh, bh
  5517b1: ff ff                        	<unknown>
  5517b3: ff 0c 00                     	dec	dword ptr [eax + eax]
  5517b6: 00 00                        	add	byte ptr [eax], al
  5517b8: 47                           	inc	edi
  5517b9: 61                           	popal
  5517ba: 69 6e 20 6c 6f 77 65         	imul	ebp, dword ptr [esi + 0x20], 0x65776f6c
  5517c1: 72 65                        	jb	0x551828 <CODE+0x150828>
  5517c3: 64 00 00                     	add	byte ptr fs:[eax], al
  5517c6: 00 00                        	add	byte ptr [eax], al
  5517c8: ff ff                        	<unknown>
  5517ca: ff ff                        	<unknown>
  5517cc: 46                           	inc	esi
  5517cd: 00 00                        	add	byte ptr [eax], al
  5517cf: 00 53 65                     	add	byte ptr [ebx + 0x65], dl
  5517d2: 6c                           	insb	byte ptr es:[edi], dx
  5517d3: 65 63 74 20 69               	arpl	word ptr gs:[eax + eiz + 0x69], si
  5517d8: 66 20 67 61                  	and	byte ptr [edi + 0x61], ah
  5517dc: 69 6e 20 66 6f 72 20         	imul	ebp, dword ptr [esi + 0x20], 0x20726f66
  5517e3: 74 68                        	je	0x55184d <CODE+0x15084d>
  5517e5: 65 20 68 69                  	and	byte ptr gs:[eax + 0x69], ch
  5517e9: 67 68 20 63 68 61            	addr16		push	0x61686320
  5517ef: 6e                           	outsb	dx, byte ptr [esi]
  5517f0: 6e                           	outsb	dx, byte ptr [esi]
  5517f1: 65 6c                        	insb	byte ptr es:[edi], dx
  5517f3: 20 69 73                     	and	byte ptr [ecx + 0x73], ch
  5517f6: 20 6c 6f 77                  	and	byte ptr [edi + 2*ebp + 0x77], ch
  5517fa: 65 72 65                     	jb	0x551862 <CODE+0x150862>
  5517fd: 64 20 62 79                  	and	byte ptr fs:[edx + 0x79], ah
  551801: 20 72 65                     	and	byte ptr [edx + 0x65], dh
  551804: 6d                           	insd	dword ptr es:[edi], dx
  551805: 6f                           	outsd	dx, dword ptr [esi]
  551806: 76 69                        	jbe	0x551871 <CODE+0x150871>
  551808: 6e                           	outsb	dx, byte ptr [esi]
  551809: 67 20 74 68                  	and	byte ptr [si + 0x68], dh
  55180d: 65 20 6a 75                  	and	byte ptr gs:[edx + 0x75], ch
  551811: 6d                           	insd	dword ptr es:[edi], dx
  551812: 70 65                        	jo	0x551879 <CODE+0x150879>
  551814: 72 73                        	jb	0x551889 <CODE+0x150889>
  551816: 00 00                        	add	byte ptr [eax], al
  551818: ff ff                        	<unknown>
  55181a: ff ff                        	<unknown>
  55181c: 0b 00                        	or	eax, dword ptr [eax]
  55181e: 00 00                        	add	byte ptr [eax], al
