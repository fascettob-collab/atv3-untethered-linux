# The Journey — from blank Linux PC to untethered SSH on Apple TV 3
> Full work log (originally in Spanish). Covers: SecureROM reverse engineering, the checkm8 exploit, custom patched Linux kernel (xHCI), iBSS/iBEC chain, SSH ramdisk, disk backup, and the final untethered install.

# SecureROM S5L8947 (Apple TV 3, iBoot-1458.2): RE notes

## The file
- `SecureROM_s5l8947x_iBoot-1458.2.bin`: 65536 bytes, SHA256 `59B9E378…2B5405`.
- Source: https://securerom.fun/ ("SecureROM for s5l8947xsi, iBoot-1458.2").
- Header at 0x200: `SecureROM for s5l8947xsi, Copyright 2011, Apple Inc. … RELEASE`.

## How to open it
- **Ghidra:** Import → Raw Binary → Language `ARM:LE:32:v7` → Base address `0x0`. The code is Thumb‑2; in Ghidra mark the functions with `TMode=1` (or start disassembly with "Disassemble Thumb").
- RAM (SRAM): `0x34000000` onward. Add an uninitialized memory block `0x34000000–0x34040000` so that references resolve.
- Quick tool without Ghidra: a capstone script (`romtool.py`: `dis <addr> <n>`, `callers <addr>`, `lit <value>`).

## Anchor points (from ipwndfu, verified in the ROM)
| Address | What it is |
|---|---|
| `0x7BC8` | DFU class request handler (the one ipwndfu hooks). Verified: compares `bRequest` against 1/4/6 and `wLength` against `0x800` |
| `0x79EC` | `usb_core_do_io` (only direct caller: `0x7CFE`) |
| `0x72A8` | `usb_create_string_descriptor` |
| `0x3402D8D4` / `0x3402D8D8` / `0x3402D8E0` | DFU state (status, GETSTATUS bytes, struct with the buffer pointer at `+0x10`) |
| `0x3402D87C` | `gUSBDescriptors` |
| `0x3402DDF8` | `gUSBSerialNumber` |
| `0x3402D92C` | Pointer to the handler (PAYLOAD_PTR) |
| `0xA6E0` | The only `0x800` literal in the ROM: probably the DFU buffer size (`malloc(0x800)`) |

## Heap (verified in the code)
- `malloc` = `0x3994`, `free` = `0x3A18`, `memalign` = `0x3B3C`, `memset` = `0x9D70`. Heap global: `0x3402CF40` (bins at `+0x28`).
- Block header of **0x20 bytes** before the data: word 0 = previous block size (`(w0<<3)&~0x1F`) plus flags (bit0 = free, bit1 = previous free); word 1 = size in units of 32 bytes. Free blocks have `next`/`prev` at `+0x20`/`+0x24`.
- `free()` validates the header against the neighbour. If it doesn't match: **panic** (`0x3B34`) = hang.
- DFU buffer: `memalign(0x800, 0x20)` at `0x7B30`, stored at `0x3402D8E0+0x10`. It's freed at `0x7DF0` (DFU exit).
- **USB request** (`usb_core_do_io` `0x79EC`): `malloc(0x1C)` → 0x40 block (0x20 header + 0x20 data). Fields: `+0x0` endpoint, `+0x4` buffer, `+0xC` length, **`+0x14` callback**, `+0x18` next. Matches ipwndfu's `struct.pack('<20xI4x', cb)`.

- **Complete request** `0x79D0`: `if (req->cb) req->cb(req); free(req);`. Called from `0x30DA`, `0x3352`, `0x36A6` and `0x392C` (USB controller driver, including the reset path). In `usb_core_do_io`, if the endpoint is `0x80` and there's no buffer, it uses the default buffer `0x3402D760`.
- Interpretation of the dumps: the block with header at 0x5A0 and data at 0x5C0 **is a pending request that gets completed on reset**. Overwriting only the header makes `free` panic (hang). Overwriting the request fields with zeros makes the reset not recognize it (recovery).
- For the callback to be called you have to leave **a valid header** (`w0=8`, prev 0x40; `w1=2`, size 0x40) and **plausible request fields** (`ep=0x80`, `buf=0x3402D760`, `len=0x40`, `cb` at `+0x14`).

