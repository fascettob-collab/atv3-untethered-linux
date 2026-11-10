#!/usr/bin/env python3
"""Envuelve una imagen HFS+ como IMG3 tipo 'rdsk', usando el disco de restauración original como molde
(mismas etiquetas TYPE/VERS/etc., solo cambia DATA y los tamaños de la cabecera).
  python3 wrap_rdsk.py ramdisk_orig.dmg imagen.hfs salida.img3
"""
import sys, struct

def tags(b):
    off, out = 20, []
    while off + 12 <= len(b):
        m, t, d = struct.unpack("<4sII", b[off:off + 12])
        out.append((m[::-1], off, t, d))
        if t == 0:
            break
        off += t
    return out

def wrap(template, hfs, dst):
    t = open(template, "rb").read()
    assert t[:4] == b"3gmI", "el molde no es IMG3"
    assert t[16:20] == b"ksdr", "el molde no es tipo rdsk"
    data = open(hfs, "rb").read()
    assert data[0x400:0x402] == b"H+", "la imagen no es HFS+"
    out = bytearray(t[:20])
    for m, off, total, dlen in tags(t):
        if m == b"DATA":
            pad = (-len(data)) % 4
            out += struct.pack("<4sII", b"ATAD", 12 + len(data) + pad, len(data)) + data + b"\0" * pad
        else:
            out += t[off:off + total]
    n = len(out)
    struct.pack_into("<III", out, 4, n, n - 20, n - 20)
    open(dst, "wb").write(out)
    print("%s: %d bytes (HFS+ de %d MB)" % (dst, n, len(data) >> 20))

if __name__ == "__main__":
    wrap(sys.argv[1], sys.argv[2], sys.argv[3])
