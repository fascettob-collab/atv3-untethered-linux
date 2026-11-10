# -*- coding: utf-8 -*-
# Python 2.7, desde ~/ipwndfu. Manda el iBEC (parcheado) al iBSS parcheado por DFU y lo hace arrancar.
# Parches del iBEC 12H1006 (direcciones con base 0x9FF00000):
#   0x9FF18A9E  bl validar_firma_IMG3 -> movs r0,#0; nop   (acepta devicetree/kernel sin firma)
#   0x9FF1A4BC  it ne -> nop                                 (usa siempre la cadena de boot-args de abajo)
#   0x9FF393FB  "rd=md0 nand-enable-reformat=1 -progress" -> "-v"   (arranque en modo texto)
#   marca USB: "(Recovery Mode)" -> "(BAUT IBEC MOD)"
# Uso: sudo python send_ibec.py ~/fw/iBEC.j33i.RELEASE.dfu
import sys, struct, time
sys.path.insert(0, '.')
import usb.core, usb.util, usb.backend.libusb1 as libusb1

import os
# Se puede cambiar con la variable BOOT_ARGS (maximo 39 caracteres: es el lugar de la cadena original).
BOOT_ARGS = os.environ.get('BOOT_ARGS', '-v')
assert len(BOOT_ARGS) <= 39, 'BOOT_ARGS demasiado largo (max 39)'

def crc_table():
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = (c >> 1) ^ 0xEDB88320 if c & 1 else c >> 1
        t.append(c)
    return t

def dfu_suffix(data):
    suf = '\xff\xff\xff\xff\xac\x05\x00\x01UFD\x10'
    t, crc = crc_table(), 0xFFFFFFFF
    for ch in data + suf:
        crc = t[(crc ^ ord(ch)) & 0xFF] ^ (crc >> 8)
    return data + suf + struct.pack('<I', crc)

def data_offset(img3):
    off = 20
    while off + 12 <= len(img3):
        magic, total, dlen = struct.unpack('<4sII', img3[off:off + 12])
        if magic[::-1] == 'DATA':
            return off + 12
        off += total
    raise SystemExit('sin DATA')

def patch(img3, addr, old, new):
    o = data_offset(img3) + (addr - 0x9FF00000)
    assert img3[o:o + len(old)] == old, 'bytes inesperados en %#x' % addr
    assert len(new) == len(old)
    return img3[:o] + new + img3[o + len(old):]

img3 = open(sys.argv[1], 'rb').read()
img3 = patch(img3, 0x9FF18A9E, '\xff\xf7\x4f\xfc', '\x00\x20\x00\xbf')
img3 = patch(img3, 0x9FF1A4BC, '\x18\xbf', '\x00\xbf')
s = 'rd=md0 nand-enable-reformat=1 -progress'
img3 = patch(img3, 0x9FF393FB, s, BOOT_ARGS + '\0' * (len(s) - len(BOOT_ARGS)))
n = img3.count('(Recovery Mode)')
img3 = img3.replace('(Recovery Mode)', '(BAUT IBEC MOD)')
print 'iBEC parcheado: firma, boot-args="%s", marcas: %d' % (BOOT_ARGS, n)
blob = dfu_suffix(img3)

dev = usb.core.find(idVendor=0x5AC, idProduct=0x1227, backend=libusb1.get_backend())
if dev is None:
    raise SystemExit('no encuentro el iBSS (05ac:1227)')
prod = usb.util.get_string(dev, dev.iProduct)
print 'dispositivo:', prod
if 'BAUT MOD' not in prod:
    raise SystemExit('no es el iBSS modificado; primero corre boot_ibss.py')

def getstatus():
    return list(bytearray(dev.ctrl_transfer(0xA1, 3, 0, 0, 6, 2000)))

blk = 0
for i in range(0, len(blob), 0x800):
    dev.ctrl_transfer(0x21, 1, blk, 0, blob[i:i + 0x800], 5000)
    st = getstatus()
    blk += 1
print 'enviados %d bloques, estado %s' % (blk, st)
dev.ctrl_transfer(0x21, 1, blk, 0, '', 5000)
for k in range(10):
    st = getstatus()
    print '  GETSTATUS', st
    if st[4] == 8:
        break
    time.sleep(st[1] / 1000.0 + 0.5 if st[1] else 0.5)
print 'reset USB: el iBSS deberia arrancar el iBEC'
try:
    dev.reset()
except Exception as e:
    print '(normal)', e
