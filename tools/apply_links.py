"""Aplica los destinos de symlinks al backup reensamblado (desde symlinks.tsv)."""
import os, sys

base = "/home/bauti/backup/apple-tv"
n = 0
for line in open("/home/bauti/backup/symlinks.tsv", encoding="utf-8", errors="surrogateescape"):
    line = line.rstrip("\n")
    if line == "#END" or not line:
        continue
    target, path = line.split("\t", 1)
    top = "system" if path.startswith("/mnt1") else "data"
    rel = path[len("/mnt1") if path.startswith("/mnt1") else len("/mnt2"):].lstrip("/")
    dst = os.path.join(base, top, rel)
    marker = dst + ".SYMLINK_SIN_DESTINO"
    if os.path.exists(marker):
        os.remove(marker)
    if os.path.lexists(dst):
        os.remove(dst)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.symlink(target, dst)
    n += 1
print("symlinks aplicados:", n)
