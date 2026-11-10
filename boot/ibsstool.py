"""Herramientas para leer el iBSS (base 0x34000000, Thumb-2)."""
import sys, struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
B = open(r"C:\Users\fasce\Documents\PROYECTOS\Apple-TV\emu\ibss_raw.bin", "rb").read()
BASE = 0x34000000
md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)

def one(a):
    for x in md.disasm(B[a - BASE:a - BASE + 4], a):
        return x

def dis(a, n):
    out = []
    while len(out) < n:
        x = one(a)
        if not x:
            out.append("%08x: ??" % a); a += 2; continue
        ex = ""
        if x.mnemonic.startswith("ldr") and "[pc" in x.op_str:
            try:
                off = int(x.op_str.split("#")[1].rstrip("]"), 0)
                la = ((a + 4) & ~3) + off - BASE
                ex = " ; =%#x" % struct.unpack("<I", B[la:la + 4])[0]
            except Exception:
                pass
        out.append("%08x: %-8s %s%s" % (a, x.mnemonic, x.op_str, ex))
        a += x.size
    return out

def lits(v):
    p = struct.pack("<I", v)
    return [BASE + i for i in range(0, len(B) - 3, 4) if B[i:i + 4] == p]

def loads(litaddr):
    r = []
    for a in range(BASE, BASE + len(B) - 4, 2):
        x = one(a)
        if x and x.mnemonic.startswith("ldr") and "[pc" in x.op_str:
            try:
                off = int(x.op_str.split("#")[1].rstrip("]"), 0)
                if ((a + 4) & ~3) + off == litaddr:
                    r.append(a)
            except Exception:
                pass
    return r

def movw_imm(v16):
    """instrucciones movw/movt con un inmediato dado"""
    r = []
    for a in range(BASE, BASE + len(B) - 4, 2):
        x = one(a)
        if x and x.mnemonic in ("movw", "movt", "mov.w", "movs", "cmp", "cmp.w") and ("#%#x" % v16) in x.op_str:
            r.append((hex(a), x.mnemonic, x.op_str))
    return r

def callers(t):
    r = []
    for a in range(BASE, BASE + len(B) - 4, 2):
        x = one(a)
        if x and x.mnemonic in ("bl", "blx") and x.op_str == "#%#x" % t:
            r.append(a)
    return r

def func(a):
    for b in range(a, a - 0x800, -2):
        x = one(b)
        if x and x.mnemonic.startswith("push") and "lr" in x.op_str:
            return b

if __name__ == "__main__":
    c = sys.argv[1]
    if c == "dis": print("\n".join(dis(int(sys.argv[2], 0), int(sys.argv[3]))))
    elif c == "lits": print([hex(x) for x in lits(int(sys.argv[2], 0))])
    elif c == "loads": print([(hex(x), hex(func(x) or 0)) for x in loads(int(sys.argv[2], 0))])
    elif c == "imm": print(movw_imm(int(sys.argv[2], 0)))
    elif c == "callers": print([(hex(x), hex(func(x) or 0)) for x in callers(int(sys.argv[2], 0))])
