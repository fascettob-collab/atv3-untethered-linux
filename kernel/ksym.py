"""Símbolos y desensamblado del kernel de tvOS (kernel.macho, ARMv7, base 0x80001000)."""
import struct, sys
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
K = open(r"C:\Users\fasce\Documents\PROYECTOS\Apple-TV\emu\kernel.macho", "rb").read()

def segments():
    ncmds = struct.unpack("<I", K[16:20])[0]; off = 28; segs = []; sym = None
    for _ in range(ncmds):
        cmd, sz = struct.unpack("<II", K[off:off + 8])
        if cmd == 1:
            name = K[off + 8:off + 24].split(b"\0")[0].decode()
            va, vs, fo, fs = struct.unpack("<IIII", K[off + 24:off + 40])
            segs.append((name, va, vs, fo, fs))
        if cmd == 2:
            sym = struct.unpack("<IIII", K[off + 8:off + 24])
        off += sz
    return segs, sym

SEGS, SYM = segments()

def va2off(va):
    for name, a, s, fo, fs in SEGS:
        if a <= va < a + fs:
            return fo + (va - a)

def symbols():
    symoff, nsyms, stroff, strsize = SYM
    out = {}
    for i in range(nsyms):
        n_strx, n_type, n_sect, n_desc, n_value = struct.unpack("<IBBHI", K[symoff + i * 12:symoff + i * 12 + 12])
        name = K[stroff + n_strx:K.index(b"\0", stroff + n_strx)].decode("latin-1")
        out[name] = n_value
    return out

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
def dis(va, n):
    va &= ~1
    o = va2off(va)
    res = []
    for ins in md.disasm(K[o:o + n * 4], va):
        res.append("%08x: %-8s %s" % (ins.address, ins.mnemonic, ins.op_str))
        if len(res) >= n:
            break
    return res

if __name__ == "__main__":
    S = symbols()
    if sys.argv[1] == "find":
        for k, v in S.items():
            if sys.argv[2].lower() in k.lower():
                print(hex(v), k)
    elif sys.argv[1] == "dis":
        a = S.get(sys.argv[2]) or int(sys.argv[2], 0)
        print("\n".join(dis(a, int(sys.argv[3]))))
