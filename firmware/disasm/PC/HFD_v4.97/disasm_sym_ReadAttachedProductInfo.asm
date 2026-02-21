┌ 224: sym.HFD.exe_ReadAttachedProductInfo (int32_t arg_8h, int32_t arg_ch, int32_t arg_10h, int32_t arg_14h, int32_t arg_18h, int32_t arg_1ch, int32_t arg_20h);
│ `- args(sp[0x4..0x1c]) vars(1:sp[0x8..0x8])
│           0x00ac0b94      55             push ebp
│           0x00ac0b95      8bec           mov ebp, esp
│           0x00ac0b97      51             push ecx
│           0x00ac0b98      53             push ebx
│           0x00ac0b99      56             push esi
│           0x00ac0b9a      57             push edi
│           0x00ac0b9b      894dfc         mov dword [var_4h], ecx
│           0x00ac0b9e      8bfa           mov edi, edx
│           0x00ac0ba0      8bf0           mov esi, eax
│           0x00ac0ba2      8b4514         mov eax, dword [arg_14h]
│           0x00ac0ba5      8b1594d0aa00   mov edx, dword [0xaad094]   ; [0xaad094:4]=0xaad098
│           0x00ac0bab      e89cd394ff     call fcn.0040df4c
│           0x00ac0bb0      833de040d7..   cmp dword [0xd740e0], 0     ; [0xd740e0:4]=0
│           0x00ac0bb7      0f95c3         setne bl
│           0x00ac0bba      84db           test bl, bl
│       ┌─< 0x00ac0bbc      0f84a8000000   je 0xac0c6a
│       │   0x00ac0bc2      8b451c         mov eax, dword [arg_1ch]
│       │   0x00ac0bc5      8b15e040d700   mov edx, dword [0xd740e0]   ; [0xd740e0:4]=0
│       │   0x00ac0bcb      81c2a8010000   add edx, 0x1a8              ; 424
│       │   0x00ac0bd1      e862c194ff     call fcn.0040cd38
│       │   0x00ac0bd6      8b4518         mov eax, dword [arg_18h]
│       │   0x00ac0bd9      8b15e040d700   mov edx, dword [0xd740e0]   ; [0xd740e0:4]=0
│       │   0x00ac0bdf      81c2a8020000   add edx, 0x2a8              ; 680
│       │   0x00ac0be5      e84ec194ff     call fcn.0040cd38
│       │   0x00ac0bea      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│       │   0x00ac0bef      0fb680c006..   movzx eax, byte [eax + 0x106c0]
│       │   0x00ac0bf6      8806           mov byte [esi], al
│       │   0x00ac0bf8      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│       │   0x00ac0bfd      0fb680c106..   movzx eax, byte [eax + 0x106c1]
│       │   0x00ac0c04      8807           mov byte [edi], al
│       │   0x00ac0c06      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│       │   0x00ac0c0b      0fb680c206..   movzx eax, byte [eax + 0x106c2]
│       │   0x00ac0c12      8b55fc         mov edx, dword [var_4h]
│       │   0x00ac0c15      8802           mov byte [edx], al
│       │   0x00ac0c17      8b4508         mov eax, dword [arg_8h]
│       │   0x00ac0c1a      c60000         mov byte [eax], 0
│       │   0x00ac0c1d      8b4514         mov eax, dword [arg_14h]
│       │   0x00ac0c20      8b15e040d700   mov edx, dword [0xd740e0]   ; [0xd740e0:4]=0
│       │   0x00ac0c26      81c2c8060100   add edx, 0x106c8
│       │   0x00ac0c2c      8b0d94d0aa00   mov ecx, dword [0xaad094]   ; [0xaad094:4]=0xaad098
│       │   0x00ac0c32      e8b1dc94ff     call fcn.0040e8e8
│       │   0x00ac0c37      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│       │   0x00ac0c3c      0fb680b807..   movzx eax, byte [eax + 0x107b8]
│       │   0x00ac0c43      8b5510         mov edx, dword [arg_10h]
│       │   0x00ac0c46      8802           mov byte [edx], al
│       │   0x00ac0c48      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│       │   0x00ac0c4d      0fb680c306..   movzx eax, byte [eax + 0x106c3]
│       │   0x00ac0c54      8b5520         mov edx, dword [arg_20h]
│       │   0x00ac0c57      8802           mov byte [edx], al
│       │   0x00ac0c59      a1e040d700     mov eax, dword [0xd740e0]   ; [0xd740e0:4]=0
│       │   0x00ac0c5e      0fb680cc07..   movzx eax, byte [eax + 0x107cc]
│       │   0x00ac0c65      8b550c         mov edx, dword [arg_ch]
│       │   0x00ac0c68      8802           mov byte [edx], al
│       └─> 0x00ac0c6a      8bc3           mov eax, ebx
│           0x00ac0c6c      5f             pop edi
│           0x00ac0c6d      5e             pop esi
│           0x00ac0c6e      5b             pop ebx
│           0x00ac0c6f      59             pop ecx
│           0x00ac0c70      5d             pop ebp
└           0x00ac0c71      c21c00         ret 0x1c
