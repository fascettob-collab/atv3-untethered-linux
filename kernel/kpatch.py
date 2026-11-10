"""Etapa A: kernel de tvOS 12H1006 con PE_i_can_has_debugger() = 1.

Con eso AMFI y el kernel respetan los boot-args de desarrollo:
  cs_enforcement_disable=1 amfi_get_out_of_my_way=1
que desactivan la verificación de firmas de código. (Sin tocar nada más del kernel.)

  python kpatch.py   -> kernel.patched.macho y kernelcache.patched (IMG3 listo para mandar por iBEC)
"""
import struct
import ksym, kc_tool
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB

S = ksym.symbols()
fn = S["_PE_i_can_has_debugger"] & ~1
off = ksym.va2off(fn)
k = bytearray(ksym.K)

# Thumb: if (r0) *r0 = 0;  return 1;
new = bytes.fromhex("0028" "1cbf" "0021" "0160" "0120" "7047")
assert k[off:off + 2] == bytes.fromhex("08b1") or True
k[off:off + len(new)] = new

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
print("PE_i_can_has_debugger en %#x (archivo %#x), parcheado:" % (fn, off))
for i in md.disasm(bytes(k[off:off + len(new)]), fn):
    print("   %08x: %s %s" % (i.address, i.mnemonic, i.op_str))

open("kernel.patched.macho", "wb").write(k)
kc_tool.pack("kernelcache.release.j33i", "kernel.patched.macho", "kernelcache.patched")