- **USB reset event** (`0x7914`, event 2): first `abort(0x80)` (`0x35A4`), which walks the EP0‑IN queue (head at `0x3402CD40 + idx*0x28 + 0x38`, next at `req+0x18`), sets `req[8]=1` and calls `0x79D0` (callback and free) **without validating the fields**. Then it calls each interface's reset handler (`iface+0x38`).
- **DFU reset handler** `0x7DC4`: if the DFU state (`0x3402D8D4`) is **8** (`dfuMANIFEST-WAIT-RESET`), it marks the job "done" and signals. The bootrom leaves DFU and boots → **this is the "recovery" we see**.
- Test of the complete fake request at 0x5C0 (valid header and fields `ep=0x80`, `buf`, `len`, `cb`): **recovery with both addresses** (6 attempts). Since `abort` doesn't validate fields, if that block were in the EP0‑IN queue the invalid callback would hang. **The 0x5C0 block is not the request queued on EP0‑IN.**
- Next RE question: why does the DFU state get to 8? Look for where 8 is written to `0x3402D8D4`. It's possibly the DNLOAD data callback (`0x7D18`, registered as `0x7D19`) running on an EP0‑OUT request that we overwrite.

- **There's no `strb #8`** to the DFU state anywhere in the ROM (only 2, 5, 6 and 0xA). The DFU exit happens through `0x3402D8D0 = 1` and the signal at `+0x1C`. The places that trigger it: `0x7C86` (**CLRSTATUS(4)/ABORT(6)** requests: if it wasn't in progress, it sets result −1 and returns), `0x7D70` (data callback with a failed `0x67DC` check) and `0x7DDA` (reset with state 8).
- **CLRSTATUS kicks the bootrom out of DFU** (`dfu_exit` `0x7DF0` frees the buffer `0x3402D8E0+0x10`) and it goes back in → **that's the origin of the checkm8 use‑after‑free on this chip**. It lines up with "(DFU loop)".
- `GETSTATUS` measured: before and after the marked step = `[0, 50, 0, 0, 2, 0]` (no error, state 2 idle). The marked step doesn't break the DFU state. Recovery is decided later: in the overwrite and the final reset.

## Emulator (`emu/emu.py`, Unicorn)
- **Use Unicorn 2.0.1.post1** (with `setuptools<70` for `pkg_resources`). 2.1.4 executes Thumb‑2 IT blocks incorrectly (skips instructions inside `free()` and ends in a fake panic).
- Starts from `0x0` with SRAM at `0x34000000` (0x40000) and MMIO mapped on demand. Minimal peripheral simulation: clock gates at `0x3F101xxx` (state = requested), PLL lock at `0x3F102xxx` (bit 30), and repeated reads that alternate between 0 and 0xFFFFFFFF.
- **Heap verified:** initialized at `0x6010` with region `0x3402DEFC`–`0x34039000`. First allocations: `malloc(0x1C)` → `0x3402DF40`, `malloc(0x100)` → `0x3402DF80`, `malloc(0x98)` → `0x3402E0A0`.
- **Interrupts:** controller at `0x3F200000`. Event at `0x3F202004` (`0x1xxxx` = external IRQ with the number in bits 0‑8; `0x70001`/`0x70004` = timers). Handler table at `0x3402C2E0` (idx*12: `+0xC` function, `+0x10` arg). IRQ vector `0x6D98` → `0x6F90` → `0xBBC`. The emulator injects a timer tick on every `WFI`.
- **64-bit timer:** low `0x3F200020`, high `0x3F200028`. It reads high‑low‑high and repeats if the high word changed.
- **Boot loop** `0x810`: `0x4F8C` returns the device type; **3 = DFU over USB** (`0x868` → `0x7AE8`). The emulator forces r4=3 at `0x8FC`.
- **In DFU (emulated):** `memalign(0x800, 0x20)` → **DFU buffer = `0x3402E300`** (up to `0x3402EB00`). The next allocations are `malloc(0x19)` → `0x3402EB20` and `0x3402EB60`. USB IRQ = **0xB** (handler `0x2EBC`), IRQ 0x1C = peripheral at `0x32000000`.
- **USB (Synopsys DWC OTG at `0x36100000`, DMA mode):** GINTSTS `+0x14` (bit 12 reset, bit 13 enumdone, bit 19 OUT EP, bit 18 IN EP). DAINT `+0x818`. DOEPINT0 `+0xB08` (bit 3 = SETUP). DOEPDMA0 `+0xB14` = **`0x3402CD00`** (the 8 SETUP bytes are written there). DIEPINT0 `+0x908`.
- **Where it used to stall:** at `WFI` (`0x804`). The task system waits for interrupts (timer and USB). To reach DFU you need to emulate the interrupt controller and a timer, and then the USB controller (Synopsys OTG at `0x3610xxxx`) with the exploit's traffic.

