# -*- coding: utf-8 -*-
# Python 2.7, desde ~/ipwndfu con la Apple TV en pwned DFU.
# Arranca un iBSS sin la verificacion de firma.
# v2: salta SIN apagar el USB de la bootrom (0x4E9C/0x71AC hace free() sobre el heap que dejo
#     roto el exploit y la bootrom hacia panic -> reinicio -> modo recuperacion). Verificado en el emulador.
import sys, struct
sys.path.insert(0, '.')
import usbexec

TRAMP = 0x34039A00
LOAD  = 0x34000000
SRC   = 0x34000100

def img3_data(path):
    b = open(path, 'rb').read()
    assert b[:4] == '3gmI', 'no es IMG3'
    off = 20
    while off + 12 <= len(b):
        magic, total, dlen = struct.unpack('<4sII', b[off:off + 12])
        if magic[::-1] == 'DATA':
            return b[off + 12:off + 12 + dlen]
        off += total
    raise SystemExit('sin DATA')

def build(prog):
    lits, idx = [], {}
    for ins in prog:
        if ins[0] == 'ldr' and ins[2] not in idx:
            idx[ins[2]] = len(lits); lits.append(ins[2])
    n, words = len(prog), []
    for i, ins in enumerate(prog):
        if ins[0] == 'ldr':
            imm = n * 4 + idx[ins[2]] * 4 - (i * 4 + 8)
            words.append(0xE59F0000 | (ins[1] << 12) | imm)
        elif ins[0] == 'blx':  words.append(0xE12FFF30 | ins[1])
        elif ins[0] == 'mov0': words.append(0xE3A00000 | (ins[1] << 12))
        elif ins[0] == 'movr': words.append(0xE1A00000 | (ins[1] << 12) | ins[2])
        elif ins[0] == 'raw':  words.append(ins[1])
    return ''.join(struct.pack('<I', w) for w in words + lits)

def trampoline(length):
    prog = [('ldr', 0, LOAD), ('ldr', 1, SRC), ('ldr', 2, length),
            ('raw', 0xE4913004), ('raw', 0xE4803004), ('raw', 0xE2522004), ('raw', 0x1AFFFFFB),
            ('ldr', 5, 0x6C75), ('blx', 5), ('movr', 8, 0),
            ('mov0', 0), ('ldr', 4, 0x5B7D), ('blx', 4),
            ('mov0', 0), ('ldr', 4, 0x4EB1), ('blx', 4),
            ('ldr', 4, 0xD89), ('blx', 4),
            ('ldr', 4, 0x5A89), ('blx', 4),
            ('ldr', 4, 0x6055), ('blx', 4),
            ('ldr', 4, 0x6C45), ('blx', 4),
            ('ldr', 0, LOAD), ('mov0', 1), ('mov0', 2), ('mov0', 3),
            ('blx', 8), ('raw', 0xEAFFFFFE)]
    return build(prog)

ibss = img3_data(sys.argv[1])
ibss += '\0' * ((-len(ibss)) % 4)
old, new = '(DFU Mode)', '(BAUT MOD)'
n = ibss.count(old)
ibss = ibss.replace(old, new)
print 'textos "%s" reemplazados: %d' % (old, n)
# Parche de firma (validado en el emulador): en 0x34005E6E, "bl validar_firma_IMG3" -> "movs r0,#0; nop".
# Asi el iBSS acepta un iBEC sin firma.
OFF = 0x5E6E
assert ibss[OFF:OFF + 4] == '\xff\xf7\x99\xfd', 'el iBSS no es el esperado (12H1006)'
ibss = ibss[:OFF] + '\x00\x20\x00\xbf' + ibss[OFF + 4:]
print 'parche de firma aplicado en %#x' % (0x34000000 + OFF)

tr = trampoline(len(ibss))
dev = usbexec.PwnedUSBDevice()
dev.write_memory(TRAMP, tr)
assert dev.read_memory(TRAMP, len(tr)) == tr, 'el trampolin no quedo escrito'
print 'trampolin v2 escrito y verificado en %#x (%d bytes)' % (TRAMP, len(tr))

blob = '\0' * (SRC - LOAD - 0x10) + ibss
print 'saltando al iBSS...'
try:
    dev.execute(0, TRAMP, blob)
except Exception as e:
    print '(esperado: la Apple TV deja de responder al saltar)', e
