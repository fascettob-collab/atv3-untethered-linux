—# Tools installation plan (SSH and packages on tvOS 8.4.4)
> The original 3-phase plan: SSH ramdisk for disk access, tethered boot with patched kernel, and installing tools to the real disk.

# Plan: installing tools (SSH and packages) on the Apple TV 3 (tvOS 8.4.4)

Starting state: the Apple TV enters **pwned DFU** with checkm8 from the PC `casa` (recipe in `securerom/NOTAS.md`).

## What you need to know first
- **Step 6 depends on the previous steps.** With Apple's original kernel, any program without Apple's signature **won't run**. We can copy SSH to the disk, but to run it you need the **patched kernel** (steps 4 and 5) on every boot.
- **Everything is "tethered":** every boot with the tools goes through the PC (exploit → iBSS → iBEC → patched kernel). A normal boot still works: the added tools simply don't run.
- **You can always go back:** DFU is in the bootrom. Restoring to 8.4.4 returns the Apple TV to factory state. Verify first that Apple is still signing 8.4.4 for `AppleTV3,2` (ipsw.me).

## Phase 1: accessing the disk without modifying anything (ramdisk with SSH)
Goal: a root terminal inside the Apple TV, booting a minimal system in memory.
1. Check whether **Legacy iOS Kit** supports `AppleTV3,2` ("SSH Ramdisk") and whether it accepts an Apple TV already in pwned DFU. If not, build the ramdisk by hand: patched iBSS/iBEC (iBoot32Patcher) + kernel + ramdisk with `dropbear`.
2. Connect over USB: `iproxy 2222 22` and `ssh -p 2222 root@localhost`.
3. **Backup first:** copy the system and data partitions (`/dev/disk0s1s1`, `/dev/disk0s1s2`) to the PC with `dd`. This is the safety net.

**Done when:** you have a root terminal and the backup is on the PC.

## Phase 2: tethered boot with patched kernel (steps 1 to 5)
1. Download the 8.4.4 IPSW for `AppleTV3,2` and decrypt iBSS, iBEC and the kernelcache (keys from The Apple Wiki, or the AES engine with the Apple TV in pwned DFU).
2. Patch **iBSS/iBEC** (iBoot32Patcher): without signature verification and with boot-args (`-v cs_enforcement_disable=1 amfi_get_out_of_my_way=1`).
3. Patch the **kernel**: disable code signature verification (AMFI and `cs_enforcement`) and the sandbox for `/usr/bin` and `/usr/sbin`. Use the patches published for 32-bit iOS 8.4 as a guide.
4. Boot script on the PC: exploit → `irecovery` sends iBSS → iBEC → patched kernel → `bootx`.

**Done when:** the Apple TV boots normal tvOS, in verbose mode (`-v`), from the PC.

## Phase 3: installing the tools (step 6)
Everything for **armv7, iOS 8** (tvOS 8.4.4 is iOS 8 on the inside).
1. **Get the packages** from the old Cydia repos (for example `apt.saurik.com`, which still publishes `iphoneos-arm` packages for iOS 8): OpenSSH or dropbear, bash, coreutils, `dpkg` and `apt`.
2. **Prepare them on the PC:** unpack the `.deb` files (`dpkg-deb -x`) and **sign each binary with `ldid -S`** ("fake" signature; sufficient with the patched kernel).
3. **Copy them to the disk** from the phase 1 ramdisk: mount the system as writable (`mount_hfs /dev/disk0s1s1 /mnt1`) and copy to `/usr/bin`, `/usr/sbin`, `/usr/lib` and `/etc`.
4. **SSH auto-start:** a plist in `/Library/LaunchDaemons/` that launches `sshd`/`dropbear`. Generate the host keys.
5. **Command-line package manager:** `dpkg` and `apt` configured with an iOS 8 repo. The Cydia app doesn't work on tvOS (no touchscreen and no iPhone UIKit), so everything goes through the command line.
6. Boot tethered (phase 2) and log in over SSH, via Wi‑Fi or over USB with `iproxy`.

**Done when:** after a tethered boot you log into the Apple TV over SSH with tvOS working, and you install a package with `apt-get`.

## Risks and how they are covered
| Risk | Coverage |
|---|---|
| A broken LaunchDaemon prevents tvOS from booting | Phase 1 backup. Delete it from the ramdisk or restore 8.4.4 |
| The system partition is small | Install only the minimum, or move things to the data partition with symlinks |
| The iOS 8.4 kernel patches don't match tvOS 8.4.4 | Find the proper offsets. The emulator and disassembler we already built can be used to verify |
| Apple stops signing 8.4.4 | With checkm8 you can restore anyway, with patched iBSS/iBEC |

## Recommended order
Phase 1 → backup → phase 2 → phase 3. Phase 1 alone already gives root access to the disk and is useful by itself.
