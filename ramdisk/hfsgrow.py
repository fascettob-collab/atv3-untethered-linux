"""Agranda una imagen HFS+ (sin journal) agregando bloques libres al final.
Sirve mientras el bitmap de asignación alcance (1 bloque de 4 KB = hasta 32768 bloques = 128 MB).
También saca el "software lock" para que Linux la monte en lectura/escritura.
  python hfsgrow.py entrada.hfs salida.hfs MEGAS
"""
import sys, struct

def grow(src, dst, megas):
    d = bytearray(open(src, "rb").read())
    vh = d[0x400:0x600]
    assert vh[:2] == b"H+"
    attrs, = struct.unpack(">I", vh[4:8])
    assert not attrs & 0x2000, "tiene journal"
    bs, total, free = struct.unpack(">III", vh[0x28:0x34])
    assert len(d) == bs * total
    alloc_logical = struct.unpack(">Q", vh[0x70:0x78])[0]
    alloc_start = struct.unpack(">I", vh[0x80:0x84])[0]
    new_total = megas * 1024 * 1024 // bs
    assert total < new_total <= alloc_logical * 8, "el bitmap no alcanza"

    bitmap_off = alloc_start * bs
    def setbit(n, v):
        byte, bit = bitmap_off + n // 8, 7 - n % 8
        if v: d[byte] |= 1 << bit
        else: d[byte] &= ~(1 << bit) & 0xFF
    def getbit(n):
        return (d[bitmap_off + n // 8] >> (7 - n % 8)) & 1

    # el último bloque viejo guardaba la copia alternativa de la cabecera: queda libre
    d[(total * bs) - 1024:(total * bs) - 512] = b"\0" * 512
    d += b"\0" * ((new_total - total) * bs)
    assert getbit(total - 1) == 1
    setbit(total - 1, 0)
    for n in range(total, new_total):
        setbit(n, 0)
    setbit(new_total - 1, 1)      # el nuevo último bloque guarda la cabecera alternativa
    new_free = free + (new_total - total)

    attrs &= ~0x80000000          # kHFSVolumeSoftwareLockBit
    attrs |= 0x100                # desmontado limpio
    struct.pack_into(">I", d, 0x404, attrs)
    struct.pack_into(">II", d, 0x42C, new_total, new_free)
    alt = len(d) - 1024
    d[alt:alt + 512] = d[0x400:0x600]
    open(dst, "wb").write(d)
    print("%s: %d -> %d bloques (%d MB), libres %d" % (dst, total, new_total, len(d) >> 20, new_free))

if __name__ == "__main__":
    grow(sys.argv[1], sys.argv[2], int(sys.argv[3]))
