# -*- coding: utf-8 -*-
# Python 2.7, desde ~/ipwndfu. Igual que boot_ramdisk.py pero SIN disco en RAM:
# sube devicetree + kernel parcheado y arranca tvOS desde la NAND (prueba del kernel solo).
# Uso: sudo python boot_kernel.py DEVICETREE.img3 KERNELCACHE
import sys, time
sys.path.insert(0, '.')
import usb.core, usb.util, usb.backend.libusb1 as libusb1

dev = usb.core.find(idVendor=0x5AC, idProduct=0x1281, backend=libusb1.get_backend())
if dev is None:
    raise SystemExit('no encuentro el iBoot/iBEC modificado (05ac:1281)')
prod = usb.util.get_string(dev, dev.iProduct)
print 'dispositivo:', prod
if 'BAUT IBEC MOD' not in prod and 'BAUT IBOT MOD' not in prod:
    raise SystemExit('no es el iBEC/iBoot modificado')
try:
    dev.set_configuration(1)
except Exception as e:
    print '(configuracion)', e
dev.set_interface_altsetting(interface=1, alternate_setting=1)

def cmd(c):
    print '>', c
    dev.ctrl_transfer(0x40, 0, 0, 0, c + '\0', 30000)

def send_file(path):
    data = open(path, 'rb').read()
    print 'enviando %s (%.1f MB)' % (path, len(data) / 1048576.0)
    dev.ctrl_transfer(0x41, 0, 0, 0, '', 5000)
    for i in range(0, len(data), 0x8000):
        dev.write(0x04, data[i:i + 0x8000], 30000)
    time.sleep(0.5)

send_file(sys.argv[1])
cmd('devicetree')
time.sleep(1)
send_file(sys.argv[2])
try:
    cmd('bootx')
except Exception as e:
    print '(normal: la Apple TV arranca el kernel)', e
print 'Listo. Mirá la tele: tendría que arrancar tvOS con texto (-v).'
