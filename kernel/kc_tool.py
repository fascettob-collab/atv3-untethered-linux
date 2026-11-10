"""Kernelcache de tvOS 12H1006 (AppleTV3,2): sacar del IMG3, descomprimir LZSS y re-armar.

  python kc_tool.py unpack kernelcache.release.j33i kernel.macho
  python kc_tool.py pack   kernelcache.release.j33i kernel.macho kernelcache.patched
"""
import sys, struct

def img3_tags(b):
    off, tags = 20, []
    while off + 12 <= len(b):
        m, t, d = struct.unpack("<4sII", b[off:off + 12])
        tags.append((m[::-1], off, t, d))
        off += t
    return tags

def lzss_decompress(src, out_len):
    N, F, TH = 4096, 18, 2
    text = bytearray(b" " * (N - F)) + bytearray(F)
    r, flags, i, out = N - F, 0, 0, bytearray()
    while i < len(src) and len(out) < out_len:
        flags >>= 1
        if not flags & 0x100:
            flags = src[i] | 0xFF00; i += 1
        if flags & 1:
            c = src[i]; i += 1
            out.append(c); text[r] = c; r = (r + 1) & (N - 1)
        else:
            if i + 1 >= len(src):
                break
            a, b = src[i], src[i + 1]; i += 2
            pos = a | ((b & 0xF0) << 4)
            ln = (b & 0x0F) + TH
            for k in range(ln + 1):
                c = text[(pos + k) & (N - 1)]
                out.append(c); text[r] = c; r = (r + 1) & (N - 1)
    return bytes(out[:out_len])

def lzss_compress(src):
    """Compresor LZSS simple (solo literales y coincidencias codiciosas) compatible con el de Apple."""
    N, F, TH = 4096, 18, 2
    out = bytearray()
    window = {}
    i = 0
    text_start = N - F   # posición inicial del buffer circular del descompresor
    while i < len(src):
        flag_pos = len(out); out.append(0); flags = 0
        for bit in range(8):
            if i >= len(src):
                break
            best_len, best_pos = 0, 0
            key = bytes(src[i:i + 3])
            if len(key) == 3:
                for cand in reversed(window.get(key, [])[-64:]):
                    if i - cand >= N - F:
                        continue
                    l = 0
                    while l < F and i + l < len(src) and src[cand + l] == src[i + l]:
                        l += 1
                    if l > best_len:
                        best_len, best_pos = l, cand
                        if l == F:
                            break
            if best_len > TH:
                pos = (text_start + best_pos) & (N - 1)
                out.append(pos & 0xFF)
                out.append(((pos >> 4) & 0xF0) | (best_len - TH - 1))
                for k in range(best_len):
                    k3 = bytes(src[i + k:i + k + 3])
                    window.setdefault(k3, []).append(i + k)
                i += best_len
            else:
                flags |= 1 << bit
                out.append(src[i])
                window.setdefault(key, []).append(i)
                i += 1
        out[flag_pos] = flags
    return bytes(out)

def adler32_apple(b):
    a, s = 1, 0
    for x in b:
        a = (a + x) % 65521; s = (s + a) % 65521
    return (s << 16) | a

def unpack(src, dst):
    b = open(src, "rb").read()
    for m, off, t, d in img3_tags(b):
        if m == b"DATA":
            data = b[off + 12:off + 12 + d]
    assert data[:8] == b"complzss", data[:8]
    chk, ulen, clen = struct.unpack(">III", data[8:20])
    raw = lzss_decompress(data[0x180:0x180 + clen], ulen)
    print("descomprimido: %d bytes (esperado %d), adler %08x vs %08x, magic %s" %
          (len(raw), ulen, adler32_apple(raw), chk, raw[:4].hex()))
    open(dst, "wb").write(raw)

def pack(src_img3, macho, dst):
    b = bytearray(open(src_img3, "rb").read())
    raw = open(macho, "rb").read()
    comp = lzss_compress(raw)
    assert lzss_decompress(comp, len(raw)) == raw, "el compresor no ida-y-vuelta"
    hdr = b"complzss" + struct.pack(">III", adler32_apple(raw), len(raw), len(comp)) + b"\0" * (0x180 - 20)
    newdata = hdr + comp
    out = bytearray(b[:20])
    for m, off, t, d in img3_tags(bytes(b)):
        if m == b"DATA":
            pad = (-len(newdata)) % 4
            body = newdata + b"\0" * pad
            out += struct.pack("<4sII", b"ATAD", 12 + len(body), len(newdata)) + body
        else:
            out += b[off:off + t]
    total = len(out)
    struct.pack_into("<III", out, 4, total, total - 20, total - 20)
    open(dst, "wb").write(out)
    print("empaquetado: %s (%d bytes, lzss %d)" % (dst, total, len(comp)))

if __name__ == "__main__":
    if sys.argv[1] == "unpack":
        unpack(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "pack":
        pack(sys.argv[2], sys.argv[3], sys.argv[4])
