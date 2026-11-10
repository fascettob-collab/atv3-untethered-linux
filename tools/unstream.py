"""Reensambla el stream de backup de la Apple TV (ver streamer.sh).
  python unstream.py backup.stream /ruta/de/salida
"""
import sys, os

def main(stream, out):
    f = open(stream, "rb")
    nfiles = ndirs = 0
    total = 0
    while True:
        line = f.readline()
        if not line:
            print("WARN: fin de stream sin END")
            break
        line = line.rstrip(b"\n")
        if line == b"END":
            break
        kind = line[:2]
        rest = line[2:]
        if kind == b"F ":
            sz, path = rest.split(b" ", 1)
            sz = int(sz)
            top = "system" if path.startswith(b"/mnt1") else "data"
            rel = path[len(b"/mnt1") if path.startswith(b"/mnt1") else len(b"/mnt2"):].decode("utf-8", "surrogateescape").lstrip("/")
            dst = os.path.join(out, top, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            left = sz
            with open(dst, "wb") as w:
                while left:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        print("WARN: stream corto en", path)
                        break
                    w.write(chunk)
                    left -= len(chunk)
            nfiles += 1
            total += sz
            if nfiles % 500 == 0:
                print(nfiles, "archivos...", total // 1024 // 1024, "MB")
        elif kind == b"D ":
            path = rest.decode("utf-8", "surrogateescape")
            top = "system" if path.startswith("/mnt1") else "data"
            rel = path[len("/mnt1") if path.startswith("/mnt1") else len("/mnt2"):].lstrip("/")
            os.makedirs(os.path.join(out, top, rel), exist_ok=True)
            ndirs += 1
        elif kind == b"L ":
            target, path = rest.split(b" ", 1)
            top = "system" if path.startswith(b"/mnt1") else "data"
            rel = path[len(b"/mnt1") if path.startswith(b"/mnt1") else len(b"/mnt2"):].decode("utf-8", "surrogateescape").lstrip("/")
            dst = os.path.join(out, top, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if target and not os.path.exists(dst):
                os.symlink(target.decode("utf-8", "surrogateescape"), dst)
            elif not target:
                # readlink no estaba en el ramdisk: destino desconocido
                with open(dst + ".SYMLINK_SIN_DESTINO", "w") as w:
                    pass
        elif kind == b"E ":
            path = rest.decode("utf-8", "surrogateescape")
            top = "system" if path.startswith("/mnt1") else "data"
            rel = path[len("/mnt1") if path.startswith("/mnt1") else len("/mnt2"):].lstrip("/")
            dst = os.path.join(out, top, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            open(dst, "wb").close()
    print("Listo: %d archivos (%.1f MB), %d directorios" % (nfiles, total / 1048576.0, ndirs))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
