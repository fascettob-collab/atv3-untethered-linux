# Installing the untether (etasonATV) — plan and lessons
> The step-by-step reasoning that led to the untethered install: LaunchDaemons in /Library/LaunchDaemons, the Apple-signed jsc, the /private/var mount shadowing authorized_keys, and why the chain takes ~5 minutes.

# Plan: permanent SSH on tvOS (phases 2+3 together)

Starting state (2026-11-10): the Apple TV boots into **pwned DFU** and boots a **ramdisk with SSH** over USB (`ramdisk-boot.sh` → `iproxy` → `ssh -p 2222 root@localhost`). **The full disk backup is already on the PC** (`~/backup/apple-tv`, 2.5 GB, files + symlinks + keybags).

Goal: **tethered boot of normal tvOS with its own SSH**, no RAM disk. Once installed, every boot is: DFU → `kernel-boot.sh` → direct SSH (over Ethernet or USB).

## Core idea
Everything to be installed **is already running on the ramdisk** (sshd + bash + libraries come from the kit). The install is copying from the ramdisk itself to `/mnt1` (the real system partition) mounted read/write. **No PC→device channel is needed**: it's a local copy inside the Apple TV.

## Step 0 — prerequisites (done or to verify)
- [x] Full backup on the PC
- [x] Tethered boot chain with patched kernel (`kernel-boot.sh`)
- [ ] Verify free space on `/mnt1` (small system partition; if not enough → data partition + symlinks)

## Step 1 — install SSH to the real disk (from the ramdisk)
Boot: `sudo ~/ramdisk-boot.sh` + Apple TV in DFU (same as today), then SSH into the ramdisk:
1. Mount the system read/write: `/sbin/mount_hfs /dev/disk0s1s1 /mnt1` **without** `-o ro` (check `mount` shows `rw`; if it resists, `mount -u -w /mnt1`).
2. Copy from the ramdisk to `/mnt1` (everything is additive, nothing Apple gets overwritten):
   - `/usr/sbin/sshd` → `/mnt1/usr/sbin/`
   - `/bin/bash` → `/mnt1/bin/` (if tvOS has no bash; verify against the backup)
   - `libcrypto.0.9.8.dylib`, `libz.1.2.5.dylib`, `libgcc_s.1.dylib`, `libncurses`/`libreadline` (if used) → `/mnt1/usr/lib/`
   - `/private/etc/ssh/{sshd_config,ssh_host_rsa_key,ssh_host_ecdsa_key}` → `/mnt1/private/etc/ssh/`
   - `authorized_keys` → `/mnt1/private/var/root/.ssh/`
3. Create `/mnt1/System/Library/LaunchDaemons/com.bauti.sshd.plist` (own LaunchDaemon, `RunAtLoad`, `KeepAlive`, `UserName root` — simple form already tested). For the plist, copy from the ramdisk with `dd` (see "reverse channel" below if something is missing).
4. Correct `chmod` (keys 600, sshd 755, plist 644, directories 755).
5. Clean unmount: `umount /mnt1` (or `mount -u -r`).

**Reverse channel (only if something is missing on the ramdisk):** reverse streamer — a `receiver.sh` script on the device reads "F <size> <path>" from stdin and writes with `dd of=`. On the PC: a `python` that emits the stream. (Fallback if any file/plist is not on the ramdisk.)

**Done when:** from the ramdisk, `/mnt1/System/Library/LaunchDaemons/` contains the plist and `ls -l` of everything copied is correct.

## Step 2 — boot tethered tvOS and test SSH
1. `sudo ~/kernel-boot.sh` (same chain: exploit → iBSS → iBEC → `boot_kernel.py` with kernelcache.patched + DeviceTree, boot-args `-v amfi_get_out_of_my_way=1`).
   - Note: `kernel-boot.sh` doesn't watch USB after bootx today; add monitoring (wait for `05ac:12a7`).