## Emulator result with the exploit sequence (`emu/host.py exploit leak=626`)
- Phase A: stall + 626 leaks → the EP0‑IN queue holds 628 requests (`0x3402EBA0`…`0x34038860`). They fill the heap.
- Phase B: DNLOAD 0x800 truncated to 64 bytes + CLRSTATUS → `dfu_exit` frees the old buffer `0x3402E300`. On re-entry, the new `memalign(0x800)` lands at **`0x3402E0C0`** (a different place, because the heap is full).
- Phase C: stall + leak → **the head of the EP0‑IN queue is `0x3402E960` = old buffer + 0x660** (the ipwndfu value).
- The overwrite is written through the dangling pointer, **starting at old buffer + 0x40** (the 64 bytes of the truncated DNLOAD have already advanced the pointer).
- **Correct padding with `partial_len=64`: 0x620** (callback at 0x634). With that, the emulator **jumps to `0x34000000` from `usb_complete` (`lr=0x79E1`)**.
- The real-world tests never tried 0x620 with the ipwndfu structure: the sweeps went in steps of 0x40 (0x5C0, 0x600, 0x640…).

## ✅ RAMDISK WITH WORKING SSH (2026-11-10)
`ssh -p 2222 root@localhost` (via `iproxy 2222 22` at home) against the disk in RAM. **Phase 1 of the plan complete.**

#  UNTETHERED SSH ACHIEVED (2026-11-10, midnight) — NO PC, JUST POWER
**REPEATABILITY VERIFIED: 2 consecutive cold boots → root SSH on its own, at ~5 min.** ✓✓
The Apple TV 3 boots normal tvOS from power and at ~3-5 minutes root SSH is available at `192.168.0.109` (and over USB with `iproxy`). **Final project goal: COMPLETE.**

## Final recipe installed on the disk (everything verified byte-exact)
| Piece | Status |
|---|---|
| `/usr/libexec/rtbuddyd` → **symlink to the framework's jsc** (`/System/Library/Frameworks/JavaScriptCore.framework/Resources/jsc`, valid Apple signature with CMS → passes AMFI on stock boot) | ✓ |
| `/--early-boot` = tihmstar's `expl.js` (17 KB, JavaScriptCore+ROP exploit) | ✓ |
| `/untether/untether.bin` (payload: kernel exploit + patches, modified Blackb0x version) | ✓ |
| `/usr/bin/orphan_commander` + `/private/etc/rc.d/daemonload` (forces `launchctl load /Library/LaunchDaemons` via syslogd) | ✓ |
| `/usr/bin/dirhelper` (Blackb0x, remounts / rw + runs /etc/rc.d) | ✓ |
| `/Library/LaunchDaemons/com.bauti.sshd.plist` → `/usr/sbin/sshd -D` | ✓ |
| sshd + bash + libcrypto.0.9.8 + readline/ncurses + config + host keys | ✓ |
| `authorized_keys` on the **data partition** (`/private/var/root/.ssh/` — the system one ends up hidden by the mount) | ✓ |
| fstab: `ro` (**do NOT put rw!** the stock kernel without the rootfs patch hangs) | ✓ |
| NVRAM: `auto-boot=true`, `boot-args=amfi_get_out_of_my_way=1` | ✓ |

## Lessons from the road (for the RE NOTES)
1. **The untether chain takes ~3-5 min** from boot until sshd listens — checks at 30-60s gave false negatives (this cost us hours).
2. Our own LaunchDaemons go in `/Library/LaunchDaemons` (launchd doesn't scan /System/Library/LaunchDaemons for third-party plists on ATV3 tvOS 8.4).
3. `authorized_keys` goes on the DATA partition (the system one stays hidden under the /private/var mount).
4. The jsc "binary extracted from the cache" (Blackb0x rtbuddyd.bin) has an adhoc signature without CMS → AMFI rejects it on stock boot (errno 85 "Bad executable"); the jsc from the system's OWN framework has a full Apple signature ✓.
5. fstab rw at boot = boot fails with a kernel that has no rootfs patch (it falls back to recovery).
6. The ramdisk timer (boot_ssh.sh) leaves `auto-boot=false` — a soft reboot from the ramdisk always falls into recovery; a cold power cycle respects auto-boot (set it with `nvram auto-boot=true` + sync).
7. `iflag=fullblock` doesn't exist in coreutils 8.12 (the ramdisk's dd) — for large files, use a dedicated SSH session with `dd of=... bs=1048576` reading from stdin until EOF.
8. The stock 12H1006 kernel is called `MarijuanARM_S5L8947X`; our kernelcache.patched keeps `RELEASE_ARM`.

