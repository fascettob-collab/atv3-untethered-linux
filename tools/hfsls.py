"""Lector mínimo de HFS+ (solo lectura): lista el árbol y extrae archivos.
  python hfsls.py ramdisk.hfs                 -> lista todo
  python hfsls.py ramdisk.hfs cat /ruta       -> imprime/guarda un archivo
"""
import sys, struct

class HFS:
    def __init__(self, path):
        self.d = open(path, "rb").read()
        vh = self.d[0x400:0x600]
        assert vh[:2] in (b"H+", b"HX")
        self.bs = struct.unpack(">I", vh[0x28:0x2C])[0]
        self.cat_fork = self.fork(vh[0x110:0x160])
        self.nodes = {}
        cat = self.read_fork(self.cat_fork)
        self.cat = cat
        hdr = cat[14:14 + 106]
        self.first_leaf = struct.unpack(">I", hdr[10:14])[0]
        self.node_size = struct.unpack(">H", hdr[18:20])[0]
        self.entries = {}   # cnid -> (parent, name, type, data)
        self.walk()

    def fork(self, f):
        logical = struct.unpack(">Q", f[0:8])[0]
        ext = [struct.unpack(">II", f[16 + 8 * i:24 + 8 * i]) for i in range(8)]
        return logical, ext

    def cnid_of(self, path):
        for cnid, (p, name, t, fk, mode) in self.entries.items():
            if t == "file" and self.path(cnid) == path:
                return cnid

    def read_attr(self, cnid, attr):
        """Lee un atributo extendido del B-tree de atributos (formato decmpfs)."""
        attr_fork = self.fork(self.d[0x400 + 0x160:0x400 + 0x1B0])
        if attr_fork[0] == 0:
            return None
        tree = self.read_fork(attr_fork)
        # nodo cabecera: BTHeaderRec en 14+..., firstLeafNode en 14+10, nodeSize en 14+18
        first_leaf = struct.unpack(">I", tree[24:28])[0]
        ns = struct.unpack(">H", tree[32:34])[0]
        n = first_leaf
        want = attr.encode("utf-16-be")
        while n:
            node = tree[n * ns:(n + 1) * ns]
            flink, blink, kind, height, nrec = struct.unpack(">IIbBH", node[:12])
            offs = [struct.unpack(">H", node[ns - 2 * (i + 1):ns - 2 * i])[0] for i in range(nrec)]
            for o in offs:
                klen = struct.unpack(">H", node[o:o + 2])[0]
                f_cnid = struct.unpack(">I", node[o + 2:o + 6])[0]
                start = struct.unpack(">I", node[o + 6:o + 10])[0]
                nlen = struct.unpack(">H", node[o + 10:o + 12])[0]
                name = node[o + 12:o + 12 + 2 * nlen]
                if f_cnid == cnid and start == 0 and name == want:
                    # registro: clave + tipo de dato (uint16 LE) + longitud + valor
                    r = o + 2 + klen
                    dtype = struct.unpack("<H", node[r:r + 2])[0]
                    dlen = struct.unpack("<I", node[r + 2:r + 6])[0]
                    return node[r + 6:r + 6 + dlen]
            n = flink
        return None

    def read_fork(self, fk):
        logical, ext = fk
        out = bytearray()
        for start, count in ext:
            if count == 0:
                break
            out += self.d[start * self.bs:(start + count) * self.bs]
        return bytes(out[:logical])

    def walk(self):
        n = self.first_leaf
        ns = self.node_size
        while n:
            node = self.cat[n * ns:(n + 1) * ns]
            flink, blink, kind, height, nrec = struct.unpack(">IIbBH", node[:12])
            offs = [struct.unpack(">H", node[ns - 2 * (i + 1):ns - 2 * i])[0] for i in range(nrec)]
            for o in offs:
                klen = struct.unpack(">H", node[o:o + 2])[0]
                parent = struct.unpack(">I", node[o + 2:o + 6])[0]
                nlen = struct.unpack(">H", node[o + 6:o + 8])[0]
                name = node[o + 8:o + 8 + 2 * nlen].decode("utf-16-be", "replace")
                r = o + 2 + klen
                rtype = struct.unpack(">h", node[r:r + 2])[0]
                if rtype == 1:      # carpeta
                    cnid = struct.unpack(">I", node[r + 8:r + 12])[0]
                    self.entries[cnid] = (parent, name, "dir", None, 0o40755)
                elif rtype == 2:    # archivo
                    cnid = struct.unpack(">I", node[r + 8:r + 12])[0]
                    mode = struct.unpack(">H", node[r + 0x2A:r + 0x2C])[0]
                    data_fork = self.fork(node[r + 0x58:r + 0x58 + 80])
                    self.entries[cnid] = (parent, name, "file", data_fork, mode)
            n = flink

    def path(self, cnid):
        parts = []
        while cnid in self.entries and cnid != 2:
            p, name, *_ = self.entries[cnid]
            parts.append(name); cnid = p
        return "/" + "/".join(reversed(parts))

    def listing(self):
        for cnid, (p, name, t, fk, mode) in sorted(self.entries.items(), key=lambda kv: self.path(kv[0])):
            size = fk[0] if fk else 0
            yield self.path(cnid), t, size, mode

    def read(self, path):
        for cnid, (p, name, t, fk, mode) in self.entries.items():
            if t == "file" and self.path(cnid) == path:
                return self.read_fork(fk)

    def read_res(self, path):
        """Lee el fork de recursos de un archivo (para decmpfs)."""
        for cnid, (p, name, t, fk, mode) in self.entries.items():
            if t == "file" and self.path(cnid) == path:
                # el registro de catálogo: rebuscar el fork de recursos (r+0xA8)
                cat = self.cat
                ns = self.node_size
                # recorrer de nuevo las hojas para encontrar el registro crudo
                n = self.first_leaf
                while n:
                    node = cat[n * ns:(n + 1) * ns]
                    flink, blink, kind, height, nrec = struct.unpack(">IIbBH", node[:12])
                    offs = [struct.unpack(">H", node[ns - 2 * (i + 1):ns - 2 * i])[0] for i in range(nrec)]
                    for o in offs:
                        klen = struct.unpack(">H", node[o:o + 2])[0]
                        parent = struct.unpack(">I", node[o + 2:o + 6])[0]
                        nlen = struct.unpack(">H", node[o + 6:o + 8])[0]
                        name = node[o + 8:o + 8 + 2 * nlen].decode("utf-16-be", "replace")
                        r = o + 2 + klen
                        rtype = struct.unpack(">h", node[r:r + 2])[0]
                        if rtype == 2 and parent == p and name == name_of(path):
                            fk = self.fork(node[r + 0xA8:r + 0xA8 + 80])
                            return self.read_fork(fk)
                    n = flink
        return None

