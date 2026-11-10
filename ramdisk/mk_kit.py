"""Arma rdkit.tar: herramientas de emu/extra (con permisos/symlinks del manifiesto) + emu/overlay.
Rutas /etc y /var se reescriben a /private/etc y /private/var (en el disco son symlinks).
Dueño root:wheel (0:0). Se extrae en la PC de casa sobre la imagen montada con:  sudo tar -xpf rdkit.tar -C mnt
"""
import os, io, json, tarfile, time

BASE = os.path.dirname(os.path.abspath(__file__))
EXTRA = os.path.join(BASE, "extra")
OVER = os.path.join(BASE, "overlay")
SKIP = ("/usr/share/man", "/usr/share/doc", "/usr/share/info", "/usr/include",
        # versión chica: el iBoot no carga discos en RAM de 40 MB ("ramdisk" -> Pipe error)
        "/usr/lib/engines", "/usr/bin/ssh", "/usr/libexec/ssh-", "/usr/bin/openssl",
        "/etc/ssh/moduli", "/usr/lib/libncursesw", "/bin/dir", "/bin/vdir",
        "/usr/bin/scp", "/usr/bin/sftp", "/usr/libexec/sftp-server")
KEEP_TERMINFO = ("/usr/share/terminfo/v/vt100", "/usr/share/terminfo/x/xterm",
                 "/usr/share/terminfo/x/xterm-256color", "/usr/share/terminfo/d/dumb")

KEEP_BIN = {"bash", "sh", "ls", "cp", "mv", "rm", "ln", "cat", "mkdir", "chmod", "chown",
            "dd", "df", "uname", "sleep", "touch", "pwd", "date", "stty", "head", "tail",
            "wc", "env", "id", "ifconfig"}
SKIP_FILES = ("/usr/lib/libssl.0.9.8.dylib", "/usr/bin/ldid")

def skip(p):
    if p.startswith("/usr/share/terminfo/") and len(p.split("/")) > 5:
        return p not in KEEP_TERMINFO
    if p.startswith(SKIP_FILES):
        return True
    parts = p.split("/")
    if len(parts) == 3 and parts[1] == "bin" or len(parts) == 4 and parts[1:3] == ["usr", "bin"]:
        return parts[-1] not in KEEP_BIN
    return p.startswith(SKIP)
MODES = {"/usr/local/bin/boot_ssh.sh": 0o755, "/etc/master.passwd": 0o600}

def remap(p):
    for top in ("/etc", "/var"):
        if p == top:
            return None
        if p.startswith(top + "/"):
            return "/private" + p
    return p

def add(tf, path, kind, data=b"", mode=0o644, target=""):
    ti = tarfile.TarInfo(path.lstrip("/"))
    ti.uid = ti.gid = 0
    ti.uname, ti.gname = "root", "wheel"
    ti.mtime = int(time.time())
    ti.mode = mode & 0o7777
    if kind == "dir":
        ti.type = tarfile.DIRTYPE
        tf.addfile(ti)
    elif kind == "link":
        ti.type = tarfile.SYMTYPE; ti.linkname = target
        tf.addfile(ti)
    else:
        ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data))

man = json.load(open(os.path.join(EXTRA, "_manifest.json")))
n = 0
with tarfile.open(os.path.join(BASE, "rdkit.tar"), "w", format=tarfile.GNU_FORMAT) as tf:
    for p in sorted(man):
        if skip(p):
            continue
        q = remap(p)
        if q is None:
            continue
        e = man[p]
        if e["type"] == "dir":
            add(tf, q, "dir", mode=e["mode"])
        elif e["type"] == "link":
            add(tf, q, "link", mode=0o777, target=e["target"])
        elif e["type"] == "file":
            add(tf, q, "file", open(os.path.join(EXTRA, p.lstrip("/").replace("/", os.sep)), "rb").read(), e["mode"])
        elif e["type"] == "hardlink":
            src = man.get(e["target"], {})
            add(tf, q, "file", open(os.path.join(EXTRA, e["target"].lstrip("/").replace("/", os.sep)), "rb").read(), e["mode"])
        n += 1
    for root, dirs, files in os.walk(OVER):
        for f in files:
            full = os.path.join(root, f)
            p = "/" + os.path.relpath(full, OVER).replace(os.sep, "/")
            data = open(full, "rb").read().replace(b"\r\n", b"\n")
            add(tf, remap(p) or p, "file", data, MODES.get(p, 0o644))
            n += 1
    add(tf, "/private/var/root/.ssh", "dir", mode=0o700)
    add(tf, "/private/var/empty", "dir", mode=0o755)
    add(tf, "/private/var/run", "dir", mode=0o755)
    add(tf, "/private/var/log", "dir", mode=0o755)
print("rdkit.tar:", n, "entradas,", os.path.getsize(os.path.join(BASE, "rdkit.tar")) // 1024, "KB")
