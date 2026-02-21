┌ 145: sym.HFD.exe_ReadAttachedDSPFilename ();
│           0x00ac0d54      53             push ebx
│           0x00ac0d55      56             push esi
│           0x00ac0d56      57             push edi
│           0x00ac0d57      8bf2           mov esi, edx
│           0x00ac0d59      8bf8           mov edi, eax
│           0x00ac0d5b      8bc6           mov eax, esi
│           0x00ac0d5d      b201           mov dl, 1
│           0x00ac0d5f      e888f0ffff     call fcn.00abfdec
│           0x00ac0d64      84c0           test al, al
│       ┌─< 0x00ac0d66      7504           jne 0xac0d6c
│       │   0x00ac0d68      33db           xor ebx, ebx
│      ┌──< 0x00ac0d6a      eb73           jmp 0xac0ddf
│      │└─> 0x00ac0d6c      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│      │    0x00ac0d71      c6404500       mov byte [eax + 0x45], 0
│      │    0x00ac0d75      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│      │    0x00ac0d7a      c6404603       mov byte [eax + 0x46], 3
│      │    0x00ac0d7e      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│      │    0x00ac0d83      c6404708       mov byte [eax + 0x47], 8
│      │    0x00ac0d87      b964000000     mov ecx, 0x64               ; 'd' ; 100
│      │    0x00ac0d8c      66ba0200       mov dx, 2
│      │    0x00ac0d90      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│      │    0x00ac0d95      e892f3ffff     call 0xac012c
│      │    0x00ac0d9a      8bd8           mov ebx, eax
│      │    0x00ac0d9c      84db           test bl, bl
│      │┌─< 0x00ac0d9e      7428           je 0xac0dc8
│      ││   0x00ac0da0      8bc7           mov eax, edi
│      ││   0x00ac0da2      8b15e040d700   mov edx, dword [0xd740e0]   ; [0xd740e0:4]=0
│      ││   0x00ac0da8      81c2ac030100   add edx, 0x103ac
│      ││   0x00ac0dae      e885bf94ff     call fcn.0040cd38
│      ││   0x00ac0db3      8bc6           mov eax, esi
│      ││   0x00ac0db5      8b15e040d700   mov edx, dword [0xd740e0]   ; [0xd740e0:4]=0
│      ││   0x00ac0dbb      81c298000000   add edx, 0x98               ; 152
│      ││   0x00ac0dc1      e872bf94ff     call fcn.0040cd38
│     ┌───< 0x00ac0dc6      eb0e           jmp 0xac0dd6
│     ││└─> 0x00ac0dc8      56             push esi
│     ││    0x00ac0dc9      8bfe           mov edi, esi
│     ││    0x00ac0dcb      bee80dac00     mov esi, 0xac0de8
│     ││    0x00ac0dd0      a5             movsd dword es:[edi], dword [esi]
│     ││    0x00ac0dd1      a5             movsd dword es:[edi], dword [esi]
│     ││    0x00ac0dd2      a5             movsd dword es:[edi], dword [esi]
│     ││    0x00ac0dd3      a5             movsd dword es:[edi], dword [esi]
│     ││    0x00ac0dd4      a4             movsb byte es:[edi], byte [esi]
│     ││    0x00ac0dd5      5e             pop esi
│     ││    ; CODE XREF from sym.HFD.exe_ReadAttachedDSPFilename @ 0xac0dc6(x)
│     └───> 0x00ac0dd6      8bd6           mov edx, esi
│      │    0x00ac0dd8      8bc3           mov eax, ebx
│      │    0x00ac0dda      e839f1ffff     call 0xabff18
│      │    ; CODE XREF from sym.HFD.exe_ReadAttachedDSPFilename @ 0xac0d6a(x)
│      └──> 0x00ac0ddf      8bc3           mov eax, ebx
│           0x00ac0de1      5f             pop edi
│           0x00ac0de2      5e             pop esi
│           0x00ac0de3      5b             pop ebx
└           0x00ac0de4      c3             ret
