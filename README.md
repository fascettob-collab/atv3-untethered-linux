# Apple TV 3 (tvOS 8.4.4) — Untethered SSH from a pure Linux PC

> **From a blank Linux box to untethered root SSH on the Apple TV 3 — no Mac required.**
> End result: the Apple TV boots from wall power alone and, ~5 minutes later, root SSH is available (`ssh root@<ip>`). Every boot. No PC involved.

This repo documents the complete journey and contains **all the tooling** built along the way: a checkm8 exploit chain driven by a custom-patched Linux kernel, SecureROM reverse-engineering notes, an SSH ramdisk, a full-disk backup system, and the final untethered install of the [etasonATV](https://etasonatv.tihmstar.net/) untether on **tvOS 8.4.4 (12H1006)** — a build combination not covered by existing tools.

## The milestone

| What | Status |
|---|---|
| Pwned DFU (checkm8) on **s5l8947 (A5)** from Linux | ✅ works first try |
| SecureROM fully reverse engineered + emulated (Unicorn) | ✅ |
| Boot chain without Apple signatures (bootrom → iBSS → iBEC → kernel) | ✅ |
| SSH ramdisk (USB) for disk access & backup | ✅ |
| Full disk backup (files + symlinks + keybags) | ✅ |
| **Untethered SSH — boots from power alone, ~5 min to sshd** | ✅ verified on 2 consecutive cold boots |

## How it works (the 3-minute version)

1. **Exploit** — [checkm8](https://github.com/axi0mX/ipwndfu) against the bootrom of the s5l8947. To make the USB SETUP truncation reliable, we run a **custom-patched Linux kernel** (xHCI driver: `ckm8_enable=1`, `ckm8_partial_len=64`) — see `kernel/`.
2. **Boot chain** — patched iBSS + iBEC (signature checks out, boot-args in), then either:
   - `ramdisk-boot.sh` → SSH **ramdisk** over USB (rescue/install environment), or
   - `kernel-boot.sh` → **tethered** tvOS with a patched kernelcache (instant SSH).
3. **Untether** — the [etasonATV](https://etasonatv.tihmstar.net/) mechanism installed to disk from Linux:
   ```
   launchd → /usr/libexec/rtbuddyd → (symlink to) jsc (Apple-signed ✓ AMFI passes)
       → jsc runs /--early-boot (expl.js, JSC ROP exploit, tihmstar)
       → untether.bin (kernel exploit + patches)
       → daemonload → launchctl load /Library/LaunchDaemons
       → sshd → root SSH, no PC, every boot
   ```

## Repo layout

```
docs/
  journey.md           ← THE full work log (RE notes → exploit → untether). Start here.
  untether-install.md ← the untether install plan + hard-won lessons
  tools-plan.md        ← the original 3-phase tools plan
kernel/               ← xHCI kernel patch (ckm8) + kpatch.py (kernelcache patches)
boot/                 ← iBSS/iBEC/iBoot/kernel loaders (Python 2.7 + usb)
ramdisk/              ← ramdisk builder (mk_kit, hfsgrow, wrap_rdsk, boot_ssh.sh)
tools/                ← standalone tools: hfsls.py (HFS+ reader w/ decmpfs!), etc.
scripts/              ← one-shot entry points: ramdisk-boot.sh, kernel-boot.sh
```

## Highlights you may find useful

- **`tools/hfsls.py`** — pure-Python HFS+ reader with **decmpfs support** (`uncat` command). Reads Apple's restore ramdisks (compressed files, extended attributes, resource forks) without a Mac. Also extracts IMG3 `DATA` payloads.
- **The jsc signature lesson** (see `docs/untether-install.md`): the jsc binary extracted from the dyld cache carries only an adhoc signature → AMFI rejects it at stock boots (`posix_spawn(): 85`). The jsc at `JavaScriptCore.framework/Resources/jsc` of the target system is fully Apple-signed and passes. Symlink, don't copy.
- **launchd on ATV3/tvOS 8.4**: custom LaunchDaemons go in **`/Library/LaunchDaemons`** (force-loaded by the untether's `daemonload`), not `/System/Library/LaunchDaemons`.
- **`authorized_keys`** must go on the **data partition** (`/private/var` mounts over the system partition's copy at boot).
- **fstab rw + stock kernel = boot loop**. Keep `ro`; the untether remounts rw itself.
- The untether chain takes **~3–5 minutes** after power-on before sshd listens — check SSH late, not at 60 s.

## Requirements

- A Linux PC (any distro) — the patched `xhci_hcd` module built from `kernel/` (or use `FUZZING`-free equivalent). Ubuntu generic kernel works for ramdisk building (hfsplus module).
- Python 2.7 (for the boot chain scripts) and Python 3 (for tools).
- Apple TV 3,2 (A1469) on tvOS 8.4.x (tested on 8.4.4/12H1006). Apple TV 3,1 (A1427) should work but needs the Arduino-based [checkm8-A5](https://github.com/synackuk/checkm8-a5) to enter pwned DFU.
- Apple firmware (iBSS/iBEC/kernelcache/DeviceTree) from the 8.4.4 IPSW — not included; see `docs/journey.md` for how each piece was decrypted (the GID key can be extracted with the device itself in pwned DFU).

## Quick start

```sh
# 1. pwned DFU + SSH ramdisk (rescue environment)
sudo ./scripts/ramdisk-boot.sh     # follow DFU instructions
ssh -p 2222 root@localhost          # via iproxy

# 2. untethered result — just power the Apple TV from the wall:
ssh root@apple-tv.local             # ~5 min after power-on
```

## Credits

- **axi0mX** — checkm8 / ipwndfu (the exploit and reference constants)
- **tihmstar** — etasonATV untether, the jsc technique, and answering questions the community asked years ago
- **NSSpiral** — [Blackb0x](https://github.com/NSSpiral/Blackb0x) (untether payload and reference layout)
- **regulad** — [Blackb0x--](https://github.com/regulad/Blackb0x--) (2026-maintained fork, CA injection docs)
- **synackuk / nyan_satan / a1exdandy** — checkm8-A5
- The iPhone Wiki, securerom.fun, and everyone who documented A5 boot chain internals before.

## License

MIT for the code in this repo. Firmware, exploits and payloads from third parties remain under their authors' terms (referenced, not included).

---
*Built as a personal preservation project — the Apple TV 3 is a great little box that deserved one more life.*
