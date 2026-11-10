# scripts/ — one-shot entry points

These are the *operational* scripts. They were written for a specific setup
(Ubuntu PC "casa", Python 2.7 at a pyenv path, firmware in `~/fw`, ipwndfu
checkout at `~/ipwndfu`) — adjust the variables at the top to your layout.

| Script | What it does |
|---|---|
| `ramdisk-boot.sh` | Full chain: checkm8 → iBSS (patched) → iBEC (patched) → SSH **ramdisk** → waits for `ssh -p 2222 root@localhost` (via `iproxy`). The rescue/install environment. |
| `kernel-boot.sh` | Full chain: checkm8 → iBSS → iBEC → **tethered tvOS** with patched kernelcache → SSH up in ~30 s. |
| `verbose-boot.sh` | Boots stock iBoot disguised as iBEC with `-v` boot-args — tvOS with kernel text on HDMI. |
| `linux-checkm8.sh` | Just the checkm8 exploit (pwned DFU), no boot chain. |
| `auto-pwn.sh` | Helper: exploit-only wrapper used during development. |

Notes:
- The kernel must be the patched `xhci_hcd` (`ckm8_enable=1`, `ckm8_partial_len=64`).
- The exploit parameters (`/tmp/leak`, `/tmp/pad` etc.) are the tuned constants for
  `partial_len=64` — see `docs/journey.md` for how they were derived.
- After a **stock** boot with the untether installed, SSH takes **~3–5 minutes**
  (the jsc chain runs early in boot but sshd comes up late). Be patient.
