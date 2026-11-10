# boot/ — loaders for the patched boot chain

Python 2.7 scripts (kept compatible with the ipwndfu environment) that run
against the Apple TV in pwned DFU / recovery.

| Script | What it does |
|---|---|
| `boot_ibss.py` | Loads the patched iBSS (signature patch at `0x34005E6E`, trampoline v2, jumps). Device shows as `Apple Mobile Device (BAUT MOD)`. |
| `send_ibec.py` | Loads the patched iBEC with custom boot-args. Shows as `BAUT IBEC MOD`. |
| `send_iboot.py` | Boots stock iBoot disguised as iBEC (HDMI on, `-v` — tvOS boots normal with kernel text). |
| `boot_kernel.py` | iBEC stage + DeviceTree + patched kernelcache + `bootx` → tethered tvOS. |
| `boot_ramdisk.py` | iBEC stage + ramdisk + DeviceTree + patched kernel + `bootx` → SSH ramdisk. |
| `ibsstool.py` / `ibectool.py` / `iboottool.py` | Patch helpers for each bootloader image (signature patches, string replacement). |
| `tramp_gen.py` | Generates the iBSS trampoline (v2, 160 bytes, verified in place). |
| `mk_flush_payload.py` | Builds the USB-flush stub appended to the checkm8 payload (disables EP0-IN, drains TX FIFOs — without it, IN responses lag one request behind). |