## State of the ecosystem pieces
- **Normal boot (no PC)**: factory tvOS + untether → root SSH at ~5 min ✓
- **Tethered boot** (`kernel-boot.sh`): tvOS with patched kernel + SSH (faster)
- **Rescue ramdisk** (`ramdisk-boot.sh`): disk access over USB
- **Full backup** at `~/backup/apple-tv` (pre-jailbreak)
- Optional pending: dyld cache patch (daibutsu/haxx, compiled at home in `/tmp/haxx`, `/tmp/dsc_patched` ready) in case we ever want AMFI fully off for tweaks — it was NOT needed.

### Tethered SSH detail (intermediate)
`ssh -i ~/.ssh/id_ed25519 root@192.168.0.109` against **real tvOS 8.4.4** (Darwin ashe-anashe).
Full chain: checkm8 → iBSS → iBEC → kernelcache.patched → bootx → tvOS → **the whole untether runs** (launchd spawns rtbuddyd=jsc → /--early-boot → expl.js → untether.bin → kernel exploit → dirhelper/daemonload → launchctl load /Library/LaunchDaemons → sshd) → root SSH.

The detail we were missing (the final bug): `authorized_keys` was going into `/mnt1/private/var/root/.ssh` (SYSTEM partition) but at boot the DATA partition is mounted ON TOP of `/private/var` and hides it. Fix: `/mnt2/root/.ssh/authorized_keys` (+ a copy in `/mnt1/private/etc/ssh/`).

