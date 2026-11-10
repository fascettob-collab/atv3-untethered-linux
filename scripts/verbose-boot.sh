#!/usr/bin/env bash
# Arranque de la Apple TV 3 en modo texto (-v), todo en un comando.
# Uso:  sudo ~/verbose-boot.sh     (la Apple TV conectada por USB y la tele por HDMI)
# Requisitos: kernel 7.0.14-ckm8 arrancado, ~/ipwndfu con boot_ibss.py y send_iboot.py, ~/fw con los archivos.
PY="/home/bauti/.pyenv/versions/2.7.18/bin/python"
IPW="/home/bauti/ipwndfu"
FW="/home/bauti/fw"

paso() { echo; echo "=== $* ==="; }
producto() { lsusb -v -d "05ac:$1" 2>/dev/null | grep -m1 iProduct | sed 's/.*iProduct *[0-9]* //'; }

# --- 0. Chequeos
if ! uname -r | grep -q ckm8; then
  echo "ERROR: este kernel no es el ckm8 ($(uname -r))."
  echo 'Corré:  sudo grub-reboot "Advanced options for Ubuntu>Ubuntu, with Linux 7.0.14-ckm8" && sudo reboot'
  exit 1
fi
for f in "$IPW/boot_ibss.py" "$IPW/send_iboot.py" "$FW/iBSS.j33i.RELEASE.dfu" "$FW/iBoot.j33i.RELEASE.img3" /home/bauti/payload8947_flush.bin; do
  [ -f "$f" ] || { echo "ERROR: falta $f"; exit 1; }
done
systemctl stop fwupd 2>/dev/null
echo 1 > /sys/module/xhci_hcd/parameters/ckm8_enable
echo 64 > /sys/module/xhci_hcd/parameters/ckm8_partial_len
echo 626 > /tmp/leak; echo 0x2000 > /tmp/owlen; echo 0x620 > /tmp/pad; echo 0x340002a4 > /tmp/cb
export FLUSH=1 MO= MP= SKIP_MARK= SKIP_OW= TINY= STATUS=
cd "$IPW" || exit 1

# --- 1. checkm8 hasta PWND
paso "1/3 Exploit (checkm8)"
n=0
while true; do
  echo ">> Poné la Apple TV en DFU: corriente afuera, enchufar, Menu+Abajo y enseguida Menu+Play/Pausa"
  until lsusb -d 05ac:1227 >/dev/null 2>&1; do sleep 0.2; done
  n=$((n+1)); echo ">> Intento $n"
  sleep 0.5
  "$PY" ./ipwndfu -p 2>&1 | tail -2
  sleep 8
  if lsusb -v -d 05ac:1227 2>/dev/null | grep -q "PWND"; then echo ">> PWND en el intento $n"; break; fi
  echo ">> No salió. Desenchufá la corriente para reintentar."
  while lsusb -d 05ac: >/dev/null 2>&1; do sleep 0.5; done
done

# --- 2. iBSS parcheado
paso "2/3 iBSS modificado"
"$PY" boot_ibss.py "$FW/iBSS.j33i.RELEASE.dfu" 2>&1 | grep -v "^ *File\|Traceback"
for i in $(seq 1 30); do
  [ "$(producto 1227)" = "Apple Mobile Device (BAUT MOD)" ] && break
  sleep 1
done
if [ "$(producto 1227)" != "Apple Mobile Device (BAUT MOD)" ]; then
  echo "ERROR: no apareció el iBSS (BAUT MOD). Desenchufá la corriente y volvé a correr el script."
  exit 1
fi
echo ">> iBSS corriendo"

# --- 3. iBoot con -v
paso "3/3 iBoot con -v  -> mirá la tele"
"$PY" send_iboot.py "$FW/iBoot.j33i.RELEASE.img3" 2>&1 | grep -E "parcheado|enviados|reset"
echo
echo "Listo: en la tele tiene que aparecer el texto del arranque y después el menú de tvOS."
echo "(Para volver a la normalidad: desenchufar y enchufar la corriente.)"