2. Wait for the full tvOS boot (menu on the TV).
3. **SSH over the network**: the Apple TV is on Ethernet → router DHCP → `ssh root@<IP>` (find it with `nmap`/router or `arp`). If the cable doesn't link up, try already-configured Wi-Fi.
4. **SSH over USB** (always available): `iproxy 2222 22` + `ssh -p 2222 root@localhost`.
5. Verify inside: `uname -a` (kernel xnu-2784.40.6 with `PE_i_can_has_debugger` patched — confirm with `sysctl` if possible), running processes, `launchctl list | grep sshd`.

**Done when:** you get in via SSH to normal tvOS (with the patched kernel) after a tethered boot.

## Step 2b — the untethered test (try this before anything else!)
**NVRAM survives power loss.** If we leave `boot-args` with relaxed AMFI, the stock iBoot passes it to the stock kernel on **every normal boot without a PC** — and with relaxed AMFI, the sshd LaunchDaemon (unsigned) would run on its own:

1. Just once (from the ramdisk or pwned DFU): `nvram boot-args="amfi_get_out_of_my_way=1"` (maybe add `-v` to see it on the TV).
2. **Unplug the Apple TV from the PC and from power. Plug it into power only.**
3. Wait for the normal tvOS boot (menu on the TV) and test `ssh root@<IP>` / `iproxy`.

Result A — **SSH answers**: it's **untethered**. The PC is only needed for maintenance. Plan ends here (step 4 for convenience).
Result B — no answer: continue with the tethered boot from step 2 (nothing is lost) and diagnose: did launchd run the plist? (get in via ramdisk and check launchd logs), did sshd die from signing? (step 3), no IP over the network? (try USB).

Technical note: with `amfi_get_out_of_my_way=1` the stock kernel (WITHOUT patches) already accepts ad-hoc code — that's what makes the ramdisk work. If more is needed (cs_enforcement), add it to the boot-arg; if a kernel patch is needed, fall back to step 3.

## Step 3 — if AMFI gets in the way (contingency)
If `sshd` doesn't start or binaries die with "Killed: 9" (code signing):
1. Add boot-args: `cs_enforcement_disable=1` alongside `amfi_get_out_of_my_way=1` in `kernel-boot.sh` (BOOT_ARGS).
2. If it still happens: the classic iOS 8 kernel patches for AMFI (`kpatch.py`: AMFI `__TEXT` checks) — find offsets with the kernelcache symbol table (we already have it).
3. The `/usr/bin` sandbox: only if sshd fails with "Operation not permitted" on file operations.

## Step 4 — convenience (after it works)
1. A `tvos-boot.sh` script that ties it all together: exploit → iBSS → iBEC → kernel → notice "SSH ready at <IP>".
2. `nvram auto-boot=true` at the end of ramdisk-boot.sh is already done; check that a NORMAL boot (without PC) still works — the Apple TV boots stock tvOS, without our tools (the sshd plist stays on disk, but without a patched kernel the unsigned binaries won't run → harmless).
3. Post-install disk backup (streamer pass 2).

## Risks and coverage
| Risk | Mitigation |
|---|---|
| `/mnt1` won't mount RW | Try `mount -u -w`; last resort: kernel patches (rootfs RW) |
| Insufficient space on `/mnt1` | Install the minimum (sshd ~720 KB + libcrypto 1.6 MB); otherwise, data partition + symlink |
| A broken LaunchDaemon hangs tvOS | Delete the plist from the ramdisk (phase 1) or restore the backup |
| Binaries die from signing (AMFI) | Step 3 |
| Something really breaks | DFU always available + full backup + signed 8.4.4 restore via checkm8 |

## Execution order
Step 1 (install) → step 2 (boot + test) → if it fails: step 3 → step 4 (convenience). Phase 1 (ramdisk) remains the permanent rescue/install tool: **nothing gets deleted from it**.
