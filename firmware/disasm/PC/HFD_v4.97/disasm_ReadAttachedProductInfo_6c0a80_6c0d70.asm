
firmware/stock/PC/HFD_v4.97/Resources/HFD.exe:	file format coff-i386

Disassembly of section .text:

00475518 <TMethodImplementationIntercept>:
  6c0a80: 00 00                        	addb	%al, (%eax)
  6c0a82: 00 03                        	addb	%al, (%ebx)
  6c0a84: 00 d9                        	addb	%bl, %cl
  6c0a86: 0a 6c 00 44                  	orb	0x44(%eax,%eax), %ch
  6c0a8a: 00 f4                        	addb	%dh, %ah
  6c0a8c: ff 14 0b                     	calll	*(%ebx,%ecx)
  6c0a8f: 6c                           	insb	%dx, %es:(%edi)
  6c0a90: 00 42 00                     	addb	%al, (%edx)
  6c0a93: f4                           	hlt
  6c0a94: ff 41 0b                     	incl	0xb(%ecx)
  6c0a97: 6c                           	insb	%dx, %es:(%edi)
  6c0a98: 00 4a 00                     	addb	%cl, (%edx)
  6c0a9b: 01 00                        	addl	%eax, (%eax)
  6c0a9d: 02 00                        	addb	(%eax), %al
  6c0a9f: 39 54 44 69                  	cmpl	%edx, 0x69(%esp,%eax,2)
  6c0aa3: 63 74 69 6f                  	arpl	%si, 0x6f(%ecx,%ebp,2)
  6c0aa7: 6e                           	outsb	(%esi), %dx
  6c0aa8: 61                           	popal
  6c0aa9: 72 79                        	jb	0x6c0b24 <TMethodImplementationIntercept+0x24b60c>
  6c0aab: 3c 53                        	cmpb	$0x53, %al
  6c0aad: 79 73                        	jns	0x6c0b22 <TMethodImplementationIntercept+0x24b60a>
  6c0aaf: 74 65                        	je	0x6c0b16 <TMethodImplementationIntercept+0x24b5fe>
  6c0ab1: 6d                           	insl	%dx, %es:(%edi)
  6c0ab2: 2e 50                        	pushl	%eax
  6c0ab4: 6f                           	outsl	(%esi), %dx
  6c0ab5: 69 6e 74 65 72 2c 53         	imull	$0x532c7265, 0x74(%esi), %ebp # imm = 0x532C7265
  6c0abc: 79 73                        	jns	0x6c0b31 <TMethodImplementationIntercept+0x24b619>
  6c0abe: 74 65                        	je	0x6c0b25 <TMethodImplementationIntercept+0x24b60d>
  6c0ac0: 6d                           	insl	%dx, %es:(%edi)
  6c0ac1: 2e 50                        	pushl	%eax
  6c0ac3: 6f                           	outsl	(%esi), %dx
  6c0ac4: 69 6e 74 65 72 3e 2e         	imull	$0x2e3e7265, 0x74(%esi), %ebp # imm = 0x2E3E7265
  6c0acb: 54                           	pushl	%esp
  6c0acc: 4b                           	decl	%ebx
  6c0acd: 65 79 43                     	jns	0x6c0b13 <TMethodImplementationIntercept+0x24b5fb>
  6c0ad0: 6f                           	outsl	(%esi), %dx
  6c0ad1: 6c                           	insb	%dx, %es:(%edi)
  6c0ad2: 6c                           	insb	%dx, %es:(%edi)
  6c0ad3: 65 63 74 69 6f               	arpl	%si, %gs:0x6f(%ecx,%ebp,2)
  6c0ad8: 6e                           	outsb	(%esi), %dx
  6c0ad9: 3b 00                        	cmpl	(%eax), %eax
  6c0adb: 68 5c 6c 00 06               	pushl	$0x6006c5c              # imm = 0x6006C5C
  6c0ae0: 43                           	incl	%ebx
  6c0ae1: 72 65                        	jb	0x6c0b48 <TMethodImplementationIntercept+0x24b630>
  6c0ae3: 61                           	popal
  6c0ae4: 74 65                        	je	0x6c0b4b <TMethodImplementationIntercept+0x24b633>
  6c0ae6: 03 00                        	addl	(%eax), %eax
  6c0ae8: 00 00                        	addb	%al, (%eax)
  6c0aea: 00 00                        	addb	%al, (%eax)
  6c0aec: 08 00                        	orb	%al, (%eax)
  6c0aee: 02 08                        	addb	(%eax), %cl
  6c0af0: 74 0b                        	je	0x6c0afd <TMethodImplementationIntercept+0x24b5e5>
  6c0af2: 6c                           	insb	%dx, %es:(%edi)
  6c0af3: 00 00                        	addb	%al, (%eax)
  6c0af5: 00 04 53                     	addb	%al, (%ebx,%edx,2)
  6c0af8: 65 6c                        	insb	%dx, %es:(%edi)
  6c0afa: 66 02 00                     	addb	(%eax), %al
  6c0afd: 0a b0 18 6c 00 02            	orb	0x2006c18(%eax), %dh
  6c0b03: 00 0b                        	addb	%cl, (%ebx)
  6c0b05: 41                           	incl	%ecx
  6c0b06: 44                           	incl	%esp
  6c0b07: 69 63 74 69 6f 6e 61         	imull	$0x616e6f69, 0x74(%ebx), %esp # imm = 0x616E6F69
  6c0b0e: 72 79                        	jb	0x6c0b89 <TMethodImplementationIntercept+0x24b671>
  6c0b10: 02 00                        	addb	(%eax), %al
  6c0b12: 02 00                        	addb	(%eax), %al
  6c0b14: 2d 00 a4 5c 6c               	subl	$0x6c5ca400, %eax       # imm = 0x6C5CA400
  6c0b19: 00 0d 47 65 74 45            	addb	%cl, 0x45746547
  6c0b1f: 6e                           	outsb	(%esi), %dx
  6c0b20: 75 6d                        	jne	0x6c0b8f <TMethodImplementationIntercept+0x24b677>
  6c0b22: 65 72 61                     	jb	0x6c0b86 <TMethodImplementationIntercept+0x24b66e>
  6c0b25: 74 6f                        	je	0x6c0b96 <TMethodImplementationIntercept+0x24b67e>
  6c0b27: 72 03                        	jb	0x6c0b2c <TMethodImplementationIntercept+0x24b614>
  6c0b29: 00 60 09                     	addb	%ah, 0x9(%eax)
  6c0b2c: 6c                           	insb	%dx, %es:(%edi)
  6c0b2d: 00 08                        	addb	%cl, (%eax)
  6c0b2f: 00 01                        	addb	%al, (%ecx)
  6c0b31: 08 74 0b 6c                  	orb	%dh, 0x6c(%ebx,%ecx)
  6c0b35: 00 00                        	addb	%al, (%eax)
  6c0b37: 00 04 53                     	addb	%al, (%ebx,%edx,2)
  6c0b3a: 65 6c                        	insb	%dx, %es:(%edi)
  6c0b3c: 66 02 00                     	addb	(%eax), %al
  6c0b3f: 02 00                        	addb	(%eax), %al
  6c0b41: 32 00                        	xorb	(%eax), %al
  6c0b43: b4 5c                        	movb	$0x5c, %ah
  6c0b45: 6c                           	insb	%dx, %es:(%edi)
  6c0b46: 00 07                        	addb	%al, (%edi)
  6c0b48: 54                           	pushl	%esp
  6c0b49: 6f                           	outsl	(%esi), %dx
  6c0b4a: 41                           	incl	%ecx
  6c0b4b: 72 72                        	jb	0x6c0bbf <TMethodImplementationIntercept+0x24b6a7>
  6c0b4d: 61                           	popal
  6c0b4e: 79 03                        	jns	0x6c0b53 <TMethodImplementationIntercept+0x24b63b>
  6c0b50: 00 8c 7d 45 00 08 00         	addb	%cl, 0x80045(%ebp,%edi,2)
  6c0b57: 02 08                        	addb	(%eax), %cl
  6c0b59: 74 0b                        	je	0x6c0b66 <TMethodImplementationIntercept+0x24b64e>
  6c0b5b: 6c                           	insb	%dx, %es:(%edi)
  6c0b5c: 00 00                        	addb	%al, (%eax)
  6c0b5e: 00 04 53                     	addb	%al, (%ebx,%edx,2)
  6c0b61: 65 6c                        	insb	%dx, %es:(%edi)
  6c0b63: 66 02 00                     	addb	(%eax), %al
  6c0b66: 40                           	incl	%eax
  6c0b67: 8c 7d 45                     	<unknown>
  6c0b6a: 00 01                        	addb	%al, (%ecx)
  6c0b6c: 00 01                        	addb	%al, (%ecx)
  6c0b6e: 01 02                        	addl	%eax, (%edx)
  6c0b70: 00 02                        	addb	%al, (%edx)
  6c0b72: 00 00                        	addb	%al, (%eax)
  6c0b74: 78 0b                        	js	0x6c0b81 <TMethodImplementationIntercept+0x24b669>
  6c0b76: 6c                           	insb	%dx, %es:(%edi)
  6c0b77: 00 07                        	addb	%al, (%edi)
  6c0b79: 39 54 44 69                  	cmpl	%edx, 0x69(%esp,%eax,2)
  6c0b7d: 63 74 69 6f                  	arpl	%si, 0x6f(%ecx,%ebp,2)
  6c0b81: 6e                           	outsb	(%esi), %dx
  6c0b82: 61                           	popal
  6c0b83: 72 79                        	jb	0x6c0bfe <TMethodImplementationIntercept+0x24b6e6>
  6c0b85: 3c 53                        	cmpb	$0x53, %al
  6c0b87: 79 73                        	jns	0x6c0bfc <TMethodImplementationIntercept+0x24b6e4>
  6c0b89: 74 65                        	je	0x6c0bf0 <TMethodImplementationIntercept+0x24b6d8>
  6c0b8b: 6d                           	insl	%dx, %es:(%edi)
  6c0b8c: 2e 50                        	pushl	%eax
  6c0b8e: 6f                           	outsl	(%esi), %dx
  6c0b8f: 69 6e 74 65 72 2c 53         	imull	$0x532c7265, 0x74(%esi), %ebp # imm = 0x532C7265
  6c0b96: 79 73                        	jns	0x6c0c0b <TMethodImplementationIntercept+0x24b6f3>
  6c0b98: 74 65                        	je	0x6c0bff <TMethodImplementationIntercept+0x24b6e7>
  6c0b9a: 6d                           	insl	%dx, %es:(%edi)
  6c0b9b: 2e 50                        	pushl	%eax
  6c0b9d: 6f                           	outsl	(%esi), %dx
  6c0b9e: 69 6e 74 65 72 3e 2e         	imull	$0x2e3e7265, 0x74(%esi), %ebp # imm = 0x2E3E7265
  6c0ba5: 54                           	pushl	%esp
  6c0ba6: 4b                           	decl	%ebx
  6c0ba7: 65 79 43                     	jns	0x6c0bed <TMethodImplementationIntercept+0x24b6d5>
  6c0baa: 6f                           	outsl	(%esi), %dx
  6c0bab: 6c                           	insb	%dx, %es:(%edi)
  6c0bac: 6c                           	insb	%dx, %es:(%edi)
  6c0bad: 65 63 74 69 6f               	arpl	%si, %gs:0x6f(%ecx,%ebp,2)
  6c0bb2: 6e                           	outsb	(%esi), %dx
  6c0bb3: 50                           	pushl	%eax
  6c0bb4: 0a 6c 00 14                  	orb	0x14(%eax,%eax), %ch
  6c0bb8: 80 45 00 00                  	addb	$0x0, (%ebp)
  6c0bbc: 00 1b                        	addb	%bl, (%ebx)
  6c0bbe: 53                           	pushl	%ebx
  6c0bbf: 79 73                        	jns	0x6c0c34 <TMethodImplementationIntercept+0x24b71c>
  6c0bc1: 74 65                        	je	0x6c0c28 <TMethodImplementationIntercept+0x24b710>
  6c0bc3: 6d                           	insl	%dx, %es:(%edi)
  6c0bc4: 2e 47                        	incl	%edi
  6c0bc6: 65 6e                        	outsb	%gs:(%esi), %dx
  6c0bc8: 65 72 69                     	jb	0x6c0c34 <TMethodImplementationIntercept+0x24b71c>
  6c0bcb: 63 73 2e                     	arpl	%si, 0x2e(%ebx)
  6c0bce: 43                           	incl	%ebx
  6c0bcf: 6f                           	outsl	(%esi), %dx
  6c0bd0: 6c                           	insb	%dx, %es:(%edi)
  6c0bd1: 6c                           	insb	%dx, %es:(%edi)
  6c0bd2: 65 63 74 69 6f               	arpl	%si, %gs:0x6f(%ecx,%ebp,2)
  6c0bd7: 6e                           	outsb	(%esi), %dx
  6c0bd8: 73 00                        	jae	0x6c0bda <TMethodImplementationIntercept+0x24b6c2>
  6c0bda: 00 01                        	addb	%al, (%ecx)
  6c0bdc: 00 02                        	addb	%al, (%edx)
  6c0bde: e8 0b 6c 00 02               	calll	0x26c77ee
  6c0be3: 00 02                        	addb	%al, (%edx)
  6c0be5: 00 00                        	addb	%al, (%eax)
  6c0be7: 00 9c 10 40 00 58 5c         	addb	%bl, 0x5c580040(%eax,%edx)
  6c0bee: 6c                           	insb	%dx, %es:(%edi)
  6c0bef: 00 00                        	addb	%al, (%eax)
  6c0bf1: 00 00                        	addb	%al, (%eax)
  6c0bf3: 00 01                        	addb	%al, (%ecx)
  6c0bf5: 00 00                        	addb	%al, (%eax)
  6c0bf7: 00 00                        	addb	%al, (%eax)
  6c0bf9: 00 00                        	addb	%al, (%eax)
  6c0bfb: 80 00 00                     	addb	$0x0, (%eax)
  6c0bfe: 00 80 ff ff 05 43            	addb	%al, 0x4305ffff(%eax)
  6c0c04: 6f                           	outsl	(%esi), %dx
  6c0c05: 75 6e                        	jne	0x6c0c75 <TMethodImplementationIntercept+0x24b75d>
  6c0c07: 74 60                        	je	0x6c0c69 <TMethodImplementationIntercept+0x24b751>
  6c0c09: 0c 6c                        	orb	$0x6c, %al
		...
  6c0c17: 00 54 0d 6c                  	addb	%dl, 0x6c(%ebp,%ecx)
  6c0c1b: 00 68 0c                     	addb	%ch, 0xc(%eax)
  6c0c1e: 6c                           	insb	%dx, %es:(%edi)
  6c0c1f: 00 99 0c 6c 00 00            	addb	%bl, 0x6c0c(%ecx)
  6c0c25: 00 00                        	addb	%al, (%eax)
  6c0c27: 00 af 0c 6c 00 10            	addb	%ch, 0x10006c0c(%edi)
  6c0c2d: 00 00                        	addb	%al, (%eax)
  6c0c2f: 00 c8                        	addb	%cl, %al
  6c0c31: 7d 45                        	jge	0x6c0c78 <TMethodImplementationIntercept+0x24b760>
  6c0c33: 00 04 a8                     	addb	%al, (%eax,%ebp,4)
  6c0c36: 40                           	incl	%eax
  6c0c37: 00 0c a8                     	addb	%cl, (%eax,%ebp,4)
  6c0c3a: 40                           	incl	%eax
  6c0c3b: 00 2c ab                     	addb	%ch, (%ebx,%ebp,4)
  6c0c3e: 40                           	incl	%eax
  6c0c3f: 00 24 ab                     	addb	%ah, (%ebx,%ebp,4)
  6c0c42: 40                           	incl	%eax
  6c0c43: 00 44 ab 40                  	addb	%al, 0x40(%ebx,%ebp,4)
  6c0c47: 00 48 ab                     	addb	%cl, -0x55(%eax)
  6c0c4a: 40                           	incl	%eax
  6c0c4b: 00 4c ab 40                  	addb	%cl, 0x40(%ebx,%ebp,4)
  6c0c4f: 00 40 ab                     	addb	%al, -0x55(%eax)
  6c0c52: 40                           	incl	%eax
  6c0c53: 00 c4                        	addb	%al, %ah
  6c0c55: a5                           	movsl	(%esi), %es:(%edi)
  6c0c56: 40                           	incl	%eax
  6c0c57: 00 e0                        	addb	%ah, %al
  6c0c59: a5                           	movsl	(%esi), %es:(%edi)
  6c0c5a: 40                           	incl	%eax
  6c0c5b: 00 cc                        	addb	%cl, %ah
  6c0c5d: a6                           	cmpsb	%es:(%edi), (%esi)
  6c0c5e: 40                           	incl	%eax
  6c0c5f: 00 00                        	addb	%al, (%eax)
  6c0c61: 5e                           	popl	%esi
  6c0c62: 6c                           	insb	%dx, %es:(%edi)
  6c0c63: 00 14 5e                     	addb	%dl, (%esi,%ebx,2)
  6c0c66: 6c                           	insb	%dx, %es:(%edi)
  6c0c67: 00 00                        	addb	%al, (%eax)
  6c0c69: 00 00                        	addb	%al, (%eax)
  6c0c6b: 00 00                        	addb	%al, (%eax)
  6c0c6d: 00 02                        	addb	%al, (%edx)
  6c0c6f: 00 00                        	addb	%al, (%eax)
  6c0c71: b0 18                        	movb	$0x18, %al
  6c0c73: 6c                           	insb	%dx, %es:(%edi)
  6c0c74: 00 04 00                     	addb	%al, (%eax,%eax)
  6c0c77: 00 00                        	addb	%al, (%eax)
  6c0c79: 0b 46 44                     	orl	0x44(%esi), %eax
  6c0c7c: 69 63 74 69 6f 6e 61         	imull	$0x616e6f69, 0x74(%ebx), %esp # imm = 0x616E6F69
  6c0c83: 72 79                        	jb	0x6c0cfe <TMethodImplementationIntercept+0x24b7e6>
  6c0c85: 02 00                        	addb	(%eax), %al
  6c0c87: 00 9c 10 40 00 08 00         	addb	%bl, 0x80040(%eax,%edx)
  6c0c8e: 00 00                        	addb	%al, (%eax)
  6c0c90: 06                           	pushl	%es
  6c0c91: 46                           	incl	%esi
  6c0c92: 49                           	decl	%ecx
  6c0c93: 6e                           	outsb	(%esi), %dx
  6c0c94: 64 65 78 02                  	js	0x6c0c9a <TMethodImplementationIntercept+0x24b782>
  6c0c98: 00 00                        	addb	%al, (%eax)
  6c0c9a: 00 02                        	addb	%al, (%edx)
  6c0c9c: 00 eb                        	addb	%ch, %bl
  6c0c9e: 0c 6c                        	orb	$0x6c, %al
  6c0ca0: 00 44 00 f4                  	addb	%al, -0xc(%eax,%eax)
  6c0ca4: ff 26                        	jmpl	*(%esi)
  6c0ca6: 0d 6c 00 42 00               	orl	$0x42006c, %eax         # imm = 0x42006C
  6c0cab: f4                           	hlt
  6c0cac: ff 02                        	incl	(%edx)
  6c0cae: 00 3b                        	addb	%bh, (%ebx)
  6c0cb0: 54                           	pushl	%esp
  6c0cb1: 44                           	incl	%esp
  6c0cb2: 69 63 74 69 6f 6e 61         	imull	$0x616e6f69, 0x74(%ebx), %esp # imm = 0x616E6F69
  6c0cb9: 72 79                        	jb	0x6c0d34 <TMethodImplementationIntercept+0x24b81c>
  6c0cbb: 3c 53                        	cmpb	$0x53, %al
  6c0cbd: 79 73                        	jns	0x6c0d32 <TMethodImplementationIntercept+0x24b81a>
  6c0cbf: 74 65                        	je	0x6c0d26 <TMethodImplementationIntercept+0x24b80e>
  6c0cc1: 6d                           	insl	%dx, %es:(%edi)
  6c0cc2: 2e 50                        	pushl	%eax
  6c0cc4: 6f                           	outsl	(%esi), %dx
  6c0cc5: 69 6e 74 65 72 2c 53         	imull	$0x532c7265, 0x74(%esi), %ebp # imm = 0x532C7265
  6c0ccc: 79 73                        	jns	0x6c0d41 <TMethodImplementationIntercept+0x24b829>
  6c0cce: 74 65                        	je	0x6c0d35 <TMethodImplementationIntercept+0x24b81d>
  6c0cd0: 6d                           	insl	%dx, %es:(%edi)
  6c0cd1: 2e 50                        	pushl	%eax
  6c0cd3: 6f                           	outsl	(%esi), %dx
  6c0cd4: 69 6e 74 65 72 3e 2e         	imull	$0x2e3e7265, 0x74(%esi), %ebp # imm = 0x2E3E7265
  6c0cdb: 54                           	pushl	%esp
  6c0cdc: 56                           	pushl	%esi
  6c0cdd: 61                           	popal
  6c0cde: 6c                           	insb	%dx, %es:(%edi)
  6c0cdf: 75 65                        	jne	0x6c0d46 <TMethodImplementationIntercept+0x24b82e>
  6c0ce1: 45                           	incl	%ebp
  6c0ce2: 6e                           	outsb	(%esi), %dx
  6c0ce3: 75 6d                        	jne	0x6c0d52 <TMethodImplementationIntercept+0x24b83a>
  6c0ce5: 65 72 61                     	jb	0x6c0d49 <TMethodImplementationIntercept+0x24b831>
  6c0ce8: 74 6f                        	je	0x6c0d59 <TMethodImplementationIntercept+0x24b841>
  6c0cea: 72 3b                        	jb	0x6c0d27 <TMethodImplementationIntercept+0x24b80f>
  6c0cec: 00 1c 5e                     	addb	%bl, (%esi,%ebx,2)
  6c0cef: 6c                           	insb	%dx, %es:(%edi)
  6c0cf0: 00 06                        	addb	%al, (%esi)
  6c0cf2: 43                           	incl	%ebx
  6c0cf3: 72 65                        	jb	0x6c0d5a <TMethodImplementationIntercept+0x24b842>
  6c0cf5: 61                           	popal
  6c0cf6: 74 65                        	je	0x6c0d5d <TMethodImplementationIntercept+0x24b845>
  6c0cf8: 03 00                        	addl	(%eax), %eax
  6c0cfa: 00 00                        	addb	%al, (%eax)
  6c0cfc: 00 00                        	addb	%al, (%eax)
  6c0cfe: 08 00                        	orb	%al, (%eax)
  6c0d00: 02 08                        	addb	(%eax), %cl
  6c0d02: 50                           	pushl	%eax
  6c0d03: 0d 6c 00 00 00               	orl	$0x6c, %eax
  6c0d08: 04 53                        	addb	$0x53, %al
  6c0d0a: 65 6c                        	insb	%dx, %es:(%edi)
  6c0d0c: 66 02 00                     	addb	(%eax), %al
  6c0d0f: 0a b0 18 6c 00 02            	orb	0x2006c18(%eax), %dh
  6c0d15: 00 0b                        	addb	%cl, (%ebx)
  6c0d17: 41                           	incl	%ecx
  6c0d18: 44                           	incl	%esp
  6c0d19: 69 63 74 69 6f 6e 61         	imull	$0x616e6f69, 0x74(%ebx), %esp # imm = 0x616E6F69
  6c0d20: 72 79                        	jb	0x6c0d9b <TMethodImplementationIntercept+0x24b883>
  6c0d22: 02 00                        	addb	(%eax), %al
  6c0d24: 02 00                        	addb	(%eax), %al
  6c0d26: 28 00                        	subb	%al, (%eax)
  6c0d28: 60                           	pushal
  6c0d29: 5e                           	popl	%esi
  6c0d2a: 6c                           	insb	%dx, %es:(%edi)
  6c0d2b: 00 08                        	addb	%cl, (%eax)
  6c0d2d: 4d                           	decl	%ebp
  6c0d2e: 6f                           	outsl	(%esi), %dx
  6c0d2f: 76 65                        	jbe	0x6c0d96 <TMethodImplementationIntercept+0x24b87e>
  6c0d31: 4e                           	decl	%esi
  6c0d32: 65 78 74                     	js	0x6c0da9 <TMethodImplementationIntercept+0x24b891>
  6c0d35: 03 00                        	addl	(%eax), %eax
  6c0d37: 00 10                        	addb	%dl, (%eax)
  6c0d39: 40                           	incl	%eax
  6c0d3a: 00 08                        	addb	%cl, (%eax)
  6c0d3c: 00 01                        	addb	%al, (%ecx)
  6c0d3e: 08 50 0d                     	orb	%dl, 0xd(%eax)
  6c0d41: 6c                           	insb	%dx, %es:(%edi)
  6c0d42: 00 00                        	addb	%al, (%eax)
  6c0d44: 00 04 53                     	addb	%al, (%ebx,%edx,2)
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
