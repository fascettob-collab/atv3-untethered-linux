"""Extrae paquetes .deb (ar + data.tar.{gz,bz2,lzma,xz}) a una carpeta, sin dependencias externas.
Guarda los permisos y symlinks en un manifiesto (mode/links.txt) porque Windows no los conserva.
  python debx.py salida paquete1.deb paquete2.deb ...
"""
import sys, os, io, tarfile, lzma, bz2, gzip, struct, json

def ar_members(b):
    assert b[:8] == b"!<arch>\n"
    off = 8
    while off < len(b):
        hdr = b[off:off + 60]
        name = hdr[:16].decode().strip().rstrip("/")
        size = int(hdr[48:58].decode().strip())
        yield name, b[off + 60:off + 60 + size]
        off += 60 + size + (size & 1)

def open_tar(name, data):
    if name.endswith(".gz"):
        data = gzip.decompress(data)
    elif name.endswith(".bz2"):
        data = bz2.decompress(data)
    elif name.endswith(".lzma"):
        data = lzma.decompress(data, format=lzma.FORMAT_ALONE)
    elif name.endswith(".xz"):
        data = lzma.decompress(data)
    return tarfile.open(fileobj=io.BytesIO(data))

def main(out, debs):
    manifest = {}
    os.makedirs(out, exist_ok=True)
    for deb in debs:
        for name, data in ar_members(open(deb, "rb").read()):
            if not name.startswith("data.tar"):
                continue
            t = open_tar(name, data)
            for m in t.getmembers():
                path = m.name.lstrip("./")
                if not path:
                    continue
                dst = os.path.join(out, path.replace("/", os.sep))
                if m.isdir():
                    os.makedirs(dst, exist_ok=True)
                    manifest["/" + path] = {"type": "dir", "mode": m.mode}
                elif m.issym():
                    manifest["/" + path] = {"type": "link", "target": m.linkname, "mode": m.mode}
                elif m.isfile():
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    with open(dst, "wb") as f:
                        f.write(t.extractfile(m).read())
                    manifest["/" + path] = {"type": "file", "mode": m.mode}
                elif m.islnk():
                    manifest["/" + path] = {"type": "hardlink", "target": "/" + m.linkname.lstrip("./"), "mode": m.mode}
        print("extraido", deb)
    json.dump(manifest, open(os.path.join(out, "_manifest.json"), "w"), indent=1, sort_keys=True)
    print("entradas:", len(manifest))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
