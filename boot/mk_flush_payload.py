"""Arma payload8947_flush.bin: payload de ipwndfu + un "stub" ARM al final que
1) llama al shellcode original (que deja R4=0 para que no se libere el pedido),
2) deshabilita EP0-IN (EPDIS|SNAK en DIEPCTL0) y vacía los TX FIFO (GRSTCTL TxFFlsh),
3) vuelve a usb_complete.
El callback del overwrite tiene que apuntar a 0x34000000 + len(payload_original).
"""
import struct, base64
P = open(r"C:\Users\fasce\Documents\PROYECTOS\Apple-TV\emu\payload8947.bin", "rb").read()
off = (len(P) + 3) & ~3
P = P + b"\0" * (off - len(P))
stub_addr = 0x34000000 + off

def bl(src, dst):
    imm = ((dst - (src + 8)) >> 2) & 0xFFFFFF
    return 0xEB000000 | imm

code = [
    0xE52DE004,                    # push {lr}
    None,                          # bl 0x34000000 (shellcode)
    0xE3000900, 0xE3430610,        # movw/movt r0, 0x36100900 (DIEPCTL0)
    0xE5901000,                    # ldr r1, [r0]
    0xE3811312,                    # orr r1, r1, #0x48000000 (EPDIS|SNAK)
    0xE5801000,                    # str r1, [r0]
    0xE3000010, 0xE3430610,        # movw/movt r0, 0x36100010 (GRSTCTL)
    0xE3001420,                    # movw r1, #0x420 (TxFNum=todos, TxFFlsh)
    0xE5801000,                    # str r1, [r0]
    0xE5901000,                    # loop: ldr r1, [r0]
    0xE3110020,                    # tst r1, #0x20
    0x1AFFFFFC,                    # bne loop
    0xE49DF004,                    # pop {pc}
]
code[1] = bl(stub_addr + 4, 0x34000000)
blob = P + b"".join(struct.pack("<I", c) for c in code)
open(r"C:\Users\fasce\Documents\PROYECTOS\Apple-TV\emu\payload8947_flush.bin", "wb").write(blob)
print("largo", len(blob), "callback", hex(stub_addr))
print(base64.b64encode(blob).decode())
