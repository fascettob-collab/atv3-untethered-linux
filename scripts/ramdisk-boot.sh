#!/usr/bin/env bash
# B4 - Arranca la Apple TV con el disco en RAM con SSH (tethered). Uso: sudo ~/ramdisk-boot.sh
# Cadena: pwned DFU -> iBSS parcheado -> iBEC parcheado (boot-args del disco en RAM)
#         -> disco en RAM + devicetree + kernel parcheado -> bootx -> ssh root@192.168.0.250
PY="/home/bauti/.pyenv/versions/2.7.18/bin/python"
IPW="/home/bauti/ipwndfu"
FW="/home/bauti/fw"
RD="/home/bauti/rd/ramdisk_ssh.img3"
KC="/home/bauti/fw/kernelcache.patched"
DT="/home/bauti/fw/DeviceTree.j33iap.img3"
export BOOT_ARGS="rd=md0 amfi_get_out_of_my_way=1 wdt=-1"   # wdt=-1: sin watchdog (si no, panic "WDT timeout" a los ~3 min)

paso() { echo; echo "=== $* ==="; }
producto() { lsusb -v -d "05ac:$1" 2>/dev/null | grep -m1 iProduct | sed 's/.*iProduct *[0-9]* //'; }
espera_producto() {  # $1 pid, $2 texto, $3 segundos
  for i in $(seq 1 "$3"); do [ "$(producto "$1")" = "$2" ] && return 0; sleep 1; done; return 1
}

if ! uname -r | grep -q ckm8; then
  echo "ERROR: este kernel no es el ckm8 ($(uname -r))."
  echo 'CorrÃ©:  sudo grub-reboot "Advanced options for Ubuntu>Ubuntu, with Linux 7.0.14-ckm8" && sudo reboot'
  exit 1
fi
for f in "$IPW/boot_ibss.py" "$IPW/send_ibec.py" "$IPW/boot_ramdisk.py" "$FW/iBSS.j33i.RELEASE.dfu" \
         "$FW/iBEC.j33i.RELEASE.dfu" "$RD" "$KC" "$DT" /home/bauti/payload8947_flush.bin; do
  [ -f "$f" ] || { echo "ERROR: falta $f"; exit 1; }
done
systemctl stop fwupd 2>/dev/null
echo 1 > /sys/module/xhci_hcd/parameters/ckm8_enable
echo 64 > /sys/module/xhci_hcd/parameters/ckm8_partial_len
echo 626 > /tmp/leak; echo 0x2000 > /tmp/owlen; echo 0x620 > /tmp/pad; echo 0x340002a4 > /tmp/cb
export FLUSH=1 MO= MP= SKIP_MARK= SKIP_OW= TINY= STATUS=
cd "$IPW" || exit 1

paso "1/4 (checkm8)"
n=0
while true; do
  echo ">> PonÃ© la Apple TV en DFU: corriente afuera, enchufar, Menu+Abajo y enseguida Menu+Play/Pausa"
  until lsusb -d 05ac:1227 >/dev/null 2>&1; do sleep 0.2; done
  n=$((n+1)); echo ">> Intento $n"
  sleep 0.5
  "$PY" ./ipwndfu -p 2>&1 | tail -2
  sleep 8
  if lsusb -v -d 05ac:1227 2>/dev/null | grep -q "PWND"; then echo ">> PWND en el intento $n"; break; fi
  echo ">> No saliÃ³. DesenchufÃ¡ la corriente para reintentar."
  while lsusb -d 05ac: >/dev/null 2>&1; do sleep 0.5; done
done

paso "2/4 iBSS modificado"
"$PY" boot_ibss.py "$FW/iBSS.j33i.RELEASE.dfu" 2>&1 | grep -v "^ *File\|Traceback"
espera_producto 1227 "Apple Mobile Device (BAUT MOD)" 30 || { echo "ERROR: no apareciÃ³ el iBSS"; exit 1; }
echo ">> iBSS corriendo"

paso "3/4 iBEC modificado (boot-args: $BOOT_ARGS)"
# Tiene que ser el iBEC: el iBoot de RELEASE no tiene los comandos ramdisk/devicetree/bootx
# (por eso "ramdisk" daba Pipe error y se reiniciaba). Contra: el iBEC no prende el HDMI.
"$PY" send_ibec.py "$FW/iBEC.j33i.RELEASE.dfu" 2>&1 | grep -E "parcheado|enviados|reset|ERROR|bytes"
espera_producto 1281 "Apple Mobile Device (BAUT IBEC MOD)" 40 || { echo "ERROR: no aparecio el iBEC (BAUT IBEC MOD)"; lsusb | grep -i 05ac; exit 1; }
echo ">> iBEC corriendo"

paso "4/4 Disco en RAM + devicetree + kernel parcheado"
"$PY" boot_ramdisk.py "$RD" "$DT" "$KC"
echo
echo "Mirando la red y el USB durante 4 minutos (cada interfaz tiene su IP: .250 .251 .252)..."
T0=$(date +%s)
visto_usb=""
for i in $(seq 1 240); do
  for ip in 192.168.0.250 192.168.0.251 192.168.0.252; do
    if ping -c1 -W1 "$ip" >/dev/null 2>&1; then
      echo ">> Â¡Responde $ip! a los $(( $(date +%s) - T0 )) s. EntrÃ¡ con:  ssh root@$ip"
      exit 0
    fi
  done
  u=$(lsusb | grep -i 05ac | sed 's/.*ID //')
  if [ -n "$u" ] && [ "$u" != "$visto_usb" ]; then
    echo ">> USB a los $(( $(date +%s) - T0 )) s: $u"
    visto_usb="$u"
  fi
done
echo
echo ">> No respondiÃ³. CÃ³mo leer lo de arriba:"
echo "   - apareciÃ³ 05ac:12a7 (tvOS normal) antes de ~30 s  -> el kernel se cayÃ³ enseguida (panic)"
echo "   - apareciÃ³ 05ac:12a7 a los ~100-150 s              -> el disco arrancÃ³ y el script corriÃ³, pero fallÃ³ sshd o la red"
echo "   - no apareciÃ³ nada                                  -> se quedÃ³ colgada (kernel o disco)"
