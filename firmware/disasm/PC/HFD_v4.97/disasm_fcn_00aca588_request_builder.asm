┌ 118: fcn.00aca588 (int32_t arg_8h);
│ `- args(sp[0x4..0x4]) vars(1:sp[0x1c..0x1c])
│           0x00aca588      55             push ebp
│           0x00aca589      8bec           mov ebp, esp
│           0x00aca58b      83c4e8         add esp, 0xffffffe8
│           0x00aca58e      53             push ebx
│           0x00aca58f      56             push esi
│           0x00aca590      57             push edi
│           0x00aca591      84d2           test dl, dl
│       ┌─< 0x00aca593      7408           je 0xaca59d
│       │   0x00aca595      83c4f0         add esp, 0xfffffff0
│       │   0x00aca598      e82b0894ff     call 0x40adc8
│       └─> 0x00aca59d      8bf1           mov esi, ecx
│           0x00aca59f      8bda           mov ebx, edx
│           0x00aca5a1      8bf8           mov edi, eax
│           0x00aca5a3      b101           mov cl, 1
│           0x00aca5a5      33d2           xor edx, edx
│           0x00aca5a7      8bc7           mov eax, edi
│           0x00aca5a9      e83655a1ff     call 0x4dfae4
│           0x00aca5ae      33d2           xor edx, edx
│           0x00aca5b0      8bc7           mov eax, edi
│           0x00aca5b2      e8655ba1ff     call 0x4e011c
│           0x00aca5b7      8d45e8         lea eax, [var_18h]
│           0x00aca5ba      e829319dff     call 0x49d6e8
│           0x00aca5bf      56             push esi
│           0x00aca5c0      57             push edi
│           0x00aca5c1      8d75e8         lea esi, [var_18h]
│           0x00aca5c4      83c740         add edi, 0x40               ; 64
│           0x00aca5c7      b906000000     mov ecx, 6
│           0x00aca5cc      f3a5           rep movsd dword es:[edi], dword [esi]
│           0x00aca5ce      5f             pop edi
│           0x00aca5cf      5e             pop esi
│           0x00aca5d0      8b4508         mov eax, dword [arg_8h]
│           0x00aca5d3      89472c         mov dword [edi + 0x2c], eax
│           0x00aca5d6      c6472a00       mov byte [edi + 0x2a], 0
│           0x00aca5da      66897728       mov word [edi + 0x28], si
│           0x00aca5de      8bc7           mov eax, edi
│           0x00aca5e0      84db           test bl, bl
│       ┌─< 0x00aca5e2      740f           je 0xaca5f3
│       │   0x00aca5e4      e8370894ff     call 0x40ae20
│       │   0x00aca5e9      648f050000..   pop dword fs:[0]
│       │   0x00aca5f0      83c40c         add esp, 0xc
│       └─> 0x00aca5f3      8bc7           mov eax, edi
│           0x00aca5f5      5f             pop edi
│           0x00aca5f6      5e             pop esi
│           0x00aca5f7      5b             pop ebx
│           0x00aca5f8      8be5           mov esp, ebp
│           0x00aca5fa      5d             pop ebp
└           0x00aca5fb      c20400         ret 4
