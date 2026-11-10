"""Verifica si un Mach-O tiene LC_CODE_SIGNATURE y qué load commands trae."""
import sys, struct

d = open(sys.argv[1], 'rb').read()
magic = struct.unpack('>I', d[:4])[0]
e = '>' if magic in (0xFEEDFACE, 0xFEEDFACF) else '<'
ncmds = struct.unpack(e + 'I', d[16:20])[0]
off = 28 if magic in (0xFEEDFACE, 0xCEFAEDFE) else 32
for _ in range(ncmds):
    cmd, size = struct.unpack(e + 'II', d[off:off + 8])
    name = {0xc: 'LC_LOAD_DYLIB', 0x1d: 'LC_CODE_SIGNATURE', 0x19: 'LC_UUID', 0x21: 'LC_ENCRYPTION_INFO'}.get(cmd, hex(cmd))
    print(name, 'size', size)
    if cmd == 0x1d:
        datasize = struct.unpack(e + 'I', d[off + 12:off + 16])[0]
        print('  >> FIRMA PRESENTE, datasize', datasize)
        print('  >> primeros 32 bytes:', d[off + 16:off + 48].hex(' '))
    off += size
