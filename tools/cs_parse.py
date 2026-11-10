"""Parsea el SuperBlob de firma de un Mach-O (LC_CODE_SIGNATURE)."""
import sys, struct

d = open(sys.argv[1], 'rb').read()
magic0 = struct.unpack('>I', d[:4])[0]
endian = '>' if magic0 in (0xFEEDFACE, 0xFEEDFACF) else '<'
is64 = magic0 in (0xFEEDFACF, 0xCFFAEDFE)
ncmds = struct.unpack(endian + 'I', d[16:20])[0]
off = 32 if is64 else 28
sig_off = sig_len = None
for _ in range(ncmds):
    if off + 8 > len(d):
        break
    cmd, size = struct.unpack(endian + 'II', d[off:off + 8])
    if cmd == 0x1d:
        sig_off, sig_len = struct.unpack(endian + 'II', d[off + 8:off + 16])
        break
    off += size
if sig_off is None:
    print('sin firma')
    sys.exit(0)
print('LC_CODE_SIGNATURE: offset', sig_off, 'len', sig_len)
blob = d[sig_off:sig_off + sig_len]
magic = struct.unpack('>I', blob[:4])[0]
print('SuperBlob magic:', hex(magic), '(0xfade0cc0 = valido)')
count = struct.unpack('>I', blob[8:12])[0]
print('blobs:', count)
for i in range(count):
    t, o = struct.unpack('>II', blob[12 + 8 * i:20 + 8 * i])
    l = struct.unpack('>I', blob[o:o + 4])[0]
    print('  blob tipo', hex(t), 'offset', o, 'len', l)
    sub = blob[o:o + l]
    if t == 0xfade0c02:  # CodeDirectory
        print('    CodeDirectory version:', hex(struct.unpack('>I', sub[8:12])[0]))
        flags = struct.unpack('>I', sub[12:16])[0]
        print('    flags:', hex(flags), '(0x2 = adhoc)')
        ident_off = struct.unpack('>I', sub[16:20])[0]
        end = sub.find(b'\0', ident_off)
        print('    ident:', sub[ident_off:end])
    elif t == 0x10000:
        print('    CMS (firma de certificado de Apple) PRESENTE, len', l)
