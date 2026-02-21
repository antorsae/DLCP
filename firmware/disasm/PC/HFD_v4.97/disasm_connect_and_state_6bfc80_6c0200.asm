
firmware/stock/PC/HFD_v4.97/Resources/HFD.exe:	file format coff-i386

Disassembly of section .text:

00475518 <TMethodImplementationIntercept>:
  6bfc80: 6c                           	insb	%dx, %es:(%edi)
  6bfc81: 66 02 00                     	addb	(%eax), %al
  6bfc84: 02 00                        	addb	(%eax), %al
  6bfc86: 00 00                        	addb	%al, (%eax)
  6bfc88: 8c fc                        	<unknown>
  6bfc8a: 6b 00 07                     	imull	$0x7, (%eax), %eax
  6bfc8d: 21 54 57 69                  	andl	%edx, 0x69(%edi,%edx,2)
  6bfc91: 6e                           	outsb	(%esi), %dx
  6bfc92: 47                           	incl	%edi
  6bfc93: 65 73 74                     	jae	0x6bfd0a <TMethodImplementationIntercept+0x24a7f2>
  6bfc96: 75 72                        	jne	0x6bfd0a <TMethodImplementationIntercept+0x24a7f2>
  6bfc98: 65 45                        	incl	%ebp
  6bfc9a: 6e                           	outsb	(%esi), %dx
  6bfc9b: 67 69 6e 65 2e 54 52 65      	imull	$0x6552542e, 0x65(%bp), %ebp # imm = 0x6552542E
  6bfca3: 61                           	popal
  6bfca4: 6c                           	insb	%dx, %es:(%edi)
  6bfca5: 54                           	pushl	%esp
  6bfca6: 69 6d 65 53 74 79 6c         	imull	$0x6c797453, 0x65(%ebp), %ebp # imm = 0x6C797453
  6bfcad: 75 73                        	jne	0x6bfd22 <TMethodImplementationIntercept+0x24a80a>
  6bfcaf: c4 f1 6b                     	<unknown>
  6bfcb2: 00 18                        	addb	%bl, (%eax)
  6bfcb4: 29 40 00                     	subl	%eax, (%eax)
  6bfcb7: 00 00                        	addb	%al, (%eax)
  6bfcb9: 10 46 4d                     	adcb	%al, 0x4d(%esi)
  6bfcbc: 58                           	popl	%eax
  6bfcbd: 2e 47                        	incl	%edi
  6bfcbf: 65 73 74                     	jae	0x6bfd36 <TMethodImplementationIntercept+0x24a81e>
  6bfcc2: 75 72                        	jne	0x6bfd36 <TMethodImplementationIntercept+0x24a81e>
  6bfcc4: 65 73 2e                     	jae	0x6bfcf5 <TMethodImplementationIntercept+0x24a7dd>
  6bfcc7: 57                           	pushl	%edi
  6bfcc8: 69 6e 00 00 02 00 02         	imull	$0x2000200, (%esi), %ebp # imm = 0x2000200
  6bfccf: e0 fc                        	loopne	0x6bfccd <TMethodImplementationIntercept+0x24a7b5>
  6bfcd1: 6b 00 02                     	imull	$0x2, (%eax), %eax
  6bfcd4: 00 02                        	addb	%al, (%edx)
  6bfcd6: 02 fd                        	addb	%ch, %bh
  6bfcd8: 6b 00 02                     	imull	$0x2, (%eax), %eax
  6bfcdb: 00 02                        	addb	%al, (%edx)
  6bfcdd: 00 00                        	addb	%al, (%eax)
  6bfcdf: 00 00                        	addb	%al, (%eax)
  6bfce1: 10 40 00                     	adcb	%al, (%eax)
  6bfce4: 14 00                        	adcb	$0x0, %al
  6bfce6: 00 ff                        	addb	%bh, %bh
  6bfce8: a0 3e 6c 00 01               	movb	0x1006c3e, %al
  6bfced: 00 00                        	addb	%al, (%eax)
  6bfcef: 00 00                        	addb	%al, (%eax)
  6bfcf1: 00 00                        	addb	%al, (%eax)
  6bfcf3: 80 00 00                     	addb	$0x0, (%eax)
  6bfcf6: 00 80 ff ff 07 45            	addb	%al, 0x4507ffff(%eax)
  6bfcfc: 6e                           	outsb	(%esi), %dx
  6bfcfd: 61                           	popal
  6bfcfe: 62 6c 65 64                  	bound	%ebp, 0x64(%ebp,%eiz,2)
  6bfd02: 98                           	cwtl
  6bfd03: b1 41                        	movb	$0x41, %cl
  6bfd05: 00 1c 00                     	addb	%bl, (%eax,%eax)
  6bfd08: 00 ff                        	addb	%bh, %bh
  6bfd0a: b4 3e                        	movb	$0x3e, %ah
  6bfd0c: 6c                           	insb	%dx, %es:(%edi)
  6bfd0d: 00 01                        	addb	%al, (%ecx)
  6bfd0f: 00 00                        	addb	%al, (%eax)
  6bfd11: 00 00                        	addb	%al, (%eax)
  6bfd13: 00 00                        	addb	%al, (%eax)
  6bfd15: 80 00 00                     	addb	$0x0, (%eax)
  6bfd18: 00 80 ff ff 06 48            	addb	%al, 0x4806ffff(%eax)
  6bfd1e: 61                           	popal
  6bfd1f: 6e                           	outsb	(%esi), %dx
  6bfd20: 64 6c                        	insb	%dx, %es:(%edi)
  6bfd22: 65 00 28                     	addb	%ch, %gs:(%eax)
  6bfd25: fd                           	std
  6bfd26: 6b 00 11                     	imull	$0x11, (%eax), %eax
  6bfd29: 15 3a 54 57 69               	adcl	$0x6957543a, %eax       # imm = 0x6957543A
  6bfd2e: 6e                           	outsb	(%esi), %dx
  6bfd2f: 47                           	incl	%edi
  6bfd30: 65 73 74                     	jae	0x6bfda7 <TMethodImplementationIntercept+0x24a88f>
  6bfd33: 75 72                        	jne	0x6bfda7 <TMethodImplementationIntercept+0x24a88f>
  6bfd35: 65 45                        	incl	%ebp
  6bfd37: 6e                           	outsb	(%esi), %dx
  6bfd38: 67 69 6e 65 2e 3a 31 04      	imull	$0x4313a2e, 0x65(%bp), %ebp # imm = 0x4313A2E
  6bfd40: 00 00                        	addb	%al, (%eax)
  6bfd42: 00 00                        	addb	%al, (%eax)
  6bfd44: 00 00                        	addb	%al, (%eax)
  6bfd46: 00 ff                        	addb	%bh, %bh
  6bfd48: ff ff                        	<unknown>
  6bfd4a: ff 88 fc 6b 00 10            	decl	0x10006bfc(%eax)
  6bfd50: 46                           	incl	%esi
  6bfd51: 4d                           	decl	%ebp
  6bfd52: 58                           	popl	%eax
  6bfd53: 2e 47                        	incl	%edi
  6bfd55: 65 73 74                     	jae	0x6bfdcc <TMethodImplementationIntercept+0x24a8b4>
  6bfd58: 75 72                        	jne	0x6bfdcc <TMethodImplementationIntercept+0x24a8b4>
  6bfd5a: 65 73 2e                     	jae	0x6bfd8b <TMethodImplementationIntercept+0x24a873>
  6bfd5d: 57                           	pushl	%edi
  6bfd5e: 69 6e 88 fc 6b 00 02         	imull	$0x2006bfc, -0x78(%esi), %ebp # imm = 0x2006BFC
  6bfd65: 00 00                        	addb	%al, (%eax)
  6bfd67: 00 c0                        	addb	%al, %al
  6bfd69: fd                           	std
  6bfd6a: 6b 00 00                     	imull	$0x0, (%eax), %eax
  6bfd6d: 00 00                        	addb	%al, (%eax)
  6bfd6f: 00 00                        	addb	%al, (%eax)
  6bfd71: 00 00                        	addb	%al, (%eax)
  6bfd73: 00 e8                        	addb	%ch, %al
  6bfd75: fd                           	std
  6bfd76: 6b 00 00                     	imull	$0x0, (%eax), %eax
  6bfd79: ff 6b 00                     	ljmpl	*(%ebx)
  6bfd7c: fa                           	cli
  6bfd7d: fd                           	std
  6bfd7e: 6b 00 42                     	imull	$0x42, (%eax), %eax
  6bfd81: fe 6b 00                     	<unknown>
  6bfd84: 00 00                        	addb	%al, (%eax)
  6bfd86: 00 00                        	addb	%al, (%eax)
  6bfd88: 60                           	pushal
  6bfd89: fe 6b 00                     	<unknown>
  6bfd8c: 20 00                        	andb	%al, (%eax)
  6bfd8e: 00 00                        	addb	%al, (%eax)
  6bfd90: 54                           	pushl	%esp
  6bfd91: ec                           	inb	%dx, %al
  6bfd92: 6b 00 04                     	imull	$0x4, (%eax), %eax
  6bfd95: a8 40                        	testb	$0x40, %al
  6bfd97: 00 0c a8                     	addb	%cl, (%eax,%ebp,4)
  6bfd9a: 40                           	incl	%eax
  6bfd9b: 00 2c ab                     	addb	%ch, (%ebx,%ebp,4)
  6bfd9e: 40                           	incl	%eax
  6bfd9f: 00 24 ab                     	addb	%ah, (%ebx,%ebp,4)
  6bfda2: 40                           	incl	%eax
  6bfda3: 00 44 ab 40                  	addb	%al, 0x40(%ebx,%ebp,4)
  6bfda7: 00 48 ab                     	addb	%cl, -0x55(%eax)
  6bfdaa: 40                           	incl	%eax
  6bfdab: 00 4c ab 40                  	addb	%cl, 0x40(%ebx,%ebp,4)
  6bfdaf: 00 40 ab                     	addb	%al, -0x55(%eax)
  6bfdb2: 40                           	incl	%eax
  6bfdb3: 00 c4                        	addb	%al, %ah
  6bfdb5: a5                           	movsl	(%esi), %es:(%edi)
  6bfdb6: 40                           	incl	%eax
  6bfdb7: 00 e0                        	addb	%ah, %al
  6bfdb9: a5                           	movsl	(%esi), %es:(%edi)
  6bfdba: 40                           	incl	%eax
  6bfdbb: 00 78 31                     	addb	%bh, 0x31(%eax)
  6bfdbe: 6c                           	insb	%dx, %es:(%edi)
  6bfdbf: 00 08                        	addb	%cl, (%eax)
  6bfdc1: 32 6c 00 dc                  	xorb	-0x24(%eax,%eax), %ch
  6bfdc5: 30 6c 00 88                  	xorb	%ch, -0x78(%eax,%eax)
  6bfdc9: 32 6c 00 24                  	xorb	0x24(%eax,%eax), %ch
  6bfdcd: 31 6c 00 d0                  	xorl	%ebp, -0x30(%eax,%eax)
  6bfdd1: 23 6d 00                     	andl	(%ebp), %ebp
  6bfdd4: e8 31 6c 00 f0               	calll	0xf06c6a0a
  6bfdd9: 48                           	decl	%eax
  6bfdda: 6c                           	insb	%dx, %es:(%edi)
  6bfddb: 00 64 25 6d                  	addb	%ah, 0x6d(%ebp,%eiz)
  6bfddf: 00 e4                        	addb	%ah, %ah
  6bfde1: 30 6c 00 48                  	xorb	%ch, 0x48(%eax,%eax)
  6bfde5: 32 6c 00 0e                  	xorb	0xe(%eax,%eax), %ch
  6bfde9: 00 00                        	addb	%al, (%eax)
  6bfdeb: 00 00                        	addb	%al, (%eax)
  6bfded: 00 01                        	addb	%al, (%ecx)
  6bfdef: 00 00                        	addb	%al, (%eax)
  6bfdf1: 00 24 fd 6b 00 14 00         	addb	%ah, 0x14006b(,%edi,8)
		...
  6bfe00: 02 00                        	addb	(%eax), %al
  6bfe02: 00 24 fd 6b 00 14 00         	addb	%ah, 0x14006b(,%edi,8)
  6bfe09: 00 00                        	addb	%al, (%eax)
  6bfe0b: 14 46                        	adcb	$0x46, %al
  6bfe0d: 44                           	incl	%esp
  6bfe0e: 65 66 65 72 72               	jb	0x6bfe85 <TMethodImplementationIntercept+0x24a96d>
  6bfe13: 65 64 43                     	incl	%ebx
  6bfe16: 6c                           	insb	%dx, %es:(%edi)
  6bfe17: 65 61                        	popal
  6bfe19: 6e                           	outsb	(%esi), %dx
  6bfe1a: 75 70                        	jne	0x6bfe8c <TMethodImplementationIntercept+0x24a974>
  6bfe1c: 4c                           	decl	%esp
  6bfe1d: 69 73 74 02 00 00 88         	imull	$0x88000002, 0x74(%ebx), %esi # imm = 0x88000002
  6bfe24: fc                           	cld
  6bfe25: 6b 00 18                     	imull	$0x18, (%eax), %eax
  6bfe28: 00 00                        	addb	%al, (%eax)
  6bfe2a: 00 14 46                     	addb	%dl, (%esi,%eax,2)
  6bfe2d: 53                           	pushl	%ebx
  6bfe2e: 74 79                        	je	0x6bfea9 <TMethodImplementationIntercept+0x24a991>
  6bfe30: 6c                           	insb	%dx, %es:(%edi)
  6bfe31: 75 73                        	jne	0x6bfea6 <TMethodImplementationIntercept+0x24a98e>
  6bfe33: 47                           	incl	%edi
  6bfe34: 65 73 74                     	jae	0x6bfeab <TMethodImplementationIntercept+0x24a993>
  6bfe37: 75 72                        	jne	0x6bfeab <TMethodImplementationIntercept+0x24a993>
  6bfe39: 65 45                        	incl	%ebp
  6bfe3b: 6e                           	outsb	(%esi), %dx
  6bfe3c: 67 69 6e 65 02 00 00 00      	imull	$0x2, 0x65(%bp), %ebp
  6bfe44: 03 00                        	addl	(%eax), %eax
  6bfe46: 72 fe                        	jb	0x6bfe46 <TMethodImplementationIntercept+0x24a92e>
  6bfe48: 6b 00 4c                     	imull	$0x4c, (%eax), %eax
  6bfe4b: 00 03                        	addb	%al, (%ebx)
  6bfe4d: 00 aa fe 6b 00 4d            	addb	%ch, 0x4d006bfe(%edx)
  6bfe53: 00 ff                        	addb	%bh, %bh
  6bfe55: ff d1                        	calll	*%ecx
  6bfe57: fe 6b 00                     	<unknown>
  6bfe5a: 43                           	incl	%ebx
  6bfe5b: 00 f4                        	addb	%dh, %ah
  6bfe5d: ff 0a                        	decl	(%edx)
  6bfe5f: 00 11                        	addb	%dl, (%ecx)
  6bfe61: 54                           	pushl	%esp
  6bfe62: 57                           	pushl	%edi
  6bfe63: 69 6e 47 65 73 74 75         	imull	$0x75747365, 0x47(%esi), %ebp # imm = 0x75747365
  6bfe6a: 72 65                        	jb	0x6bfed1 <TMethodImplementationIntercept+0x24a9b9>
  6bfe6c: 45                           	incl	%ebp
  6bfe6d: 6e                           	outsb	(%esi), %dx
  6bfe6e: 67 69 6e 65 38 00 24 31      	imull	$0x31240038, 0x65(%bp), %ebp # imm = 0x31240038
  6bfe76: 6c                           	insb	%dx, %es:(%edi)
  6bfe77: 00 06                        	addb	%al, (%esi)
  6bfe79: 43                           	incl	%ebx
  6bfe7a: 72 65                        	jb	0x6bfee1 <TMethodImplementationIntercept+0x24a9c9>
  6bfe7c: 61                           	popal
  6bfe7d: 74 65                        	je	0x6bfee4 <TMethodImplementationIntercept+0x24a9cc>
  6bfe7f: 03 00                        	addl	(%eax), %eax
  6bfe81: 00 00                        	addb	%al, (%eax)
  6bfe83: 00 00                        	addb	%al, (%eax)
  6bfe85: 08 00                        	orb	%al, (%eax)
  6bfe87: 02 08                        	addb	(%eax), %cl
  6bfe89: fc                           	cld
  6bfe8a: fe 6b 00                     	<unknown>
  6bfe8d: 00 00                        	addb	%al, (%eax)
  6bfe8f: 04 53                        	addb	$0x53, %al
  6bfe91: 65 6c                        	insb	%dx, %es:(%edi)
  6bfe93: 66 02 00                     	addb	(%eax), %al
  6bfe96: 0a 04 dd 4a 00 02 00         	orb	0x2004a(,%ebx,8), %al
  6bfe9d: 08 41 43                     	orb	%al, 0x43(%ecx)
  6bfea0: 6f                           	outsl	(%esi), %dx
  6bfea1: 6e                           	outsb	(%esi), %dx
  6bfea2: 74 72                        	je	0x6bff16 <TMethodImplementationIntercept+0x24a9fe>
  6bfea4: 6f                           	outsl	(%esi), %dx
  6bfea5: 6c                           	insb	%dx, %es:(%edi)
  6bfea6: 02 00                        	addb	(%eax), %al
  6bfea8: 02 00                        	addb	(%eax), %al
  6bfeaa: 27                           	daa
  6bfeab: 00 78 31                     	addb	%bh, 0x31(%eax)
  6bfeae: 6c                           	insb	%dx, %es:(%edi)
  6bfeaf: 00 07                        	addb	%al, (%edi)
  6bfeb1: 44                           	incl	%esp
  6bfeb2: 65 73 74                     	jae	0x6bff29 <TMethodImplementationIntercept+0x24aa11>
  6bfeb5: 72 6f                        	jb	0x6bff26 <TMethodImplementationIntercept+0x24aa0e>
  6bfeb7: 79 03                        	jns	0x6bfebc <TMethodImplementationIntercept+0x24a9a4>
  6bfeb9: 00 00                        	addb	%al, (%eax)
  6bfebb: 00 00                        	addb	%al, (%eax)
  6bfebd: 00 08                        	addb	%cl, (%eax)
  6bfebf: 00 01                        	addb	%al, (%ecx)
  6bfec1: 08 fc                        	orb	%bh, %ah
  6bfec3: fe 6b 00                     	<unknown>
  6bfec6: 00 00                        	addb	%al, (%eax)
  6bfec8: 04 53                        	addb	$0x53, %al
  6bfeca: 65 6c                        	insb	%dx, %es:(%edi)
  6bfecc: 66 02 00                     	addb	(%eax), %al
  6bfecf: 02 00                        	addb	(%eax), %al
  6bfed1: 29 00                        	subl	%eax, (%eax)
  6bfed3: e8 33 6c 00 09               	calll	0x96c6b0b
  6bfed8: 53                           	pushl	%ebx
  6bfed9: 75 70                        	jne	0x6bff4b <TMethodImplementationIntercept+0x24aa33>
  6bfedb: 70 6f                        	jo	0x6bff4c <TMethodImplementationIntercept+0x24aa34>
  6bfedd: 72 74                        	jb	0x6bff53 <TMethodImplementationIntercept+0x24aa3b>
  6bfedf: 65 64 03 00                  	addl	%fs:(%eax), %eax
  6bfee3: 00 10                        	addb	%dl, (%eax)
  6bfee5: 40                           	incl	%eax
  6bfee6: 00 08                        	addb	%cl, (%eax)
  6bfee8: 00 01                        	addb	%al, (%ecx)
  6bfeea: 00 00                        	addb	%al, (%eax)
  6bfeec: 00 00                        	addb	%al, (%eax)
  6bfeee: 00 00                        	addb	%al, (%eax)
  6bfef0: 00 04 53                     	addb	%al, (%ebx,%edx,2)
  6bfef3: 65 6c                        	insb	%dx, %es:(%edi)
  6bfef5: 66 02 00                     	addb	(%eax), %al
  6bfef8: 02 00                        	addb	(%eax), %al
  6bfefa: 00 00                        	addb	%al, (%eax)
  6bfefc: 00 ff                        	addb	%bh, %bh
  6bfefe: 6b 00 07                     	imull	$0x7, (%eax), %eax
  6bff01: 11 54 57 69                  	adcl	%edx, 0x69(%edi,%edx,2)
  6bff05: 6e                           	outsb	(%esi), %dx
  6bff06: 47                           	incl	%edi
  6bff07: 65 73 74                     	jae	0x6bff7e <TMethodImplementationIntercept+0x24aa66>
  6bff0a: 75 72                        	jne	0x6bff7e <TMethodImplementationIntercept+0x24aa66>
  6bff0c: 65 45                        	incl	%ebp
  6bff0e: 6e                           	outsb	(%esi), %dx
  6bff0f: 67 69 6e 65 c0 fd 6b 00      	imull	$0x6bfdc0, 0x65(%bp), %ebp # imm = 0x6BFDC0
  6bff17: fc                           	cld
  6bff18: ed                           	inl	%dx, %eax
  6bff19: 6b 00 00                     	imull	$0x0, (%eax), %eax
  6bff1c: 00 10                        	addb	%dl, (%eax)
  6bff1e: 46                           	incl	%esi
  6bff1f: 4d                           	decl	%ebp
  6bff20: 58                           	popl	%eax
  6bff21: 2e 47                        	incl	%edi
  6bff23: 65 73 74                     	jae	0x6bff9a <TMethodImplementationIntercept+0x24aa82>
  6bff26: 75 72                        	jne	0x6bff9a <TMethodImplementationIntercept+0x24aa82>
  6bff28: 65 73 2e                     	jae	0x6bff59 <TMethodImplementationIntercept+0x24aa41>
  6bff2b: 57                           	pushl	%edi
  6bff2c: 69 6e 00 00 00 00 02         	imull	$0x2000000, (%esi), %ebp # imm = 0x2000000
  6bff33: 00 00                        	addb	%al, (%eax)
  6bff35: 00 00                        	addb	%al, (%eax)
  6bff37: 00 3c ff                     	addb	%bh, (%edi,%edi,8)
  6bff3a: 6b 00 08                     	imull	$0x8, (%eax), %eax
  6bff3d: 1f                           	popl	%ds
  6bff3e: 54                           	pushl	%esp
  6bff3f: 47                           	incl	%edi
  6bff40: 65 73 74                     	jae	0x6bffb7 <TMethodImplementationIntercept+0x24aa9f>
  6bff43: 75 72                        	jne	0x6bffb7 <TMethodImplementationIntercept+0x24aa9f>
  6bff45: 65 52                        	pushl	%edx
  6bff47: 65 63 6f 67                  	arpl	%bp, %gs:0x67(%edi)
  6bff4b: 6e                           	outsb	(%esi), %dx
  6bff4c: 69 7a 65 72 2e 54 50         	imull	$0x50542e72, 0x65(%edx), %edi # imm = 0x50542E72
  6bff53: 72 65                        	jb	0x6bffba <TMethodImplementationIntercept+0x24aaa2>
  6bff55: 43                           	incl	%ebx
  6bff56: 61                           	popal
  6bff57: 6c                           	insb	%dx, %es:(%edi)
  6bff58: 6c                           	insb	%dx, %es:(%edi)
  6bff59: 62 61 63                     	bound	%esp, 0x63(%ecx)
  6bff5c: 6b 00 05                     	imull	$0x5, (%eax), %eax
  6bff5f: 16                           	pushl	%ss
  6bff60: 06                           	pushl	%es
  6bff61: 50                           	pushl	%eax
  6bff62: 6f                           	outsl	(%esi), %dx
  6bff63: 69 6e 74 73 07 54 50         	imull	$0x50540773, 0x74(%esi), %ebp # imm = 0x50540773
  6bff6a: 6f                           	outsl	(%esi), %dx
  6bff6b: 69 6e 74 46 16 0d 47         	imull	$0x470d1646, 0x74(%esi), %ebp # imm = 0x470D1646
  6bff72: 65 73 74                     	jae	0x6bffe9 <TMethodImplementationIntercept+0x24aad1>
  6bff75: 75 72                        	jne	0x6bffe9 <TMethodImplementationIntercept+0x24aad1>
  6bff77: 65 50                        	pushl	%eax
  6bff79: 6f                           	outsl	(%esi), %dx
  6bff7a: 69 6e 74 73 07 54 50         	imull	$0x50540773, 0x74(%esi), %ebp # imm = 0x50540773
  6bff81: 6f                           	outsl	(%esi), %dx
  6bff82: 69 6e 74 46 00 09 47         	imull	$0x47090046, 0x74(%esi), %ebp # imm = 0x47090046
  6bff89: 65 73 74                     	jae	0x6c0000 <TMethodImplementationIntercept+0x24aae8>
  6bff8c: 75 72                        	jne	0x6c0000 <TMethodImplementationIntercept+0x24aae8>
  6bff8e: 65 49                        	decl	%ecx
  6bff90: 44                           	incl	%esp
  6bff91: 0a 54 47 65                  	orb	0x65(%edi,%eax,2), %dl
  6bff95: 73 74                        	jae	0x6c000b <TMethodImplementationIntercept+0x24aaf3>
  6bff97: 75 72                        	jne	0x6c000b <TMethodImplementationIntercept+0x24aaf3>
  6bff99: 65 49                        	decl	%ecx
  6bff9b: 44                           	incl	%esp
  6bff9c: 00 09                        	addb	%cl, (%ecx)
  6bff9e: 44                           	incl	%esp
  6bff9f: 65 76 69                     	jbe	0x6c000b <TMethodImplementationIntercept+0x24aaf3>
  6bffa2: 61                           	popal
  6bffa3: 74 69                        	je	0x6c000e <TMethodImplementationIntercept+0x24aaf6>
  6bffa5: 6f                           	outsl	(%esi), %dx
  6bffa6: 6e                           	outsb	(%esi), %dx
  6bffa7: 07                           	popl	%es
  6bffa8: 49                           	decl	%ecx
  6bffa9: 6e                           	outsb	(%esi), %dx
  6bffaa: 74 65                        	je	0x6c0011 <TMethodImplementationIntercept+0x24aaf9>
  6bffac: 67 65 72 00                  	addr16		jb	0x6bffb0 <TMethodImplementationIntercept+0x24aa98>
  6bffb0: 0b 45 72                     	orl	0x72(%ebp), %eax
  6bffb3: 72 6f                        	jb	0x6c0024 <TMethodImplementationIntercept+0x24ab0c>
  6bffb5: 72 4d                        	jb	0x6c0004 <TMethodImplementationIntercept+0x24aaec>
  6bffb7: 61                           	popal
  6bffb8: 72 67                        	jb	0x6c0021 <TMethodImplementationIntercept+0x24ab09>
  6bffba: 69 6e 07 49 6e 74 65         	imull	$0x65746e49, 0x7(%esi), %ebp # imm = 0x65746E49
  6bffc1: 67 65 72 00                  	addr16		jb	0x6bffc5 <TMethodImplementationIntercept+0x24aaad>
		...
  6bffcd: 5c                           	popl	%esp
  6bffce: 5d                           	popl	%ebp
  6bffcf: 93                           	xchgl	%ebx, %eax
  6bffd0: 00 9c 10 40 00 9c 10         	addb	%bl, 0x109c0040(%eax,%edx)
  6bffd7: 40                           	incl	%eax
  6bffd8: 00 df                        	addb	%bl, %bh
  6bffda: ff 6b 00                     	ljmpl	*(%ebx)
  6bffdd: 02 00                        	addb	(%eax), %al
  6bffdf: 00 00                        	addb	%al, (%eax)
  6bffe1: 00 00                        	addb	%al, (%eax)
  6bffe3: 00 00                        	addb	%al, (%eax)
  6bffe5: 05 16 ec 58 41               	addl	$0x4158ec16, %eax       # imm = 0x4158EC16
  6bffea: 00 06                        	addb	%al, (%esi)
  6bffec: 50                           	pushl	%eax
  6bffed: 6f                           	outsl	(%esi), %dx
  6bffee: 69 6e 74 73 02 00 16         	imull	$0x16000273, 0x74(%esi), %ebp # imm = 0x16000273
  6bfff5: ec                           	inb	%dx, %al
  6bfff6: 58                           	popl	%eax
  6bfff7: 41                           	incl	%ecx
  6bfff8: 00 0d 47 65 73 74            	addb	%cl, 0x74736547
  6bfffe: 75 72                        	jne	0x6c0072 <TMethodImplementationIntercept+0x24ab5a>
  6c0000: 65 50                        	pushl	%eax
  6c0002: 6f                           	outsl	(%esi), %dx
  6c0003: 69 6e 74 73 02 00 00         	imull	$0x273, 0x74(%esi), %ebp # imm = 0x273
  6c000a: 5c                           	popl	%esp
  6c000b: 5d                           	popl	%ebp
  6c000c: 93                           	xchgl	%ebx, %eax
  6c000d: 00 09                        	addb	%cl, (%ecx)
  6c000f: 47                           	incl	%edi
  6c0010: 65 73 74                     	jae	0x6c0087 <TMethodImplementationIntercept+0x24ab6f>
  6c0013: 75 72                        	jne	0x6c0087 <TMethodImplementationIntercept+0x24ab6f>
  6c0015: 65 49                        	decl	%ecx
  6c0017: 44                           	incl	%esp
  6c0018: 02 00                        	addb	(%eax), %al
  6c001a: 00 9c 10 40 00 09 44         	addb	%bl, 0x44090040(%eax,%edx)
  6c0021: 65 76 69                     	jbe	0x6c008d <TMethodImplementationIntercept+0x24ab75>
  6c0024: 61                           	popal
  6c0025: 74 69                        	je	0x6c0090 <TMethodImplementationIntercept+0x24ab78>
  6c0027: 6f                           	outsl	(%esi), %dx
  6c0028: 6e                           	outsb	(%esi), %dx
  6c0029: 02 00                        	addb	(%eax), %al
  6c002b: 00 9c 10 40 00 0b 45         	addb	%bl, 0x450b0040(%eax,%edx)
  6c0032: 72 72                        	jb	0x6c00a6 <TMethodImplementationIntercept+0x24ab8e>
  6c0034: 6f                           	outsl	(%esi), %dx
  6c0035: 72 4d                        	jb	0x6c0084 <TMethodImplementationIntercept+0x24ab6c>
  6c0037: 61                           	popal
  6c0038: 72 67                        	jb	0x6c00a1 <TMethodImplementationIntercept+0x24ab89>
  6c003a: 69 6e 02 00 00 00 44         	imull	$0x44000000, 0x2(%esi), %ebp # imm = 0x44000000
  6c0041: 00 6c 00 08                  	addb	%ch, 0x8(%eax,%eax)
  6c0045: 20 54 47 65                  	andb	%dl, 0x65(%edi,%eax,2)
  6c0049: 73 74                        	jae	0x6c00bf <TMethodImplementationIntercept+0x24aba7>
  6c004b: 75 72                        	jne	0x6c00bf <TMethodImplementationIntercept+0x24aba7>
  6c004d: 65 52                        	pushl	%edx
  6c004f: 65 63 6f 67                  	arpl	%bp, %gs:0x67(%edi)
  6c0053: 6e                           	outsb	(%esi), %dx
  6c0054: 69 7a 65 72 2e 54 50         	imull	$0x50542e72, 0x65(%edx), %edi # imm = 0x50542E72
  6c005b: 6f                           	outsl	(%esi), %dx
  6c005c: 73 74                        	jae	0x6c00d2 <TMethodImplementationIntercept+0x24abba>
  6c005e: 43                           	incl	%ebx
  6c005f: 61                           	popal
  6c0060: 6c                           	insb	%dx, %es:(%edi)
  6c0061: 6c                           	insb	%dx, %es:(%edi)
  6c0062: 62 61 63                     	bound	%esp, 0x63(%ecx)
  6c0065: 6b 00 04                     	imull	$0x4, (%eax), %eax
  6c0068: 16                           	pushl	%ss
  6c0069: 0b 50 65                     	orl	0x65(%eax), %edx
  6c006c: 72 63                        	jb	0x6c00d1 <TMethodImplementationIntercept+0x24abb9>
  6c006e: 65 6e                        	outsb	%gs:(%esi), %dx
  6c0070: 74 61                        	je	0x6c00d3 <TMethodImplementationIntercept+0x24abbb>
  6c0072: 67 65 73 06                  	addr16		jae	0x6c007c <TMethodImplementationIntercept+0x24ab64>
  6c0076: 44                           	incl	%esp
  6c0077: 6f                           	outsl	(%esi), %dx
  6c0078: 75 62                        	jne	0x6c00dc <TMethodImplementationIntercept+0x24abc4>
  6c007a: 6c                           	insb	%dx, %es:(%edi)
  6c007b: 65 16                        	pushl	%ss
  6c007d: 06                           	pushl	%es
  6c007e: 50                           	pushl	%eax
  6c007f: 6f                           	outsl	(%esi), %dx
  6c0080: 69 6e 74 73 07 54 50         	imull	$0x50540773, 0x74(%esi), %ebp # imm = 0x50540773
  6c0087: 6f                           	outsl	(%esi), %dx
  6c0088: 69 6e 74 46 16 0d 47         	imull	$0x470d1646, 0x74(%esi), %ebp # imm = 0x470D1646
  6c008f: 65 73 74                     	jae	0x6c0106 <TMethodImplementationIntercept+0x24abee>
  6c0092: 75 72                        	jne	0x6c0106 <TMethodImplementationIntercept+0x24abee>
  6c0094: 65 50                        	pushl	%eax
  6c0096: 6f                           	outsl	(%esi), %dx
  6c0097: 69 6e 74 73 07 54 50         	imull	$0x50540773, 0x74(%esi), %ebp # imm = 0x50540773
  6c009e: 6f                           	outsl	(%esi), %dx
  6c009f: 69 6e 74 46 00 09 47         	imull	$0x47090046, 0x74(%esi), %ebp # imm = 0x47090046
  6c00a6: 65 73 74                     	jae	0x6c011d <TMethodImplementationIntercept+0x24ac05>
  6c00a9: 75 72                        	jne	0x6c011d <TMethodImplementationIntercept+0x24ac05>
  6c00ab: 65 49                        	decl	%ecx
  6c00ad: 44                           	incl	%esp
  6c00ae: 0a 54 47 65                  	orb	0x65(%edi,%eax,2), %dl
  6c00b2: 73 74                        	jae	0x6c0128 <TMethodImplementationIntercept+0x24ac10>
  6c00b4: 75 72                        	jne	0x6c0128 <TMethodImplementationIntercept+0x24ac10>
  6c00b6: 65 49                        	decl	%ecx
  6c00b8: 44                           	incl	%esp
		...
  6c00c5: 00 5c 5d 93                  	addb	%bl, -0x6d(%ebp,%ebx,2)
  6c00c9: 00 d0                        	addb	%dl, %al
  6c00cb: 00 6c 00 02                  	addb	%ch, 0x2(%eax,%eax)
  6c00cf: 00 00                        	addb	%al, (%eax)
  6c00d1: 00 00                        	addb	%al, (%eax)
  6c00d3: 00 00                        	addb	%al, (%eax)
  6c00d5: 00 04 16                     	addb	%al, (%esi,%edx)
  6c00d8: b0 11                        	movb	$0x11, %al
  6c00da: 40                           	incl	%eax
  6c00db: 00 0b                        	addb	%cl, (%ebx)
  6c00dd: 50                           	pushl	%eax
  6c00de: 65 72 63                     	jb	0x6c0144 <TMethodImplementationIntercept+0x24ac2c>
  6c00e1: 65 6e                        	outsb	%gs:(%esi), %dx
  6c00e3: 74 61                        	je	0x6c0146 <TMethodImplementationIntercept+0x24ac2e>
  6c00e5: 67 65 73 02                  	addr16		jae	0x6c00eb <TMethodImplementationIntercept+0x24abd3>
  6c00e9: 00 16                        	addb	%dl, (%esi)
  6c00eb: ec                           	inb	%dx, %al
  6c00ec: 58                           	popl	%eax
  6c00ed: 41                           	incl	%ecx
  6c00ee: 00 06                        	addb	%al, (%esi)
  6c00f0: 50                           	pushl	%eax
  6c00f1: 6f                           	outsl	(%esi), %dx
  6c00f2: 69 6e 74 73 02 00 16         	imull	$0x16000273, 0x74(%esi), %ebp # imm = 0x16000273
  6c00f9: ec                           	inb	%dx, %al
  6c00fa: 58                           	popl	%eax
  6c00fb: 41                           	incl	%ecx
  6c00fc: 00 0d 47 65 73 74            	addb	%cl, 0x74736547
  6c0102: 75 72                        	jne	0x6c0176 <TMethodImplementationIntercept+0x24ac5e>
  6c0104: 65 50                        	pushl	%eax
  6c0106: 6f                           	outsl	(%esi), %dx
  6c0107: 69 6e 74 73 02 00 00         	imull	$0x273, 0x74(%esi), %ebp # imm = 0x273
  6c010e: 5c                           	popl	%esp
  6c010f: 5d                           	popl	%ebp
  6c0110: 93                           	xchgl	%ebx, %eax
  6c0111: 00 09                        	addb	%cl, (%ecx)
  6c0113: 47                           	incl	%edi
  6c0114: 65 73 74                     	jae	0x6c018b <TMethodImplementationIntercept+0x24ac73>
  6c0117: 75 72                        	jne	0x6c018b <TMethodImplementationIntercept+0x24ac73>
  6c0119: 65 49                        	decl	%ecx
  6c011b: 44                           	incl	%esp
  6c011c: 02 00                        	addb	(%eax), %al
  6c011e: 00 00                        	addb	%al, (%eax)
  6c0120: 78 01                        	js	0x6c0123 <TMethodImplementationIntercept+0x24ac0b>
  6c0122: 6c                           	insb	%dx, %es:(%edi)
		...
  6c012f: 00 88 02 6c 00 90            	addb	%cl, -0x6fff93fe(%eax)
  6c0135: 01 6c 00 c9                  	addl	%ebp, -0x37(%eax,%eax)
  6c0139: 01 6c 00 00                  	addl	%ebp, (%eax,%eax)
  6c013d: 00 00                        	addb	%al, (%eax)
  6c013f: 00 d7                        	addb	%dl, %bh
  6c0141: 01 6c 00 1c                  	addl	%ebp, 0x1c(%eax,%eax)
  6c0145: 00 00                        	addb	%al, (%eax)
  6c0147: 00 6c 0f 6d                  	addb	%ch, 0x6d(%edi,%ecx)
  6c014b: 00 04 a8                     	addb	%al, (%eax,%ebp,4)
  6c014e: 40                           	incl	%eax
  6c014f: 00 0c a8                     	addb	%cl, (%eax,%ebp,4)
  6c0152: 40                           	incl	%eax
  6c0153: 00 2c ab                     	addb	%ch, (%ebx,%ebp,4)
  6c0156: 40                           	incl	%eax
  6c0157: 00 24 ab                     	addb	%ah, (%ebx,%ebp,4)
  6c015a: 40                           	incl	%eax
  6c015b: 00 44 ab 40                  	addb	%al, 0x40(%ebx,%ebp,4)
  6c015f: 00 48 ab                     	addb	%cl, -0x55(%eax)
  6c0162: 40                           	incl	%eax
  6c0163: 00 4c ab 40                  	addb	%cl, 0x40(%ebx,%ebp,4)
  6c0167: 00 40 ab                     	addb	%al, -0x55(%eax)
  6c016a: 40                           	incl	%eax
  6c016b: 00 c4                        	addb	%al, %ah
  6c016d: a5                           	movsl	(%esi), %es:(%edi)
  6c016e: 40                           	incl	%eax
  6c016f: 00 e0                        	addb	%ah, %al
  6c0171: a5                           	movsl	(%esi), %es:(%edi)
  6c0172: 40                           	incl	%eax
  6c0173: 00 cc                        	addb	%cl, %ah
  6c0175: a6                           	cmpsb	%es:(%edi), (%esi)
  6c0176: 40                           	incl	%eax
  6c0177: 00 80 49 6c 00 ac            	addb	%al, -0x53ff93b7(%eax)
  6c017d: 3c 6d                        	cmpb	$0x6d, %al
  6c017f: 00 d4                        	addb	%dl, %ah
  6c0181: 3f                           	aas
  6c0182: 6d                           	insl	%dx, %es:(%edi)
  6c0183: 00 98 42 6d 00 b0            	addb	%bl, -0x4fff92be(%eax)
  6c0189: 3d 6d 00 fc 7b               	cmpl	$0x7bfc006d, %eax       # imm = 0x7BFC006D
  6c018e: 40                           	incl	%eax
  6c018f: 00 00                        	addb	%al, (%eax)
  6c0191: 00 00                        	addb	%al, (%eax)
  6c0193: 00 00                        	addb	%al, (%eax)
  6c0195: 00 02                        	addb	%al, (%edx)
  6c0197: 00 01                        	addb	%al, (%ecx)
  6c0199: 38 ff                        	cmpb	%bh, %bh
  6c019b: 6b 00 08                     	imull	$0x8, (%eax), %eax
  6c019e: 00 00                        	addb	%al, (%eax)
  6c01a0: 00 0c 46                     	addb	%cl, (%esi,%eax,2)
  6c01a3: 50                           	pushl	%eax
  6c01a4: 72 65                        	jb	0x6c020b <TMethodImplementationIntercept+0x24acf3>
  6c01a6: 43                           	incl	%ebx
  6c01a7: 61                           	popal
  6c01a8: 6c                           	insb	%dx, %es:(%edi)
  6c01a9: 6c                           	insb	%dx, %es:(%edi)
  6c01aa: 62 61 63                     	bound	%esp, 0x63(%ecx)
  6c01ad: 6b 02 00                     	imull	$0x0, (%edx), %eax
  6c01b0: 01 40 00                     	addl	%eax, (%eax)
  6c01b3: 6c                           	insb	%dx, %es:(%edi)
  6c01b4: 00 10                        	addb	%dl, (%eax)
  6c01b6: 00 00                        	addb	%al, (%eax)
  6c01b8: 00 0d 46 50 6f 73            	addb	%cl, 0x736f5046
  6c01be: 74 43                        	je	0x6c0203 <TMethodImplementationIntercept+0x24aceb>
  6c01c0: 61                           	popal
  6c01c1: 6c                           	insb	%dx, %es:(%edi)
  6c01c2: 6c                           	insb	%dx, %es:(%edi)
  6c01c3: 62 61 63                     	bound	%esp, 0x63(%ecx)
  6c01c6: 6b 02 00                     	imull	$0x0, (%edx), %eax
  6c01c9: 00 00                        	addb	%al, (%eax)
  6c01cb: 01 00                        	addl	%eax, (%eax)
  6c01cd: ea 01 6c 00 4a 00 00         	ljmpl	$0x0, $0x4a006c01       # imm = 0x4A006C01
  6c01d4: 00 06                        	addb	%al, (%esi)
  6c01d6: 00 12                        	addb	%dl, (%edx)
  6c01d8: 54                           	pushl	%esp
  6c01d9: 47                           	incl	%edi
  6c01da: 65 73 74                     	jae	0x6c0251 <TMethodImplementationIntercept+0x24ad39>
  6c01dd: 75 72                        	jne	0x6c0251 <TMethodImplementationIntercept+0x24ad39>
  6c01df: 65 52                        	pushl	%edx
  6c01e1: 65 63 6f 67                  	arpl	%bp, %gs:0x67(%edi)
  6c01e5: 6e                           	outsb	(%esi), %dx
  6c01e6: 69 7a 65 72 98 00 80         	imull	$0x80009872, 0x65(%edx), %edi # imm = 0x80009872
  6c01ed: 49                           	decl	%ecx
  6c01ee: 6c                           	insb	%dx, %es:(%edi)
  6c01ef: 00 05 4d 61 74 63            	addb	%al, 0x6374614d
  6c01f5: 68 03 00 8c 11               	pushl	$0x118c0003             # imm = 0x118C0003
  6c01fa: 40                           	incl	%eax
  6c01fb: 00 20                        	addb	%ah, (%eax)
  6c01fd: 00 07                        	addb	%al, (%edi)
  6c01ff: 08 84 02 6c 00 00 00         	orb	%al, 0x6c(%edx,%eax)