## End-of-day status
- **Tethered SSH: WORKS** (boot with kernel-boot.sh = exploit + patched kernel → SSH over the network or USB)
- **Untethered (no PC): ONE piece missing** — on a STOCK kernel boot, launchd rejects rtbuddyd: `posix_spawn(): 85: Bad executable (or shared library)` (AMFI rejects the signature of the jsc extracted from the cache). With the patched kernel it runs perfectly.
- Ideas for a pure untethered:
  1. Get a jsc with a valid Apple signature (tihmstar's design assumes "Apple's own binary with valid code signature") — e.g. a standalone jsc from the iPhoneOS SDK, or figure out why the embedded signature (1584 bytes) doesn't validate.
  2. Patch AMFI persistently... (impossible without the bootchain).
  3. Ask for the rtbuddyd from the regulad/Blackb0x-- fork (maintained in 2026, maybe a new signature).
  4. Inspect from the tethered SSH how AMFI validated it (signature log).

## etasonATV untether installed (2026-11-10 evening) — PENDING DEBUG
We installed to the disk (`/mnt1`, everything verified byte-exact with the streamer):
- `/usr/libexec/rtbuddyd` = jsc (Apple-signed) → on every boot, launchd spawns it (label `com.apple.rtbuddyd` confirmed in the system's jetsam plist)
- `/--early-boot` and `/untether/expl.js` (JavaScriptCore exploit), `/untether/untether.bin` (the version MODIFIED by NSSpiral, not orig_untether.bin)
- `/usr/bin/orphan_commander`, `/private/etc/rc.d/daemonload` (runs `orphan_commander -w syslogd 'launchctl load /Library/LaunchDaemons'`), `/usr/bin/dirhelper` (remounts / rw + runs /etc/rc.d)
- `/Library/LaunchDaemons/com.bauti.sshd.plist` (daemons go there, NOT in /System/Library/LaunchDaemons — that was one of our bugs)
- sshd + bash + libcrypto + config + keys already installed from before (verified working in the ramdisk)

**Doesn't work yet**: tvOS boots normally but 22 stays closed. No jsc crash reports. The boot syslog couldn't be captured (idevicesyslog has to be running BEFORE the power cycle; `/tmp/sysloop2.sh` at home).

Next debug steps:
1. **With the ramdisk, run `/mnt1/usr/libexec/rtbuddyd --early-boot` by hand** and see what happens (does the exploit run? does jsc die? kernel panic?). It's the direct test of the whole chain.
2. Capture the syslog during the power cycle (sysloop2 running before unplugging).
3. Check how launchd launches rtbuddyd (with what argv? `--early-boot`?) — jsc interprets argv as script files, the name "/--early-boot" comes from cwd=/.
4. Hypothesis if it runs and fails: `untether.bin` with offsets for another kernel (12H876/885 vs our 12H1006). Blackb0x's modified version claimed to support 8.4.x. Alternative: use the untether from the `regulad/Blackb0x--` fork (maintained in 2026).

Tools created today: `hfsls.py` (decmpfs `uncat`), `macho_deps.py`, `unstream.py`, `apply_links.py`, reverse streamer (`receiver.sh`/`send_untether.sh` — path parsing: `path=${line#F $sz }`), canary markers. All in `casa:/tmp` and in `emu/`.


## Permanent SSH on tvOS — intermediate diagnosis (2026-11-10 afternoon)
Install to the real disk (`/mnt1`) verified and surviving (the "journal rollback" was false: I was looking at an unmounted /mnt1). In the ramdisk everything works: `/mnt1/bin/touch` exec ✓, `/mnt1/usr/sbin/sshd -t` with config+keys installed → rc=0 ✓, `sshd -D` listens ✓, `launchctl load` accepts the plist ✓.

On the REAL tvOS boot (tethered with patched kernel and untethered with stock kernel): port 22 closed, no crash reports, and the syslog captured with `idevicesyslog` shows that launchd loads all the daemons but **doesn't even mention com.bauti.sshd**.

Canaries installed at `/mnt1/System/Library/LaunchDaemons/com.bauti.canary.plist`:
- `CANARY2` = created by launchd (signed) via StandardOutPath → proves that launchd runs our jobs
- `CANARY` = created by /bin/touch (ours, unsigned) → additionally proves that AMFI lets unsigned code run

Reading the results (after idevicecrashreport):
- Only CANARY2 → AMFI kills the unsigned stuff (kernel not patched or insufficient boot-args) → keep going tethered or install the etasonATV untether
- CANARY and CANARY2 → launchd+AMFI OK; the problem is sshd itself (probably dyld/libs against the cache)
- Neither → launchd isn't reading /mnt1 (partition or scan)

Other data:
- Blackb0x (github.com/NSSpiral/Blackb0x) = **public untethered jailbreak for AppleTV3,2 tvOS 8.4.x** (tihmstar's etasonATV jsc untether): confirms that the untethered is feasible and how it does it (exploits JavaScriptCore at boot from the disk). It's a macOS app.
- The factory iBEC's USB in recovery sometimes ends up "misaligned" (commands have no effect): it's fixed by unplugging EVERYTHING and plugging it back in (re-enumeration).
- `irecovery -n` from that state may do nothing; a full power cycle with auto-boot=true boots normal tvOS.

### Full backup (phase 1, 2026-11-10)
- `~/backup/apple-tv/{system,data}`: 15,704 files, 2.4 GB, 4,423 directories (system = /mnt1, data = /mnt2).
- Raw stream in `~/backup/apple-tv-backup.stream` + `emu/unstream.py` (reassembler) + `emu/apply_links.py` (symlink targets from `~/backup/symlinks.tsv`).
- **`readlink` is missing in the ramdisk**: symlinks are recovered with `ls -l` (separate pass, see `/tmp/symlinks.sh` at home).
- The data partition includes `keybags` (file keys) — a future restore has everything.
- When done: `nvram auto-boot=true` before unplugging (boot_ssh.sh leaves it at false).

Root causes found (3 chained bugs):
1. **`restored_external`'s plist replaced**: the kit pointed its plist at `boot_ssh.sh`, so `restored_external` never ran → nobody brought up the USB restore-mode → no usbmux → no SSH (and no USB on the bus: xHCI didn't see a SINGLE connection event during the ramdisk). Starting it by hand from bash doesn't help: it needs launchd's spawn. **Fix**: original Apple plist restored (extracted from the factory ramdisk with decmpfs, see `hfsls.py uncat`) + our own `com.bauti.bootssh.plist` for `boot_ssh.sh`.
2. **Apple-style bootssh plist didn't work**: with `POSIXSpawnType`/`StandardOutPath` launchd wouldn't spawn it. The form that works: `Label`/`ProgramArguments`/`RunAtLoad`/`KeepAlive=false`/`UserName=root` (the same one the original replaced plist had).
3. **launchctl is in `/bin/launchctl`** (not `/usr/bin`).

Details of the working ramdisk:
- The USB shows up as `05ac:12a7 TV Device` ~8 s after bootx (usbmux up).
- `restored_external` runs as PID 6 (seen with `/bin/launchctl list`).
- `bautlog` in NVRAM works if the variable is pre-created with `setenv`+`saveenv` from the factory iBEC (the ramdisk's `nvram` doesn't create new variables). Trace: `ini;sh;lo0=0;l=[lo0];en0:no;...;sshd=0;restored:no` (false: launchctl is at another path).
- **`/` ends up mounted read-only** (`mount -u -w /` fails) → `/tmp/quedarse` can't be touched; the reboot timer is disarmed with `launchctl remove com.bauti.bootssh`.
- **Opening `/dev/rdisk*`/`/dev/disk*` gives EPERM** even as root without sandbox (mount via kernel does work). Raw NAND backup with dd: still to be solved (entitlements?).
- **File-level backup**: `mount_hfs /dev/disk0s1s1 /mnt1` (system) and `disk0s1s2 /mnt2` (data) OK. Bash streamer (`streamer.sh`: per-file dd with F/D/L header) + `emu/unstream.py` on the PC. Backup at `~/backup/apple-tv-backup.stream`.
- Missing in the ramdisk: `libiconv.2.dylib` (breaks `/bin/cat`), `head/tail/wc` are not in /bin. `dd` doesn't accept the lowercase `m` suffix (use `M`).
- `ideviceinfo` hangs against the ramdisk (there's no lockdown) — useful to tell the ramdisk apart from normal tvOS.

## ✅ PWNED DFU ACHIEVED (2026-11-09)
`Device is now in pwned DFU Mode.` and `iSerial 6 CPID:8947 … SRTG:[iBoot-1458.2] PWND:[checkm8]`, on the 2nd attempt.
Full recipe:
- Linux PC with the `7.0.14-ckm8` kernel (patched xHCI): `ckm8_enable=1`, `ckm8_partial_len=64`.
- ipwndfu: `large_leak=626`; async step replaced by a marked DNLOAD 0x800 (`wValue=0xC8C8`) that the kernel cuts to 64 bytes without STATUS.
- Overwrite: `'\0'*0x620 + struct.pack('<20xI4x', 0x340002A4)`.
- Payload: ipwndfu's for the 8947 plus an ARM stub (`emu/mk_flush_payload.py`) that calls the shellcode and then disables EP0‑IN and flushes the TX FIFOs. Without the stub, the responses came back shifted by one position.

- **Bootrom dump from the Apple TV itself** (`ipwndfu --dump-rom`, with `USB_READ_LIMIT = 0x1000` in `usbexec.py` because Linux doesn't accept control requests larger than 4096 bytes): `SecureROM-s5l8947xsi-1458.2-RELEASE.dump`, 65536 bytes, SHA256 `59b9e378…2b5405`, **identical** to the one from securerom.fun.

- **Decryption with the chip's GID key** (`ipwndfu --decrypt-gid`): the 8.4.x builds (12H914…12H1006) of AppleTV3,2 come **unencrypted**, with no KBAG. The iBSS of **12B466 (tvOS 8.1.3)** IS encrypted: production KBAG `2f25a729…b0016225` → the Apple TV returned IV+key `4c7933dc37a6ed5e253bceb8324ffac3` / `9aebfc6e666490560b3215abf2d7c526e52df1fd53c6d33d6ceac256755b95ac`. The decrypted iBSS starts with the ARM vector table (`0e0000ea 18f09fe5…`). Script: `emu/fw_keys.py`.

- **Modified iBSS booted unsigned** (`emu/boot_ibss.py` v2): the Apple TV shows up as `05ac:1227 Product: Apple Mobile Device (BAUT MOD)`, serial without `SRTG` (`… IBFL:1B`). Key points: the bootrom's jump routine needs the `0x6C74` stub, and you have to **skip the USB shutdown** (`0x4E9C`/`0x71AC`), because it does `free()` on the heap broken by checkm8 → panic. Reproduced and validated earlier in `emu/exploit_then_ibss.py`.

- **Unsigned iBEC booted by the patched iBSS**: patch in the iBSS at `0x34005E6E` (`bl verify_IMG3` → `movs r0,#0; nop`) and sent over DFU with a 16-byte suffix and CRC (`emu/send_ibec.py`). The Apple TV shows up as `05ac:1281 Product: Apple Mobile Device (BAUT IBEC MOD)`, `IBFL:1A`. Validated earlier in `emu/ibss_ibec.py` (the iBEC is loaded at `0x8FE00000`).

- ✅ **VERBOSE BOOT (`-v`) ON THE TV.** The iBEC doesn't turn on HDMI (the "screen initialized" flag at `0x9FF44EB0` stays at 0). Solution: send the **normal iBoot disguised as an iBEC** (`emu/send_iboot.py`: type `ibot`→`ibec` in the header and in `TYPE`, `it ne`→nop at `0x9FF1CB94`, string `0x9FF3C87B` → `-v`). iBoot turns on HDMI (720p@60Hz) and boots tvOS from the NAND. On screen: `boot-args = -v`, `root: disk0s1s1`, `Darwin Bootstrapper Version 2.1.8`, WiFi and USB drivers, etc.
- Full chain: `auto-pwn.sh` (pwned DFU) → `boot_ibss.py` (patched iBSS) → `send_iboot.py ~/fw/iBoot.j33i.RELEASE.img3`.

## Tethered jailbreak — stage A (kernel)
- `emu/kc_tool.py`: kernelcache unpack/pack (IMG3 + complzss). Kernel 12H1006: 12,984,320 bytes, **with a symbol table** (4,344).
- `emu/kpatch.py`: `_PE_i_can_has_debugger` (`0x803372D8`) → `if (r0) *r0 = 0; return 1;`. Generates `emu/kernelcache.patched` (7,713,136 bytes). Verified: it decompresses identically to the patched one and Apple's adler32 matches.
- Boot-args to use: `-v cs_enforcement_disable=1 amfi_get_out_of_my_way=1`. **Not confirmed** that AMFI honours them: the direct reference to those strings wasn't found. It gets tested in stage B.

## Tethered jailbreak — stage B1 (restore disk)
- `048-72014-118.dmg` from IPSW 12H1006 = IMG3 of type `rdsk`, **unencrypted**, DATA = 16,621,568-byte HFS+ (4058 blocks of 4 KB, **0 free**). Extracted to `emu/ramdisk.hfs`. Listing: `emu/ramdisk_listing.txt` (`emu/hfsls.py`, our own HFS+ reader).
- The files are **HFS-compressed** (decmpfs: empty data fork, content in the resource fork).
- Boot: `launchd` → `/System/Library/LaunchDaemons/com.apple.restored_external.plist` → `/usr/local/bin/restored_external`.
- Tools present: `cat expr launchctl ln mkdir mv rm sed mount mount_hfs fsck_hfs newfs_hfs nvram asr fdisk reboot halt`. **There's no shell (`sh`), no `ifconfig`, no `ipconfig`, no SSH.** `libSystem` and the base frameworks (CoreFoundation, SystemConfiguration, IOKit, CFNetwork) are there.
- Implications: we have to bring `sh`, `ifconfig` and `dropbear` for iOS ARMv7 (linked against `libSystem`), grow the image and change the `restored_external` plist so that it launches our script.

## Tethered jailbreak — stage B3 (disk in RAM with SSH)
- `emu/hfsgrow.py` grows the HFS+ to 40 MB (`emu/ramdisk_big.hfs`). `emu/mk_kit.py` builds `emu/rdkit.tar` (Saurik's tools + `overlay/`: `boot_ssh.sh`, `restored_external` plist, `sshd_config`, passwd).
- On the original disk `/sbin/reboot` and `/sbin/halt` come in mode 0444 (not executable): `build_ramdisk.sh` sets them to 755.
- `emu/build_ramdisk.sh` (run on Linux): mounts `ramdisk_big.hfs` read/write, extracts `rdkit.tar`, generates the server keys (RSA and ECDSA), copies `~/.ssh/id_ed25519.pub` into `authorized_keys`, verifies and wraps it as an IMG3 `rdsk` with `emu/wrap_rdsk.py` (template: `ramdisk_orig.dmg`). Everything together in `emu/rdpack.tar`.

## Tethered jailbreak — stage B2 (ARMv7 tools)
- Source: Saurik's repository (`http://apt.saurik.com/dists/ios/main/binary-iphoneos-arm/`, index in `emu/debs/Packages.txt`). **It has no dropbear**: we use **OpenSSH 6.7p1** (`sshd`, `ssh-keygen`).
- Downloaded into `emu/debs/`: bash 4.0.44, readline 6.0, ncurses 5.7, network-cmds 307 (`ifconfig`; the package requires firmware ≥ 9.0, to be tried on 8.4), openssh 6.7p1, openssl 0.9.8zg (`libcrypto`), coreutils-bin 8.12, inetutils 1.6 (`ping`), ldid (the iOS version, useless on the PC).
- Extracted with `emu/debx.py` into `emu/extra/` (19.7 MB, 577 entries; permissions and symlinks in `extra/_manifest.json`).
- All the binaries are **ARM (subtype ALL, they run on ARMv7)** and already carry an **ldid ad hoc signature** (`LC_CODE_SIGNATURE`). Dependencies: `libSystem`, `libgcc_s`, `libz` (the disk has them), `libreadline`/`libncurses`/`libcrypto` (they come in the packages). `ping` requires `libresolv.9.dylib`, which the disk doesn't have.

## Result on the real Apple TV (2026-11-09, before the stub)
- Padding **0x620** + jump to `0x34000000` + ipwndfu's real payload (676 bytes): **the bootrom executes the payload**. After the reset: "device firmware changed", the serial moves to index 6 and the configuration descriptor ends up changed. The change **persists after `usbreset`**.
- In the emulator, the same payload leaves `gUSBSerialNumber = "... PWND:[checkm8]"` and index 6, with all descriptors aligned → **ipwndfu's constants for the 8947 are correct**.
- Open problem on the real hardware: **every IN request gets the response of the previous request** (text 6 → langids of text 0; config → 9 bytes) and after that EP0 stops responding (timeout). Hypothesis: cache/DMA coherency (`0x8D94` before programming `DIEPDMA` at `0x3394`), or leftovers in the EP0‑IN FIFO/DMA from the phase C stall. The emulator doesn't model the cache or the FIFO, so it doesn't show up there.

## What we know from the experiments (`ckm8` kernel)
- Overwrite of ≤0x5A0 bytes → comes back in clean DFU. From 0x5A4 bytes onward → it hangs. There's a **pointer at offset 0x5A0–0x5A3** of the overwrite that the bootrom uses on reset.
- Overwriting that pointer with any value (zeros, pattern, `0xDEADBEE0`, `0x34000001`) hangs. **You have to preserve its original value.**
- From 0x600 bytes onward → it goes to recovery: there's another field between 0x5C0 and 0x600.

## Next RE tasks
1. **Heap allocator:** from the use of `0x800` at `0xA6E0`, find `malloc`/`free`. Describe the block header (size, prev/next pointers, possible checksum). Hypothesis: the 0x5A0 pointer is **heap metadata** of a free or neighbouring block (a free-list link). If so, its value is a predictable SRAM address.
2. **Heap base and allocation order** at DFU boot: DFU buffer, USB requests, descriptors. With that we can compute what sits at +0x5A0 from the freed buffer.
3. **USB reset path:** from `usb_core_do_io` and the event handlers, find where the pending requests are walked and their callback is called. That gives the real offset of the callback in the request structure.
4. With 1 to 3: build an overwrite that **rewrites the original value at 0x5A0** and puts the fake structure where it belongs. Try first with `BX LR` against an invalid address.

## SSH access (post-untether, 2026-11-10 late night)
- **Windows PC**: `ssh atv` (alias in `C:\Users\fasce\.ssh\config`, keypair `atv`/`atv.pub` ed25519 installed)
- **casa (Linux)**: `ssh atv` (alias in `~/.ssh/config`)
- **USB**: `iproxy 2222 22` on casa + `ssh -p 2222 root@localhost`
- SSH takes **~3-5 minutes** after powering the ATV on (the untether chain).
- IP: `192.168.0.109` (worth reserving in the router's DHCP).
- Still to install on the ATV: `cat`, `grep`, `head`, `ifconfig` (armv7 binaries in `emu/extra/`).

## Open next steps
1. **Kodi Helix 14.2** on the ATV (repo from the regulad/Blackb0x-- fork, maintained 2026) — HW-accelerated playback + shared folder with the Linux box.
2. **"Stremio-ATV"**: adapt PopcornTimeSE with Cinemeta catalogs + Torrentio streams (auth-less JSON APIs), sequential torrent engine already proven on the A5. Pending issue: iOS 8 distrusts modern CAs → inject Debian CAs (documented in regulad's fork).
3. Optional: dyld cache patch (daibutsu/haxx — compiled at `casa:/tmp/haxx`, patched cache at `casa:/tmp/dsc_patched`) for full AMFI-off if tweaks are ever needed.

## Public repo
- Everything published at: `github.com/fascettob-collab/atv3-untethered-linux` (local: `Apple-TV/github-repo/`). This file is the English translation of `docs/NOTAS-es.md` (the Spanish source of truth).
