# -*- coding: utf-8 -*-
# Python 2.7, desde ~/ipwndfu. Plan B para ver el arranque en texto:
# en vez del iBEC (que no prende el HDMI), mandamos el iBoot "normal" (el que muestra el logo y
# arranca tvOS desde la memoria interna), haciendolo pasar por iBEC para que el iBSS parcheado lo acepte.
# Parches del iBoot 12H1006 (base 0x9FF00000):
#   tipo IMG3 'ibot' -> 'ibec'                    (el iBSS solo carga imagenes tipo iBEC)
#   0x9FF1CB94  it ne -> nop                       (usar siempre la cadena de boot-args)
#   0x9FF3C87B  "rd=md0 nand-enable-reformat=1 -progress" -> "-v"
#   marca USB: "(Recovery Mode)" -> "(BAUT IBOT MOD)"  (por si queda en recuperacion)
# Uso: sudo python send_iboot.py ~/fw/iBoot.j33i.RELEASE.img3
import sys, struct, time
sys.path.insert(0, '.')
import usb.core, usb.util, usb.backend.libusb1 as libusb1

import os
BOOT_ARGS = os.environ.get('BOOT_ARGS', '-v')
assert len(BOOT_ARGS) <= 39, 'BOOT_ARGS demasiado largo (max 39)'
# QUEDARSE=1: el iBoot no arranca solo (auto-boot=0) y acepta imagenes sin firma por USB,
# para mandarle disco en RAM + devicetree + kernel parcheado CON LA PANTALLA PRENDIDA.
QUEDARSE = os.environ.get('QUEDARSE') == '1'

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

def tag_offset(img3, name):
    off = 20
    while off + 12 <= len(img3):
        magic, total, dlen = struct.unpack('<4sII', img3[off:off + 12])
        if magic[::-1] == name:
            return off + 12
        off += total
    raise SystemExit('sin %s' % name)

def patch(img3, addr, old, new):
    o = tag_offset(img3, 'DATA') + (addr - 0x9FF00000)
    assert img3[o:o + len(old)] == old, 'bytes inesperados en %#x' % addr
    assert len(new) == len(old)
    return img3[:o] + new + img3[o + len(old):]

img3 = open(sys.argv[1], 'rb').read()
# tipo: cabecera (ident en +16) y etiqueta TYPE
assert img3[16:20] == 'tobi', 'no es un iBoot'
img3 = img3[:16] + 'cebi' + img3[20:]
t = tag_offset(img3, 'TYPE')
assert img3[t:t + 4] == 'tobi'
img3 = img3[:t] + 'cebi' + img3[t + 4:]
img3 = patch(img3, 0x9FF1CB94, '\x18\xbf', '\x00\xbf')
s = 'rd=md0 nand-enable-reformat=1 -progress'
img3 = patch(img3, 0x9FF3C87B, s, BOOT_ARGS + '\0' * (len(s) - len(BOOT_ARGS)))
if QUEDARSE:
    img3 = patch(img3, 0x9FF00E26, '\x17\xf0\x2d\xff', '\x00\x20\x00\xbf')   # getenv("auto-boot") -> 0
    img3 = patch(img3, 0x9FF1B20E, '\xff\xf7\x77\xfc', '\x00\x20\x00\xbf')   # validar firma IMG3 -> OK
n = img3.count('(Recovery Mode)')
img3 = img3.replace('(Recovery Mode)', '(BAUT IBOT MOD)')
print 'iBoot parcheado: tipo ibec, boot-args="%s", queda en recuperacion: %s, marcas: %d' % (BOOT_ARGS, QUEDARSE, n)
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
print 'reset USB: el iBSS deberia arrancar el iBoot -> logo -> tvOS con -v'
try:
    dev.reset()
except Exception as e:
    print '(normal)', e
