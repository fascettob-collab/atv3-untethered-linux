#!/usr/bin/env bash
# B3 - Arma el disco en RAM con SSH para la Apple TV 3 (se corre en la PC Linux de casa).
# Uso:  cd ~/rd && sudo ./build_ramdisk.sh
# Entrada (en esta carpeta): ramdisk_big.hfs, rdkit.tar, ramdisk_orig.dmg, wrap_rdsk.py
# Salida: ~/rd/ramdisk_ssh.img3  (IMG3 tipo rdsk, listo para mandar al iBEC)
set -e
cd "$(dirname "$0")"
USER_HOME=/home/bauti
for f in ramdisk_big.hfs rdkit.tar ramdisk_orig.dmg wrap_rdsk.py; do
  [ -f "$f" ] || { echo "ERROR: falta $f"; exit 1; }
done

echo "== 1. copia de trabajo y montaje (HFS+ en lectura/escritura)"
cp ramdisk_big.hfs work.hfs
mkdir -p mnt
umount mnt 2>/dev/null || true
modprobe hfsplus 2>/dev/null || true
mount -t hfsplus -o loop,rw work.hfs mnt
if ! touch mnt/.prueba_escritura 2>/dev/null; then
  echo "ERROR: Linux monto la imagen en solo lectura"; umount mnt; exit 1
fi
rm -f mnt/.prueba_escritura

echo "== 2. herramientas + scripts (rdkit.tar)"
tar -xpf rdkit.tar -C mnt
chmod 755 mnt/sbin/reboot mnt/sbin/halt mnt/usr/local/bin/boot_ssh.sh

echo "== 3. claves del servidor SSH"
mkdir -p mnt/private/etc/ssh
rm -f mnt/private/etc/ssh/ssh_host_*
ssh-keygen -q -t rsa -b 2048 -N '' -f mnt/private/etc/ssh/ssh_host_rsa_key
ssh-keygen -q -t ecdsa -b 256 -N '' -f mnt/private/etc/ssh/ssh_host_ecdsa_key

echo "== 4. tu clave para entrar (sin contraseña)"
if [ ! -f "$USER_HOME/.ssh/id_ed25519.pub" ]; then
  sudo -u bauti ssh-keygen -q -t ed25519 -N '' -f "$USER_HOME/.ssh/id_ed25519"
fi
mkdir -p mnt/private/var/root/.ssh
cp "$USER_HOME/.ssh/id_ed25519.pub" mnt/private/var/root/.ssh/authorized_keys
chmod 700 mnt/private/var/root/.ssh
chmod 600 mnt/private/var/root/.ssh/authorized_keys
chown -R 0:0 mnt/private/etc/ssh mnt/private/var/root

echo "== 5. verificación"
for f in usr/sbin/sshd bin/bash sbin/ifconfig usr/local/bin/boot_ssh.sh \
         System/Library/LaunchDaemons/com.apple.restored_external.plist \
         private/etc/ssh/sshd_config private/etc/ssh/ssh_host_rsa_key private/var/root/.ssh/authorized_keys; do
  [ -e "mnt/$f" ] && echo "   ok  /$f" || { echo "   FALTA /$f"; umount mnt; exit 1; }
done
grep -q boot_ssh.sh mnt/System/Library/LaunchDaemons/com.apple.restored_external.plist && echo "   ok  el arranque apunta a boot_ssh.sh"
df -h mnt | tail -1
sync
umount mnt

echo "== 6. IMG3 tipo rdsk"
python3 wrap_rdsk.py ramdisk_orig.dmg work.hfs ramdisk_ssh.img3
rm -f work.hfs
chown bauti:bauti ramdisk_ssh.img3
echo
echo "LISTO: $(pwd)/ramdisk_ssh.img3"
