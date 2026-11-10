"""Lista las dependencias (LC_LOAD_DYLIB / LC_LOAD_WEAK_DYLIB) de un Mach-O.
  python macho_deps.py archivo [archivo2 ...]
"""
import sys, struct

def deps(path):
    d = open(path, "rb").read()
    magic = struct.unpack(">I", d[:4])[0]
    if magic in (0xFEEDFACE, 0xFEEDFACF):          # big endian 32/64
        e = ">"
    elif magic in (0xCEFAEDFE, 0xCFFAEDFE):        # little endian 32/64
        e = "<"
    else:
        print(path, "no es Mach-O:", hex(magic))
        return
    ncmds = struct.unpack(e + "I", d[16:20])[0]
    off = 28 if magic in (0xFEEDFACE, 0xCEFAEDFE) else 32
    for _ in range(ncmds):
        cmd, size = struct.unpack(e + "II", d[off:off + 8])
        if cmd in (0xc, 0x18):
            nameoff = struct.unpack(e + "I", d[off + 8:off + 12])[0]
            name = d[off + nameoff:off + size].split(b"\0")[0].decode("utf-8", "replace")
            print("%-6s %s" % ("weak" if cmd == 0x18 else "load", name))
        off += size

if __name__ == "__main__":
    for p in sys.argv[1:]:
        print("==", p)
        deps(p)
