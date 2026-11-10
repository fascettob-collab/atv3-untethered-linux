#!/bin/bash
# Arranque del disco en RAM: red por Ethernet con IP fija + sshd.
# Cada interfaz recibe su propia IP (no sabemos cuál es el cable): en0=.250, en1=.251, en2=.252
#
# MODO DIAGNÓSTICO: si a los 4 minutos nadie entró por SSH (no existe /tmp/quedarse),
# reinicia la Apple TV de forma LIMPIA para que la NVRAM guarde la bitácora.
# Leerla desde recuperación:  sudo irecovery -s   y adentro:  getenv bautlog
# Si entrás por SSH:  touch /tmp/quedarse   (así no se reinicia)
export PATH=/bin:/usr/bin:/sbin:/usr/sbin:/usr/local/bin

/sbin/mount -u -w / 2>/dev/null
mkdir -p /var/run /var/empty /var/log /var/tmp /tmp
chmod 1777 /tmp /var/tmp

exec >/var/log/boot_ssh.log 2>&1
echo "boot_ssh: inicio"

LOG="ini"
marca() { LOG="$LOG;$1"; /usr/sbin/nvram bautlog="$LOG" 2>/dev/null; }
marca "sh"

ifconfig lo0 127.0.0.1 up; marca "lo0=$?"
# qué interfaces ve el kernel (nombres cortos, sin grep)
todas=$(ifconfig -l 2>&1); marca "l=[${todas// /,}]"

n=250
for i in en0 en1 en2; do
  out=$(ifconfig "$i" 2>&1); rc=$?
  if [ $rc -ne 0 ]; then
    marca "$i:no"
  else
    ifconfig "$i" inet "192.168.0.$n" netmask 255.255.255.0 up; rc=$?
    out=$(ifconfig "$i" 2>&1); st=""; ip="-"
    [[ $out =~ status:\ ([a-z]+) ]] && st=${BASH_REMATCH[1]}
    [[ $out =~ inet\ ([0-9.]+) ]] && ip=${BASH_REMATCH[1]}
    marca "$i:rc$rc,$ip,${st:-sinstatus}"
  fi
  n=$((n+1))
done

[ -x /usr/sbin/sshd ] && marca "sshd:x" || marca "sshd:noexec"
/usr/sbin/sshd -t -f /etc/ssh/sshd_config; marca "sshdt=$?"
/usr/sbin/sshd -e -f /etc/ssh/sshd_config; marca "sshd=$?"

# Sin configd el kernel no crea en0 (solo lo0): la red no sirve en el disco en RAM.
# Plan B: SSH por USB. restored_external ahora lo lanza launchd con su plist original
# (com.apple.restored_external.plist sin tocar) y es el que configura el USB del lado
# de la Apple TV (modo restauración, con el "usbmux" del kernel).
# Desde la PC:  iproxy 2222 22  y  ssh -p 2222 root@localhost
sleep 5
out=$(/bin/launchctl list 2>/dev/null)
case "$out" in *restored_external*) marca "restored:vivo";; *) marca "restored:no";; esac

sleep 600
if [ ! -e /tmp/quedarse ]; then
  marca "rb"
  /usr/sbin/nvram auto-boot=false   # que quede en recuperación para poder leer la bitácora
  sync
  /sbin/reboot
fi
