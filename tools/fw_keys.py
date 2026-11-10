#!/usr/bin/env python3
"""Desencriptar el arranque de tvOS 8.4.4 (AppleTV3,2) con el motor AES de la bootrom.

  python3 fw_keys.py fetch            -> baja solo iBSS/iBEC/iBoot del IPSW y muestra los KBAG
  python3 fw_keys.py decrypt <archivo> <IV+KEY en hex>   -> desencripta la parte DATA del IMG3

Requiere: pip install --user --break-system-packages remotezip ; openssl en el sistema.
"""
import sys, json, struct, subprocess, urllib.request

DEVICE = "AppleTV3,2"
WANT = ("iBSS", "iBEC", "iBoot")

def ipsw_url(build="12H1006"):
    # es el build que tiene la Apple TV (ideviceinfo: BuildVersion 12H1006)
    data = json.load(urllib.request.urlopen("https://api.ipsw.me/v4/device/%s?type=ipsw" % DEVICE))
    for fw in data["firmwares"]:
        if fw["buildid"] == build:
            return fw["url"], fw["buildid"]
    raise SystemExit("no encontre el build %s" % build)

def img3_tags(blob):
    if blob[:4] != b"3gmI":
        raise SystemExit("no es IMG3")
    off, tags = 20, []
    while off + 12 <= len(blob):
        magic, total, dlen = struct.unpack("<4sII", blob[off:off + 12])
        tags.append((magic[::-1].decode("latin-1"), blob[off + 12:off + 12 + dlen]))
        off += total
        if total == 0:
            break
    return tags

def kbags(blob):
    out = []
    for name, data in img3_tags(blob):
        if name == "KBAG":
            state, aes = struct.unpack("<II", data[:8])
            klen = aes // 8
            out.append((state, aes, data[8:24].hex(), data[24:24 + klen].hex()))
    return out

def cmd_fetch():
    from remotezip import RemoteZip
    url, build = ipsw_url()
    print("IPSW:", url, "build", build)
    with RemoteZip(url) as z:
        for n in z.namelist():
            base = n.split("/")[-1]
            if any(base.startswith(w) for w in WANT) and "RELEASE" in base:
                blob = z.read(n)
                fn = base
                open(fn, "wb").write(blob)
                print("\n%s (%d bytes)" % (fn, len(blob)))
                for state, aes, iv, key in kbags(blob):
                    tipo = "PRODUCCION" if state == 1 else "desarrollo"
                    print("  KBAG %s AES-%d" % (tipo, aes))
                    print("    para ipwndfu --decrypt-gid=%s%s" % (iv, key))

def cmd_decrypt(fn, ivkey):
    blob = open(fn, "rb").read()
    data = dict(img3_tags(blob))["DATA"]
    iv, key = ivkey[:32], ivkey[32:]
    enc = data[: len(data) // 16 * 16]
    out = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-nopad", "-K", key, "-iv", iv],
                         input=enc, capture_output=True, check=True).stdout
    dst = fn + ".dec"
    open(dst, "wb").write(out)
    texto = [s for s in out[:0x400].split(b"\0") if len(s) > 6][:4]
    print("guardado", dst, len(out), "bytes")
    print("primeros textos:", texto)

if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "fetch":
        cmd_fetch()
    elif len(sys.argv) == 4 and sys.argv[1] == "decrypt":
        cmd_decrypt(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
