            ; XREFS(34)
┌ 86: fcn.00ac012c ();
│           0x00ac012c      53             push ebx
│           0x00ac012d      56             push esi
│           0x00ac012e      57             push edi
│           0x00ac012f      8bf0           mov esi, eax
│           0x00ac0131      51             push ecx
│           0x00ac0132      8bca           mov ecx, edx
│           0x00ac0134      a154f2ab00     mov eax, dword [0xabf254]   ; [0xabf254:4]=0xabf2ac
│           0x00ac0139      b201           mov dl, 1
│           0x00ac013b      e848a40000     call fcn.00aca588
│           0x00ac0140      8bf8           mov edi, eax
│           0x00ac0142      89beac060100   mov dword [esi + 0x106ac], edi ; [0x106ac:4]=-1
│           0x00ac0148      8bc7           mov eax, edi
│           0x00ac014a      e8e106a2ff     call fcn.004e0830
│           0x00ac014f      8bc7           mov eax, edi
│           0x00ac0151      e8a207a2ff     call fcn.004e08f8
│           0x00ac0156      0fb65f2a       movzx ebx, byte [edi + 0x2a]
│           0x00ac015a      8d8698000000   lea eax, [esi + 0x98]
│           0x00ac0160      8b5738         mov edx, dword [edi + 0x38]
│           0x00ac0163      b9ff000000     mov ecx, 0xff               ; 255
│           0x00ac0168      e88bd394ff     call fcn.0040d4f8
│           0x00ac016d      33c0           xor eax, eax
│           0x00ac016f      8986ac060100   mov dword [esi + 0x106ac], eax ; [0x106ac:4]=-1
│           0x00ac0175      8bc7           mov eax, edi
│           0x00ac0177      e860a594ff     call fcn.0040a6dc
│           0x00ac017c      8bc3           mov eax, ebx
│           0x00ac017e      5f             pop edi
│           0x00ac017f      5e             pop esi
│           0x00ac0180      5b             pop ebx
└           0x00ac0181      c3             ret
