# kernel/ — Linux xHCI patch (ckm8) + kernelcache patches

## ckm8: the Linux-side USB truncation

`checkm8` against the s5l8947 bootrom needs a USB SETUP transfer with
`wLength=0x800` to be **truncated to 64 bytes** mid-flight, with no STATUS
stage. Stock Linux hosts can't do that — so we patch the `xhci_hcd` driver:

- module params: `ckm8_enable` (arm the quirk), `ckm8_partial_len` (truncate size)
- the quirk triggers on the Apple DFU device (`05ac:1227`) with the magic
  `wIndex=0x8947` and rewrites the SETUP packet length

Two patch generations exist in this folder (the `.py` files apply the diff to
a kernel tree; the final working recipe used in this project was `7.0.14` with
`ckm8_partial_len=64` and the exploit constants retuned accordingly — see
`docs/journey.md`).

## kpatch.py: the Apple kernelcache patches

Unpacks the 12H1006 kernelcache (IMG3 + complzss — thanks to `kc_tool.py`),
applies patches and repacks:

- `_PE_i_can_has_debugger` → always report debugger enabled (gates AMFI's
  relaxed mode under `amfi_get_out_of_my_way=1`)

`kc_tool.py` unpacks/packs IMG3+complzss kernelcaches; `ksym.py` reads the
embedded symbol table (the 12H1006 kernel ships one — very handy for finding
offsets).
