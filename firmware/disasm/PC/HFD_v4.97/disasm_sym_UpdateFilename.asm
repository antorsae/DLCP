┌ 202: sym.HFD.exe_UpdateFilename ();
│ afv: vars(1:sp[0xb..0xb])
│           0x00ac0c74      53             push ebx
│           0x00ac0c75      56             push esi
│           0x00ac0c76      57             push edi
│           0x00ac0c77      81c400ffffff   add esp, 0xffffff00
│           0x00ac0c7d      8bf0           mov esi, eax
│           0x00ac0c7f      8d3c24         lea edi, [esp]
│           0x00ac0c82      0fb60e         movzx ecx, byte [esi]
│           0x00ac0c85      41             inc ecx
│           0x00ac0c86      f3a4           rep movsb byte es:[edi], byte [esi]
│           0x00ac0c88      8bf2           mov esi, edx
│           0x00ac0c8a      8bc6           mov eax, esi
│           0x00ac0c8c      b201           mov dl, 1
│           0x00ac0c8e      e859f1ffff     call fcn.00abfdec
│           0x00ac0c93      84c0           test al, al
│       ┌─< 0x00ac0c95      7507           jne 0xac0c9e
│       │   0x00ac0c97      33db           xor ebx, ebx
│      ┌──< 0x00ac0c99      e994000000     jmp 0xac0d32
│      │└─> 0x00ac0c9e      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│      │    0x00ac0ca3      c6404500       mov byte [eax + 0x45], 0
│      │    0x00ac0ca7      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│      │    0x00ac0cac      c6404603       mov byte [eax + 0x46], 3
│      │    0x00ac0cb0      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│      │    0x00ac0cb5      c6404709       mov byte [eax + 0x47], 9
│      │    0x00ac0cb9      0fb60424       movzx eax, byte [esp]
│      │    0x00ac0cbd      84c0           test al, al
│      │┌─< 0x00ac0cbf      742c           je 0xac0ced
│      ││   0x00ac0cc1      0fb6c8         movzx ecx, al
│      ││   0x00ac0cc4      83c102         add ecx, 2
│      ││   0x00ac0cc7      83e903         sub ecx, 3
│     ┌───< 0x00ac0cca      7c21           jl 0xac0ced
│     │││   0x00ac0ccc      41             inc ecx
│     │││   0x00ac0ccd      ba03000000     mov edx, 3
│     │││   0x00ac0cd2      8d442401       lea eax, [var_1h]
│    ┌────> 0x00ac0cd6      83fa21         cmp edx, 0x21               ; '!' ; 33
│   ┌─────< 0x00ac0cd9      7d0d           jge 0xac0ce8
│   │╎│││   0x00ac0cdb      0fb618         movzx ebx, byte [eax]
│   │╎│││   0x00ac0cde      8b3de040d700   mov edi, dword [0xd740e0]   ; [0xd740e0:4]=0
│   │╎│││   0x00ac0ce4      885c1745       mov byte [edi + edx + 0x45], bl
│   └─────> 0x00ac0ce8      42             inc edx
│    ╎│││   0x00ac0ce9      40             inc eax
│    ╎│││   0x00ac0cea      49             dec ecx
│    └────< 0x00ac0ceb      75e9           jne 0xac0cd6
│     └─└─> 0x00ac0ced      b964000000     mov ecx, 0x64               ; 'd' ; 100
│      │    0x00ac0cf2      66ba0200       mov dx, 2
│      │    0x00ac0cf6      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│      │    0x00ac0cfb      e82cf4ffff     call 0xac012c
│      │    0x00ac0d00      8bd8           mov ebx, eax
│      │    0x00ac0d02      84db           test bl, bl
│      │┌─< 0x00ac0d04      7415           je 0xac0d1b
│      ││   0x00ac0d06      8bc6           mov eax, esi
│      ││   0x00ac0d08      8b15e040d700   mov edx, dword [0xd740e0]   ; [0xd740e0:4]=0
│      ││   0x00ac0d0e      81c298000000   add edx, 0x98               ; 152
│      ││   0x00ac0d14      e81fc094ff     call fcn.0040cd38
│     ┌───< 0x00ac0d19      eb0e           jmp 0xac0d29
│     ││└─> 0x00ac0d1b      56             push esi
│     ││    0x00ac0d1c      8bfe           mov edi, esi
│     ││    0x00ac0d1e      be400dac00     mov esi, 0xac0d40
│     ││    0x00ac0d23      a5             movsd dword es:[edi], dword [esi]
│     ││    0x00ac0d24      a5             movsd dword es:[edi], dword [esi]
│     ││    0x00ac0d25      a5             movsd dword es:[edi], dword [esi]
│     ││    0x00ac0d26      a5             movsd dword es:[edi], dword [esi]
│     ││    0x00ac0d27      a4             movsb byte es:[edi], byte [esi]
│     ││    0x00ac0d28      5e             pop esi
│     ││    ; CODE XREF from sym.HFD.exe_UpdateFilename @ 0xac0d19(x)
│     └───> 0x00ac0d29      8bd6           mov edx, esi
│      │    0x00ac0d2b      8bc3           mov eax, ebx
│      │    0x00ac0d2d      e8e6f1ffff     call 0xabff18
│      │    ; CODE XREF from sym.HFD.exe_UpdateFilename @ 0xac0c99(x)
│      └──> 0x00ac0d32      8bc3           mov eax, ebx
│           0x00ac0d34      81c400010000   add esp, 0x100
│           0x00ac0d3a      5f             pop edi
│           0x00ac0d3b      5e             pop esi
│           0x00ac0d3c      5b             pop ebx
└           0x00ac0d3d      c3             ret