def name_of(path):
    return path.rstrip("/").split("/")[-1]

def decmpfs_xattr(val):
    """Valor del xattr com.apple.decmpfs: magic fpmc + metodo + tamaño + datos (si inline)."""
    import zlib
    magic, method, usize = struct.unpack(">III", val[:12])
    assert magic == 0x66706D63, hex(magic)
    data = val[12:]
    if method == 3:  # zlib
        return zlib.decompress(data)[:usize]
    if method == 4:  # lzvn/lzss de Apple
        raise SystemExit("decmpfs metodo 4 (lzvn) no soportado todavia")
    raise SystemExit("metodo decmpfs desconocido: %d" % method)

def decmpfs_res(res):
    """Descomprime el fork de recursos de un archivo decmpfs HFS+."""
    import zlib
    assert res[:4] == b"fpmc", res[:4].hex()
    unk, usize, nblocks = struct.unpack(">III", res[4:16])
    sizes = [struct.unpack(">I", res[16 + 4 * i:20 + 4 * i])[0] for i in range(nblocks)]
    out = bytearray()
    off = 16 + 4 * nblocks
    for s in sizes:
        blk = res[off:off + s]
        off += s
        if blk[:2] == b"\x78\x9c" or blk[:1] == b"\x78":
            out += zlib.decompress(blk)
        else:
            out += blk  # bloque sin comprimir
    return bytes(out[:usize])

if __name__ == "__main__":
    h = HFS(sys.argv[1])
    if len(sys.argv) > 3 and sys.argv[2] == "cat":
        sys.stdout.buffer.write(h.read(sys.argv[3]))
    elif len(sys.argv) > 3 and sys.argv[2] == "catr":
        sys.stdout.buffer.write(h.read_res(sys.argv[3]))
    elif len(sys.argv) > 3 and sys.argv[2] == "uncat":
        # archivo comprimido con decmpfs: probar primero el xattr, sino el fork de recursos
        cnid = h.cnid_of(sys.argv[3])
        v = h.read_attr(cnid, "com.apple.decmpfs")
        if v:
            sys.stdout.buffer.write(decmpfs_xattr(v))
        else:
            sys.stdout.buffer.write(decmpfs_res(h.read_res(sys.argv[3])))
    else:
        for p, t, size, mode in h.listing():
            print("%s %8d %o %s" % ("d" if t == "dir" else "-", size, mode, p))
