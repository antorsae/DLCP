            ; XREFS(43)
┌ 211: fcn.00abfdec ();
│           0x00abfdec      53             push ebx
│           0x00abfded      56             push esi
│           0x00abfdee      57             push edi
│           0x00abfdef      8bf0           mov esi, eax
│           0x00abfdf1      833de040d7..   cmp dword [0xd740e0], 0     ; [0xd740e0:4]=0
│       ┌─< 0x00abfdf8      7516           jne 0xabfe10
│       │   0x00abfdfa      33db           xor ebx, ebx
│       │   0x00abfdfc      8bfe           mov edi, esi
│       │   0x00abfdfe      bec0feab00     mov esi, 0xabfec0           ; "0!USB not initialised (dll.connect() not called?)"
│       │   0x00abfe03      b90c000000     mov ecx, 0xc                ; 12
│       │   0x00abfe08      f3a5           rep movsd dword es:[edi], dword [esi]
│       │   0x00abfe0a      a4             movsb byte es:[edi], byte [esi]
│      ┌──< 0x00abfe0b      e9a9000000     jmp 0xabfeb9
│      │└─> 0x00abfe10      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│      │    0x00abfe15      0fb680a903..   movzx eax, byte [eax + 0x3a9]
│      │    0x00abfe1c      84d0           test al, dl
│      │┌─< 0x00abfe1e      7461           je 0xabfe81
│      ││   0x00abfe20      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│      ││   0x00abfe25      80b8960000..   cmp byte [eax + 0x96], 0
│     ┌───< 0x00abfe2c      742f           je 0xabfe5d
│     │││   0x00abfe2e      33db           xor ebx, ebx
│     │││   0x00abfe30      56             push esi
│     │││   0x00abfe31      8bfe           mov edi, esi
│     │││   0x00abfe33      bef4feab00     mov esi, 0xabfef4           ; "\r!Command busy"
│     │││   0x00abfe38      a5             movsd dword es:[edi], dword [esi]
│     │││   0x00abfe39      a5             movsd dword es:[edi], dword [esi]
│     │││   0x00abfe3a      a5             movsd dword es:[edi], dword [esi]
│     │││   0x00abfe3b      66a5           movsw word es:[edi], word [esi]
│     │││   0x00abfe3d      5e             pop esi
│     │││   0x00abfe3e      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│     │││   0x00abfe43      c680980100..   mov byte [eax + 0x198], 0
│     │││   0x00abfe4a      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│     │││   0x00abfe4f      0598000000     add eax, 0x98               ; 152
│     │││   0x00abfe54      8bd6           mov edx, esi
│     │││   0x00abfe56      e8ddce94ff     call fcn.0040cd38
│    ┌────< 0x00abfe5b      eb5c           jmp 0xabfeb9
│    │└───> 0x00abfe5d      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│    │ ││   0x00abfe62      c680960000..   mov byte [eax + 0x96], 1
│    │ ││   0x00abfe69      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│    │ ││   0x00abfe6e      e8917a0000     call 0xac7904
│    │ ││   0x00abfe73      b301           mov bl, 1
│    │ ││   0x00abfe75      c60600         mov byte [esi], 0
│    │ ││   0x00abfe78      c605e440d7..   mov byte [0xd740e4], 0      ; [0xd740e4:1]=0
│    │┌───< 0x00abfe7f      eb38           jmp 0xabfeb9
│    │││└─> 0x00abfe81      84c0           test al, al
│    │││┌─< 0x00abfe83      752f           jne 0xabfeb4
│    ││││   0x00abfe85      33db           xor ebx, ebx
│    ││││   0x00abfe87      56             push esi
│    ││││   0x00abfe88      8bfe           mov edi, esi
│    ││││   0x00abfe8a      be04ffab00     mov esi, 0xabff04
│    ││││   0x00abfe8f      a5             movsd dword es:[edi], dword [esi]
│    ││││   0x00abfe90      a5             movsd dword es:[edi], dword [esi]
│    ││││   0x00abfe91      a5             movsd dword es:[edi], dword [esi]
│    ││││   0x00abfe92      a5             movsd dword es:[edi], dword [esi]
│    ││││   0x00abfe93      a5             movsd dword es:[edi], dword [esi]
│    ││││   0x00abfe94      5e             pop esi
│    ││││   0x00abfe95      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│    ││││   0x00abfe9a      c680980100..   mov byte [eax + 0x198], 0
│    ││││   0x00abfea1      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│    ││││   0x00abfea6      0598000000     add eax, 0x98               ; 152
│    ││││   0x00abfeab      8bd6           mov edx, esi
│    ││││   0x00abfead      e886ce94ff     call fcn.0040cd38
│   ┌─────< 0x00abfeb2      eb05           jmp 0xabfeb9
│   ││││└─> 0x00abfeb4      b301           mov bl, 1
│   ││││    0x00abfeb6      c60600         mov byte [esi], 0
│   ││││    ; CODE XREFS from fcn.00abfdec @ 0xabfe0b(x), 0xabfe5b(x), 0xabfe7f(x), 0xabfeb2(x)
│   └└└└──> 0x00abfeb9      8bc3           mov eax, ebx
│           0x00abfebb      5f             pop edi
│           0x00abfebc      5e             pop esi
│           0x00abfebd      5b             pop ebx
└           0x00abfebe      c3             ret
