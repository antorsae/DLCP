┌ 194: fcn.004e08f8 ();
│ afv: vars(5:sp[0x24..0x40])
│           0x004e08f8      53             push ebx
│           0x004e08f9      56             push esi
│           0x004e08fa      83c4d8         add esp, 0xffffffd8
│           0x004e08fd      8bf0           mov esi, eax
│           0x004e08ff      807e2400       cmp byte [esi + 0x24], 0
│       ┌─< 0x004e0903      7417           je 0x4e091c
│       │   0x004e0905      8b0d8881d500   mov ecx, dword [0xd58188]   ; [0xd58188:4]=0x41e758
│       │   0x004e090b      b201           mov dl, 1
│       │   0x004e090d      a130a64a00     mov eax, dword [0x4aa630]   ; [0x4aa630:4]=0x4aa688
│       │   0x004e0912      e80941f5ff     call 0x434a20
│       │   0x004e0917      e818b4f2ff     call 0x40bd34
│       └─> 0x004e091c      8b4608         mov eax, dword [esi + 8]
│           0x004e091f      89442404       mov dword [var_4h], eax
│           0x004e0923      e81cf6ffff     call 0x4dff44
│           0x004e0928      8b4004         mov eax, dword [eax + 4]
│           0x004e092b      8b15348bd500   mov edx, dword [0xd58b34]   ; [0xd58b34:4]=0xd59044
│           0x004e0931      3b02           cmp eax, dword [edx]
│       ┌─< 0x004e0933      7558           jne 0x4e098d
│       │   0x004e0935      33db           xor ebx, ebx
│       │   0x004e0937      a1acf4d500     mov eax, dword [0xd5f4ac]   ; [0xd5f4ac:4]=0
│       │   0x004e093c      89442408       mov dword [var_8h_2], eax
│      ┌──> 0x004e0940      83fb02         cmp ebx, 2                  ; 2
│     ┌───< 0x004e0943      7512           jne 0x4e0957
│     │╎│   0x004e0945      6a00           push 0
│     │╎│   0x004e0947      6a00           push 0
│     │╎│   0x004e0949      6a00           push 0
│     │╎│   0x004e094b      6a00           push 0
│     │╎│   0x004e094d      8d44241c       lea eax, [var_1ch]
│     │╎│   0x004e0951      50             push eax
│     │╎│   0x004e0952      e8a5c9f3ff     call 0x41d2fc
│     └───> 0x004e0957      6a40           push 0x40                   ; '@' ; 64
│      ╎│   0x004e0959      68e8030000     push 0x3e8                  ; 1000
│      ╎│   0x004e095e      6a00           push 0
│      ╎│   0x004e0960      8d442410       lea eax, [var_4h]
│      ╎│   0x004e0964      50             push eax
│      ╎│   0x004e0965      6a02           push 2                      ; 2
│      ╎│   0x004e0967      e878c9f3ff     call 0x41d2e4
│      ╎│   0x004e096c      8bd8           mov ebx, eax
│      ╎│   0x004e096e      83fbff         cmp ebx, 0xffffffff
│      ╎│   0x004e0971      0f95c2         setne dl
│      ╎│   0x004e0974      8bc6           mov eax, esi
│      ╎│   0x004e0976      e8b9f4ffff     call 0x4dfe34
│      ╎│   0x004e097b      83fb01         cmp ebx, 1                  ; 1
│     ┌───< 0x004e097e      7507           jne 0x4e0987
│     │╎│   0x004e0980      33c0           xor eax, eax
│     │╎│   0x004e0982      e869edffff     call 0x4df6f0
│     └───> 0x004e0987      85db           test ebx, ebx
│      └──< 0x004e0989      75b5           jne 0x4e0940
│      ┌──< 0x004e098b      eb0c           jmp 0x4e0999
│      │└─> 0x004e098d      6aff           push 0xffffffffffffffff
│      │    0x004e098f      8b442408       mov eax, dword [var_4h]
│      │    0x004e0993      50             push eax
│      │    0x004e0994      e843c0f3ff     call 0x41c9dc
│      │    ; CODE XREF from fcn.004e08f8 @ 0x4e098b(x)
│      └──> 0x004e0999      54             push esp
│           0x004e099a      8b442408       mov eax, dword [var_8h]
│           0x004e099e      50             push eax
│           0x004e099f      e8ccbcf3ff     call 0x41c670
│           0x004e09a4      83f801         cmp eax, 1                  ; 1
│           0x004e09a7      1bd2           sbb edx, edx
│           0x004e09a9      42             inc edx
│           0x004e09aa      8bc6           mov eax, esi
│           0x004e09ac      e883f4ffff     call 0x4dfe34
│           0x004e09b1      8b0424         mov eax, dword [esp]
│           0x004e09b4      83c428         add esp, 0x28
│           0x004e09b7      5e             pop esi
│           0x004e09b8      5b             pop ebx
└           0x004e09b9      c3             ret
