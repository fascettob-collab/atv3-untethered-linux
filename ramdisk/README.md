# ramdisk/ — the SSH rescue ramdisk

Builds the disk-on-RAM used to install everything and rescue the system.

- `hfsgrow.py` — grows the restore ramdisk HFS+ image to ~26 MB (40 MB max: iBoot won't load bigger).
- `mk_kit.py` — builds `rdkit.tar`: coreutils (armv7, adhoc-signed) + overlay (plists, `boot_ssh.sh`, sshd config).
- `wrap_rdsk.py` — wraps the HFS+ image as an IMG3 `rdsk` using Apple's original as template.
- `build_ramdisk.sh` — runs on the Linux box with the `hfsplus` kernel module: mounts RW, installs kit + host keys + `authorized_keys`, verifies, wraps.
- `overlay/` — the files overlaid onto the ramdisk image (LaunchDaemons, `boot_ssh.sh`).

## Hard-won details

- `restored_external` must be launched by **launchd via its original plist** —
  it's what brings up USB restore-mode (and thus `iproxy`). Launching it by
  hand from bash fails silently.
- A launchd plist with `POSIXSpawnType`/`StandardOutPath` to a file never
  spawned; the simple `Label`/`ProgramArguments`/`RunAtLoad`/`KeepAlive`/
  `UserName` form works.
- `launchctl` lives at `/bin/launchctl`.
- `/` stays read-only: `/tmp/quedarse` can't be created — disarm the auto-reboot
  timer with `launchctl remove com.bauti.bootssh`.
- Opening `/dev/rdisk*` gives EPERM even as root — file-level access works via
  mount (`mount_hfs`), so the backup is file-level (streamer + `unstream.py`).
