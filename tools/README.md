# tools/ — standalone utilities

All pure Python 3 (no dependencies beyond the standard library).

| Tool | What it does |
|---|---|
| **`hfsls.py`** | Minimal HFS+ reader: lists/extracts files, **including decmpfs-compressed files** (`uncat`), resource forks (`catr`) and extended attributes. Reads Apple restore ramdisks without a Mac. Also extracts IMG3 `DATA` payloads from wrapped images. |
| `macho_deps.py` | Lists `LC_LOAD_DYLIB` dependencies of a Mach-O (32/64-bit, fat). |
| `macho_sigs.py` | Lists load commands and finds `LC_CODE_SIGNATURE`. |
| `cs_parse.py` | Parses the code-signature SuperBlob — tells adhoc from Apple-signed (CMS blob present?) in seconds. This is how we discovered the jsc signature issue. |
| `debx.py` | Extracts `.deb` packages (for the tool kit). |
| `unstream.py` / `apply_links.py` | Reassemble the disk backup stream (see `docs/journey.md`, backup section). |
| `fw_keys.py` | KBAG decryption helpers for firmware images. |
