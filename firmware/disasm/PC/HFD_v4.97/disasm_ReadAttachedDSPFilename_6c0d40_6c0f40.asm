
firmware/stock/PC/HFD_v4.97/Resources/HFD.exe:	file format coff-i386

Disassembly of section .text:

00475518 <TMethodImplementationIntercept>:
  6c0d40: 0d 6c 00 00 00               	orl	$0x6c, %eax
  6c0d45: 04 53                        	addb	$0x53, %al
  6c0d47: 65 6c                        	insb	%dx, %es:(%edi)
  6c0d49: 66 02 00                     	addb	(%eax), %al
  6c0d4c: 02 00                        	addb	(%eax), %al
  6c0d4e: 00 00                        	addb	%al, (%eax)
  6c0d50: 54                           	pushl	%esp
  6c0d51: 0d 6c 00 07 3b               	orl	$0x3b07006c, %eax       # imm = 0x3B07006C
  6c0d56: 54                           	pushl	%esp
  6c0d57: 44                           	incl	%esp
  6c0d58: 69 63 74 69 6f 6e 61         	imull	$0x616e6f69, 0x74(%ebx), %esp # imm = 0x616E6F69
  6c0d5f: 72 79                        	jb	0x6c0dda <TMethodImplementationIntercept+0x24b8c2>
  6c0d61: 3c 53                        	cmpb	$0x53, %al
  6c0d63: 79 73                        	jns	0x6c0dd8 <TMethodImplementationIntercept+0x24b8c0>
  6c0d65: 74 65                        	je	0x6c0dcc <TMethodImplementationIntercept+0x24b8b4>
  6c0d67: 6d                           	insl	%dx, %es:(%edi)
  6c0d68: 2e 50                        	pushl	%eax
  6c0d6a: 6f                           	outsl	(%esi), %dx
  6c0d6b: 69 6e 74 65 72 2c 53         	imull	$0x532c7265, 0x74(%esi), %ebp # imm = 0x532C7265
  6c0d72: 79 73                        	jns	0x6c0de7 <TMethodImplementationIntercept+0x24b8cf>
  6c0d74: 74 65                        	je	0x6c0ddb <TMethodImplementationIntercept+0x24b8c3>
  6c0d76: 6d                           	insl	%dx, %es:(%edi)
  6c0d77: 2e 50                        	pushl	%eax
  6c0d79: 6f                           	outsl	(%esi), %dx
  6c0d7a: 69 6e 74 65 72 3e 2e         	imull	$0x2e3e7265, 0x74(%esi), %ebp # imm = 0x2E3E7265
  6c0d81: 54                           	pushl	%esp
  6c0d82: 56                           	pushl	%esi
  6c0d83: 61                           	popal
  6c0d84: 6c                           	insb	%dx, %es:(%edi)
  6c0d85: 75 65                        	jne	0x6c0dec <TMethodImplementationIntercept+0x24b8d4>
  6c0d87: 45                           	incl	%ebp
  6c0d88: 6e                           	outsb	(%esi), %dx
  6c0d89: 75 6d                        	jne	0x6c0df8 <TMethodImplementationIntercept+0x24b8e0>
  6c0d8b: 65 72 61                     	jb	0x6c0def <TMethodImplementationIntercept+0x24b8d7>
  6c0d8e: 74 6f                        	je	0x6c0dff <TMethodImplementationIntercept+0x24b8e7>
  6c0d90: 72 60                        	jb	0x6c0df2 <TMethodImplementationIntercept+0x24b8da>
  6c0d92: 0c 6c                        	orb	$0x6c, %al
  6c0d94: 00 7c 7e 45                  	addb	%bh, 0x45(%esi,%edi,2)
  6c0d98: 00 00                        	addb	%al, (%eax)
  6c0d9a: 00 1b                        	addb	%bl, (%ebx)
  6c0d9c: 53                           	pushl	%ebx
  6c0d9d: 79 73                        	jns	0x6c0e12 <TMethodImplementationIntercept+0x24b8fa>
  6c0d9f: 74 65                        	je	0x6c0e06 <TMethodImplementationIntercept+0x24b8ee>
  6c0da1: 6d                           	insl	%dx, %es:(%edi)
  6c0da2: 2e 47                        	incl	%edi
  6c0da4: 65 6e                        	outsb	%gs:(%esi), %dx
  6c0da6: 65 72 69                     	jb	0x6c0e12 <TMethodImplementationIntercept+0x24b8fa>
  6c0da9: 63 73 2e                     	arpl	%si, 0x2e(%ebx)
  6c0dac: 43                           	incl	%ebx
  6c0dad: 6f                           	outsl	(%esi), %dx
  6c0dae: 6c                           	insb	%dx, %es:(%edi)
  6c0daf: 6c                           	insb	%dx, %es:(%edi)
  6c0db0: 65 63 74 69 6f               	arpl	%si, %gs:0x6f(%ecx,%ebp,2)
  6c0db5: 6e                           	outsb	(%esi), %dx
  6c0db6: 73 00                        	jae	0x6c0db8 <TMethodImplementationIntercept+0x24b8a0>
  6c0db8: 00 01                        	addb	%al, (%ecx)
  6c0dba: 00 02                        	addb	%al, (%edx)
  6c0dbc: c6 0d 6c 00 02 00            	<unknown>
  6c0dc2: 02 00                        	addb	(%eax), %al
  6c0dc4: 00 00                        	addb	%al, (%eax)
  6c0dc6: 00 11                        	addb	%dl, (%ecx)
  6c0dc8: 40                           	incl	%eax
  6c0dc9: 00 ec                        	addb	%ch, %ah
  6c0dcb: 5d                           	popl	%ebp
  6c0dcc: 6c                           	insb	%dx, %es:(%edi)
  6c0dcd: 00 00                        	addb	%al, (%eax)
  6c0dcf: 00 00                        	addb	%al, (%eax)
  6c0dd1: 00 01                        	addb	%al, (%ecx)
  6c0dd3: 00 00                        	addb	%al, (%eax)
  6c0dd5: 00 00                        	addb	%al, (%eax)
  6c0dd7: 00 00                        	addb	%al, (%eax)
  6c0dd9: 80 00 00                     	addb	$0x0, (%eax)
  6c0ddc: 00 80 ff ff 07 43            	addb	%al, 0x4307ffff(%eax)
  6c0de2: 75 72                        	jne	0x6c0e56 <TMethodImplementationIntercept+0x24b93e>
  6c0de4: 72 65                        	jb	0x6c0e4b <TMethodImplementationIntercept+0x24b933>
  6c0de6: 6e                           	outsb	(%esi), %dx
  6c0de7: 74 40                        	je	0x6c0e29 <TMethodImplementationIntercept+0x24b911>
  6c0de9: 0e                           	pushl	%cs
  6c0dea: 6c                           	insb	%dx, %es:(%edi)
		...
  6c0df7: 00 6c 0f 6c                  	addb	%ch, 0x6c(%edi,%ecx)
  6c0dfb: 00 48 0e                     	addb	%cl, 0xe(%eax)
  6c0dfe: 6c                           	insb	%dx, %es:(%edi)
  6c0dff: 00 71 0e                     	addb	%dh, 0xe(%ecx)
  6c0e02: 6c                           	insb	%dx, %es:(%edi)
  6c0e03: 00 00                        	addb	%al, (%eax)
  6c0e05: 00 00                        	addb	%al, (%eax)
  6c0e07: 00 8f 0e 6c 00 0c            	addb	%cl, 0xc006c0e(%edi)
  6c0e0d: 00 00                        	addb	%al, (%eax)
  6c0e0f: 00 f4                        	addb	%dh, %ah
  6c0e11: 7e 45                        	jle	0x6c0e58 <TMethodImplementationIntercept+0x24b940>
  6c0e13: 00 04 a8                     	addb	%al, (%eax,%ebp,4)
  6c0e16: 40                           	incl	%eax
  6c0e17: 00 0c a8                     	addb	%cl, (%eax,%ebp,4)
  6c0e1a: 40                           	incl	%eax
  6c0e1b: 00 2c ab                     	addb	%ch, (%ebx,%ebp,4)
  6c0e1e: 40                           	incl	%eax
  6c0e1f: 00 24 ab                     	addb	%ah, (%ebx,%ebp,4)
  6c0e22: 40                           	incl	%eax
  6c0e23: 00 44 ab 40                  	addb	%al, 0x40(%ebx,%ebp,4)
  6c0e27: 00 48 ab                     	addb	%cl, -0x55(%eax)
  6c0e2a: 40                           	incl	%eax
  6c0e2b: 00 4c ab 40                  	addb	%cl, 0x40(%ebx,%ebp,4)
  6c0e2f: 00 40 ab                     	addb	%al, -0x55(%eax)
  6c0e32: 40                           	incl	%eax
  6c0e33: 00 c4                        	addb	%al, %ah
  6c0e35: a5                           	movsl	(%esi), %es:(%edi)
  6c0e36: 40                           	incl	%eax
  6c0e37: 00 e0                        	addb	%ah, %al
  6c0e39: a5                           	movsl	(%esi), %es:(%edi)
  6c0e3a: 40                           	incl	%eax
  6c0e3b: 00 74 79 47                  	addb	%dh, 0x47(%ecx,%edi,2)
  6c0e3f: 00 80 5d 6c 00 d4            	addb	%al, -0x2bff93a3(%eax)
  6c0e45: 5d                           	popl	%ebp
  6c0e46: 6c                           	insb	%dx, %es:(%edi)
  6c0e47: 00 00                        	addb	%al, (%eax)
  6c0e49: 00 00                        	addb	%al, (%eax)
  6c0e4b: 00 00                        	addb	%al, (%eax)
  6c0e4d: 00 01                        	addb	%al, (%ecx)
  6c0e4f: 00 00                        	addb	%al, (%eax)
  6c0e51: b0 18                        	movb	$0x18, %al
  6c0e53: 6c                           	insb	%dx, %es:(%edi)
  6c0e54: 00 04 00                     	addb	%al, (%eax,%eax)
  6c0e57: 00 00                        	addb	%al, (%eax)
  6c0e59: 0b 46 44                     	orl	0x44(%esi), %eax
  6c0e5c: 69 63 74 69 6f 6e 61         	imull	$0x616e6f69, 0x74(%ebx), %esp # imm = 0x616E6F69
  6c0e63: 72 79                        	jb	0x6c0ede <TMethodImplementationIntercept+0x24b9c6>
  6c0e65: 0c 00                        	orb	$0x0, %al
  6c0e67: fc                           	cld
  6c0e68: 20 40 00                     	andb	%al, (%eax)
  6c0e6b: ac                           	lodsb	(%esi), %al
  6c0e6c: a6                           	cmpsb	%es:(%edi), (%esi)
  6c0e6d: 40                           	incl	%eax
  6c0e6e: 00 00                        	addb	%al, (%eax)
  6c0e70: 00 00                        	addb	%al, (%eax)
  6c0e72: 00 03                        	addb	%al, (%ebx)
  6c0e74: 00 cb                        	addb	%cl, %bl
  6c0e76: 0e                           	pushl	%cs
  6c0e77: 6c                           	insb	%dx, %es:(%edi)
  6c0e78: 00 44 00 f4                  	addb	%al, -0xc(%eax,%eax)
  6c0e7c: ff 06                        	incl	(%esi)
  6c0e7e: 0f 6c                        	<unknown>
  6c0e80: 00 42 00                     	addb	%al, (%edx)
  6c0e83: f4                           	hlt
  6c0e84: ff 33                        	pushl	(%ebx)
  6c0e86: 0f 6c                        	<unknown>
  6c0e88: 00 4a 00                     	addb	%cl, (%edx)
  6c0e8b: 01 00                        	addl	%eax, (%eax)
  6c0e8d: 02 00                        	addb	(%eax), %al
  6c0e8f: 3b 54 44 69                  	cmpl	0x69(%esp,%eax,2), %edx
  6c0e93: 63 74 69 6f                  	arpl	%si, 0x6f(%ecx,%ebp,2)
  6c0e97: 6e                           	outsb	(%esi), %dx
  6c0e98: 61                           	popal
  6c0e99: 72 79                        	jb	0x6c0f14 <TMethodImplementationIntercept+0x24b9fc>
  6c0e9b: 3c 53                        	cmpb	$0x53, %al
  6c0e9d: 79 73                        	jns	0x6c0f12 <TMethodImplementationIntercept+0x24b9fa>
  6c0e9f: 74 65                        	je	0x6c0f06 <TMethodImplementationIntercept+0x24b9ee>
  6c0ea1: 6d                           	insl	%dx, %es:(%edi)
  6c0ea2: 2e 50                        	pushl	%eax
  6c0ea4: 6f                           	outsl	(%esi), %dx
  6c0ea5: 69 6e 74 65 72 2c 53         	imull	$0x532c7265, 0x74(%esi), %ebp # imm = 0x532C7265
  6c0eac: 79 73                        	jns	0x6c0f21 <TMethodImplementationIntercept+0x24ba09>
  6c0eae: 74 65                        	je	0x6c0f15 <TMethodImplementationIntercept+0x24b9fd>
  6c0eb0: 6d                           	insl	%dx, %es:(%edi)
  6c0eb1: 2e 50                        	pushl	%eax
  6c0eb3: 6f                           	outsl	(%esi), %dx
  6c0eb4: 69 6e 74 65 72 3e 2e         	imull	$0x2e3e7265, 0x74(%esi), %ebp # imm = 0x2E3E7265
  6c0ebb: 54                           	pushl	%esp
  6c0ebc: 56                           	pushl	%esi
  6c0ebd: 61                           	popal
  6c0ebe: 6c                           	insb	%dx, %es:(%edi)
  6c0ebf: 75 65                        	jne	0x6c0f26 <TMethodImplementationIntercept+0x24ba0e>
  6c0ec1: 43                           	incl	%ebx
  6c0ec2: 6f                           	outsl	(%esi), %dx
  6c0ec3: 6c                           	insb	%dx, %es:(%edi)
  6c0ec4: 6c                           	insb	%dx, %es:(%edi)
  6c0ec5: 65 63 74 69 6f               	arpl	%si, %gs:0x6f(%ecx,%ebp,2)
  6c0eca: 6e                           	outsb	(%esi), %dx
  6c0ecb: 3b 00                        	cmpl	(%eax), %eax
  6c0ecd: 88 5d 6c                     	movb	%bl, 0x6c(%ebp)
  6c0ed0: 00 06                        	addb	%al, (%esi)
  6c0ed2: 43                           	incl	%ebx
  6c0ed3: 72 65                        	jb	0x6c0f3a <TMethodImplementationIntercept+0x24ba22>
  6c0ed5: 61                           	popal
  6c0ed6: 74 65                        	je	0x6c0f3d <TMethodImplementationIntercept+0x24ba25>
  6c0ed8: 03 00                        	addl	(%eax), %eax
  6c0eda: 00 00                        	addb	%al, (%eax)
  6c0edc: 00 00                        	addb	%al, (%eax)
  6c0ede: 08 00                        	orb	%al, (%eax)
  6c0ee0: 02 08                        	addb	(%eax), %cl
  6c0ee2: 68 0f 6c 00 00               	pushl	$0x6c0f                 # imm = 0x6C0F
  6c0ee7: 00 04 53                     	addb	%al, (%ebx,%edx,2)
  6c0eea: 65 6c                        	insb	%dx, %es:(%edi)
  6c0eec: 66 02 00                     	addb	(%eax), %al
  6c0eef: 0a b0 18 6c 00 02            	orb	0x2006c18(%eax), %dh
  6c0ef5: 00 0b                        	addb	%cl, (%ebx)
  6c0ef7: 41                           	incl	%ecx
  6c0ef8: 44                           	incl	%esp
  6c0ef9: 69 63 74 69 6f 6e 61         	imull	$0x616e6f69, 0x74(%ebx), %esp # imm = 0x616E6F69
  6c0f00: 72 79                        	jb	0x6c0f7b <TMethodImplementationIntercept+0x24ba63>
  6c0f02: 02 00                        	addb	(%eax), %al
  6c0f04: 02 00                        	addb	(%eax), %al
  6c0f06: 2d 00 c4 5d 6c               	subl	$0x6c5dc400, %eax       # imm = 0x6C5DC400
  6c0f0b: 00 0d 47 65 74 45            	addb	%cl, 0x45746547
  6c0f11: 6e                           	outsb	(%esi), %dx
  6c0f12: 75 6d                        	jne	0x6c0f81 <TMethodImplementationIntercept+0x24ba69>
  6c0f14: 65 72 61                     	jb	0x6c0f78 <TMethodImplementationIntercept+0x24ba60>
  6c0f17: 74 6f                        	je	0x6c0f88 <TMethodImplementationIntercept+0x24ba70>
  6c0f19: 72 03                        	jb	0x6c0f1e <TMethodImplementationIntercept+0x24ba06>
  6c0f1b: 00 50 0d                     	addb	%dl, 0xd(%eax)
  6c0f1e: 6c                           	insb	%dx, %es:(%edi)
  6c0f1f: 00 08                        	addb	%cl, (%eax)
  6c0f21: 00 01                        	addb	%al, (%ecx)
  6c0f23: 08 68 0f                     	orb	%ch, 0xf(%eax)
  6c0f26: 6c                           	insb	%dx, %es:(%edi)
  6c0f27: 00 00                        	addb	%al, (%eax)
  6c0f29: 00 04 53                     	addb	%al, (%ebx,%edx,2)
  6c0f2c: 65 6c                        	insb	%dx, %es:(%edi)
  6c0f2e: 66 02 00                     	addb	(%eax), %al
  6c0f31: 02 00                        	addb	(%eax), %al
  6c0f33: 32 00                        	xorb	(%eax), %al
  6c0f35: d4 5d                        	aam	$0x5d
  6c0f37: 6c                           	insb	%dx, %es:(%edi)
  6c0f38: 00 07                        	addb	%al, (%edi)
  6c0f3a: 54                           	pushl	%esp
  6c0f3b: 6f                           	outsl	(%esi), %dx
  6c0f3c: 41                           	incl	%ecx
  6c0f3d: 72 72                        	jb	0x6c0fb1 <TMethodImplementationIntercept+0x24ba99>
  6c0f3f: 61                           	popal
