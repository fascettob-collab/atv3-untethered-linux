# SecureROM S5L8947 (Apple TV 3, iBoot-1458.2): notas de RE

## Archivo
- `SecureROM_s5l8947x_iBoot-1458.2.bin`: 65536 bytes, SHA256 `59B9E378…2B5405`.
- Fuente: https://securerom.fun/ ("SecureROM for s5l8947xsi, iBoot-1458.2").
- Cabecera en 0x200: `SecureROM for s5l8947xsi, Copyright 2011, Apple Inc. … RELEASE`.

## Cómo abrirlo
- **Ghidra:** Import → Raw Binary → Language `ARM:LE:32:v7` → Base address `0x0`. El código es Thumb‑2; en Ghidra marcar las funciones con `TMode=1` (o empezar el desensamblado con "Disassemble Thumb").
- RAM (SRAM): `0x34000000` en adelante. Agregar un bloque de memoria sin inicializar `0x34000000–0x34040000` para que resuelva referencias.
- Herramienta rápida sin Ghidra: script con capstone (`romtool.py`: `dis <addr> <n>`, `callers <addr>`, `lit <valor>`).

## Puntos de anclaje (de ipwndfu, verificados en el ROM)
| Dirección | Qué es |
|---|---|
| `0x7BC8` | Handler de pedidos DFU de clase (el que ipwndfu engancha). Verificado: compara `bRequest` con 1/4/6 y `wLength` con `0x800` |
| `0x79EC` | `usb_core_do_io` (único llamador directo: `0x7CFE`) |
| `0x72A8` | `usb_create_string_descriptor` |
| `0x3402D8D4` / `0x3402D8D8` / `0x3402D8E0` | Estado DFU (status, bytes de GETSTATUS, estructura con el puntero al buffer en `+0x10`) |
| `0x3402D87C` | `gUSBDescriptors` |
| `0x3402DDF8` | `gUSBSerialNumber` |
| `0x3402D92C` | Puntero al handler (PAYLOAD_PTR) |
| `0xA6E0` | Único literal `0x800` del ROM: probablemente el tamaño del buffer DFU (`malloc(0x800)`) |

## Heap (verificado en el código)
- `malloc` = `0x3994`, `free` = `0x3A18`, `memalign` = `0x3B3C`, `memset` = `0x9D70`. Global del heap: `0x3402CF40` (bins en `+0x28`).
- Cabecera de bloque de **0x20 bytes** antes de los datos: palabra 0 = tamaño del bloque anterior (`(w0<<3)&~0x1F`) más flags (bit0 = libre, bit1 = anterior libre); palabra 1 = tamaño en unidades de 32 bytes. Los bloques libres tienen `next`/`prev` en `+0x20`/`+0x24`.
- `free()` valida la cabecera contra el vecino. Si no coincide: **panic** (`0x3B34`) = cuelgue.
- Buffer DFU: `memalign(0x800, 0x20)` en `0x7B30`, guardado en `0x3402D8E0+0x10`. Se libera en `0x7DF0` (salida de DFU).
- **Pedido USB** (`usb_core_do_io` `0x79EC`): `malloc(0x1C)` → bloque de 0x40 (cabecera 0x20 + datos 0x20). Campos: `+0x0` endpoint, `+0x4` buffer, `+0xC` largo, **`+0x14` callback**, `+0x18` siguiente. Coincide con `struct.pack('<20xI4x', cb)` de ipwndfu.

- **Completar pedido** `0x79D0`: `if (req->cb) req->cb(req); free(req);`. Lo llaman `0x30DA`, `0x3352`, `0x36A6` y `0x392C` (driver del controlador USB, incluida la ruta del reset). En `usb_core_do_io`, si el endpoint es `0x80` y no hay buffer, usa el buffer por defecto `0x3402D760`.
- Interpretación de los recortes: el bloque con cabecera en 0x5A0 y datos en 0x5C0 **es un pedido pendiente que se completa en el reset**. Pisar solo la cabecera hace que `free` haga panic (cuelgue). Pisar los campos del pedido con ceros hace que el reset no lo reconozca (recuperación).
- Para que se llame al callback hay que dejar **una cabecera válida** (`w0=8`, prev 0x40; `w1=2`, tamaño 0x40) y **los campos del pedido verosímiles** (`ep=0x80`, `buf=0x3402D760`, `len=0x40`, `cb` en `+0x14`).

- **Evento de reset USB** (`0x7914`, evento 2): primero `abort(0x80)` (`0x35A4`), que recorre la cola de EP0‑IN (cabeza en `0x3402CD40 + idx*0x28 + 0x38`, siguiente en `req+0x18`), pone `req[8]=1` y llama a `0x79D0` (callback y free) **sin validar campos**. Después llama al handler de reset de cada interfaz (`iface+0x38`).
- **Handler de reset de DFU** `0x7DC4`: si el estado DFU (`0x3402D8D4`) es **8** (`dfuMANIFEST-WAIT-RESET`), marca "terminado" y señaliza. La bootrom sale de DFU y arranca → **esto es la "recuperación" que vemos**.
- Prueba del pedido falso completo en 0x5C0 (cabecera válida y campos `ep=0x80`, `buf`, `len`, `cb`): **recuperación con las dos direcciones** (6 intentos). Como `abort` no valida campos, si ese bloque estuviera en la cola de EP0‑IN el callback inválido colgaría. **El bloque de 0x5C0 no es el pedido encolado en EP0‑IN.**
- Siguiente pregunta de RE: ¿por qué el estado DFU llega a 8? Buscar dónde se escribe 8 en `0x3402D8D4`. Posiblemente sea el callback de datos de DNLOAD (`0x7D18`, registrado como `0x7D19`) ejecutado sobre un pedido EP0‑OUT que pisamos.

- **No hay ningún `strb #8`** al estado DFU en el ROM (solo 2, 5, 6 y 0xA). La salida de DFU ocurre por `0x3402D8D0 = 1` y la señal en `+0x1C`. Lugares que la disparan: `0x7C86` (pedidos **CLRSTATUS(4)/ABORT(6)**: si no estaba en curso, pone resultado −1 y sale), `0x7D70` (callback de datos con verificación `0x67DC` fallida) y `0x7DDA` (reset con estado 8).
- **CLRSTATUS saca a la bootrom de DFU** (`dfu_exit` `0x7DF0` libera el buffer `0x3402D8E0+0x10`) y vuelve a entrar → **ese es el origen del use‑after‑free** de checkm8 en este chip. Encaja con "(DFU loop)".
- `GETSTATUS` medido: antes y después del paso marcado = `[0, 50, 0, 0, 2, 0]` (sin error, estado 2 idle). El paso marcado no rompe el estado DFU. La recuperación se decide después: en el overwrite y el reset final.

## Emulador (`emu/emu.py`, Unicorn)
- **Usar Unicorn 2.0.1.post1** (con `setuptools<70` para `pkg_resources`). La 2.1.4 ejecuta mal los bloques IT de Thumb‑2 (saltea instrucciones en `free()` y termina en un panic falso).
- Arranca desde `0x0` con la SRAM en `0x34000000` (0x40000) y MMIO mapeado a demanda. Simulación mínima de periféricos: clock gates en `0x3F101xxx` (estado = pedido), PLL lock en `0x3F102xxx` (bit 30), y lecturas repetidas que alternan entre 0 y 0xFFFFFFFF.
- **Heap verificado:** se inicializa en `0x6010` con región `0x3402DEFC`–`0x34039000`. Primeras reservas: `malloc(0x1C)` → `0x3402DF40`, `malloc(0x100)` → `0x3402DF80`, `malloc(0x98)` → `0x3402E0A0`.
- **Interrupciones:** controlador en `0x3F200000`. Evento en `0x3F202004` (`0x1xxxx` = IRQ externa con número en los bits 0‑8; `0x70001`/`0x70004` = timers). Tabla de handlers en `0x3402C2E0` (idx*12: `+0xC` función, `+0x10` arg). Vector IRQ `0x6D98` → `0x6F90` → `0xBBC`. El emulador inyecta un tick de timer en cada `WFI`.
- **Timer de 64 bits:** baja `0x3F200020`, alta `0x3F200028`. Se lee alta‑baja‑alta y se repite si cambió la alta.
- **Bucle de arranque** `0x810`: `0x4F8C` devuelve el tipo de dispositivo; **3 = DFU por USB** (`0x868` → `0x7AE8`). El emulador fuerza r4=3 en `0x8FC`.
- **En DFU (emulado):** `memalign(0x800, 0x20)` → **buffer DFU = `0x3402E300`** (hasta `0x3402EB00`). Las siguientes reservas son `malloc(0x19)` → `0x3402EB20` y `0x3402EB60`. IRQ USB = **0xB** (handler `0x2EBC`), IRQ 0x1C = periférico en `0x32000000`.
- **USB (Synopsys DWC OTG en `0x36100000`, modo DMA):** GINTSTS `+0x14` (bit 12 reset, bit 13 enumdone, bit 19 OUT EP, bit 18 IN EP). DAINT `+0x818`. DOEPINT0 `+0xB08` (bit 3 = SETUP). DOEPDMA0 `+0xB14` = **`0x3402CD00`** (los 8 bytes del SETUP se escriben ahí). DIEPINT0 `+0x908`.
- **Dónde se frenaba antes:** en `WFI` (`0x804`). El sistema de tareas espera interrupciones (timer y USB). Para llegar a DFU falta emular el controlador de interrupciones y un timer, y después el controlador USB (Synopsys OTG en `0x3610xxxx`) con el tráfico del exploit.

## Resultado del emulador con la secuencia del exploit (`emu/host.py exploit leak=626`)
- Fase A: stall + 626 leaks → la cola de EP0‑IN tiene 628 pedidos (`0x3402EBA0`…`0x34038860`). Llenan el heap.
- Fase B: DNLOAD 0x800 cortado a 64 bytes + CLRSTATUS → `dfu_exit` libera el buffer viejo `0x3402E300`. Al volver a entrar, el `memalign(0x800)` nuevo cae en **`0x3402E0C0`** (otro lugar, porque el heap está lleno).
- Fase C: stall + leak → **la cabeza de la cola EP0‑IN es `0x3402E960` = buffer viejo + 0x660** (el valor de ipwndfu).
- El overwrite se escribe por el puntero colgado, **a partir de buffer viejo + 0x40** (los 64 bytes del DNLOAD cortado ya avanzaron el puntero).
- **Relleno correcto con `partial_len=64`: 0x620** (callback en 0x634). Con eso, el emulador **salta a `0x34000000` desde `usb_complete` (`lr=0x79E1`)**.
- En las pruebas reales nunca se probó 0x620 con la estructura de ipwndfu: los barridos fueron de a 0x40 (0x5C0, 0x600, 0x640…).

## ✅ RAMDISK CON SSH FUNCIONANDO (2026-11-10)
`ssh -p 2222 root@localhost` (via `iproxy 2222 22` en casa) contra el disco en RAM. **Fase 1 del plan completa.**

# 🏆🏆 SSH UNTETHERED LOGRADO (2026-11-10, medianoche) — SIN PC, SOLO CORRIENTE
**REPETIBILIDAD VERIFICADA: 2 boots en frío consecutivos → SSH root solo, a los ~5 min.** ✓✓
La Apple TV 3 arranca tvOS normal desde la corriente y a los ~3-5 minutos el SSH root está disponible en `192.168.0.109` (y por USB con `iproxy`). **Objetivo final del proyecto: COMPLETO.**

## Receta final instalada en el disco (todo verificadо byte-exacto)
| Pieza | Estado |
|---|---|
| `/usr/libexec/rtbuddyd` → **symlink al jsc del framework** (`/System/Library/Frameworks/JavaScriptCore.framework/Resources/jsc`, firma Apple válida con CMS → pasa AMFI en boot stock) | ✓ |
| `/--early-boot` = `expl.js` de tihmstar (17 KB, exploit JavaScriptCore+ROP) | ✓ |
| `/untether/untether.bin` (payload: exploit de kernel + parches, versión modificada Blackb0x) | ✓ |
| `/usr/bin/orphan_commander` + `/private/etc/rc.d/daemonload` (fuerza `launchctl load /Library/LaunchDaemons` vía syslogd) | ✓ |
| `/usr/bin/dirhelper` (Blackb0x, remonta / rw + corre /etc/rc.d) | ✓ |
| `/Library/LaunchDaemons/com.bauti.sshd.plist` → `/usr/sbin/sshd -D` | ✓ |
| sshd + bash + libcrypto.0.9.8 + readline/ncurses + config + claves host | ✓ |
| `authorized_keys` en **partición de datos** (`/private/var/root/.ssh/` — la del sistema queda tapada por el mount) | ✓ |
| fstab: `ro` (¡NO poner rw! el kernel stock sin parche de rootfs se cuelga) | ✓ |
| NVRAM: `auto-boot=true`, `boot-args=amfi_get_out_of_my_way=1` | ✓ |

## Lecciones del camino (para NOTAS de RE)
1. **La cadena del untether tarda ~3-5 min** desde el boot hasta que sshd escucha — los checks a los 30-60s daban falso negativo (esto nos costó horas).
2. Los LaunchDaemons propios van en `/Library/LaunchDaemons` (launchd no escanea /System/Library/LaunchDaemons para plists ajenos en ATV3 tvOS 8.4).
3. `authorized_keys` a la partición de DATOS (la del sistema queda oculta bajo el mount de /private/var).
4. El jsc "binario extraído del cache" (Blackb0x rtbuddyd.bin) tiene firma adhoc sin CMS → AMFI lo rechaza en boot stock (errno 85 "Bad executable"); el jsc del framework del PROPIO sistema tiene firma Apple completa ✓.
5. fstab rw en el arranque = boot falla con kernel sin parche de rootfs (cae a recovery).
6. El timer del ramdisk (boot_ssh.sh) deja `auto-boot=false` — el reinicio suave del ramdisk siempre cae en recovery; power cycle frío respeta auto-boot (setear con `nvram auto-boot=true` + sync).
7. `iflag=fullblock` no existe en coreutils 8.12 (dd del ramdisk) — para archivos grandes, sesión SSH dedicada con `dd of=... bs=1048576` leyendo del stdin hasta EOF.
8. Kernel stock 12H1006 se llama `MarijuanARM_S5L8947X`; el kernelcache.patched nuestro mantiene `RELEASE_ARM`.

## Estado de las piezas del ecosistema
- **Arranque normal (sin PC)**: tvOS de fábrica + untether → SSH root a los ~5 min ✓
- **Arranque tethered** (`kernel-boot.sh`): tvOS con kernel parcheado + SSH (más rápido)
- **Ramdisk de rescate** (`ramdisk-boot.sh`): acceso al disco por USB
- **Backup completo** en `~/backup/apple-tv` (pre-jailbreak)
- Pendiente opcional: parche del dyld cache (daibutsu/haxx, compilado en `/tmp/haxx` de casa, `/tmp/dsc_patched` listo) si algún día se quiere AMFI totalmente off para tweaks — NO fue necesario.

### Detalle del SSH tethered (intermedio)
`ssh -i ~/.ssh/id_ed25519 root@192.168.0.109` contra **tvOS 8.4.4 real** (Darwin ashe-anashe).
Cadena completa: checkm8 → iBSS → iBEC → kernelcache.patched → bootx → tvOS → **untether completo corre** (launchd spawnea rtbuddyd=jsc → /--early-boot → expl.js → untether.bin → kernel exploit → dirhelper/daemonload → launchctl load /Library/LaunchDaemons → sshd) → SSH root.

Detalle que faltaba (bug final): `authorized_keys` iba en `/mnt1/private/var/root/.ssh` (partición SISTEMA) pero al bootear, la partición de DATOS se monta ENCIMA de `/private/var` y lo tapa. Fix: `/mnt2/root/.ssh/authorized_keys` (+ copia en `/mnt1/private/etc/ssh/`).

## Estado final del día
- **Tethered SSH: FUNCIONA** (boot con kernel-boot.sh = exploit + kernel parcheado → SSH por red o USB)
- **Untethered (sin PC): falta UNA pieza** — en boot con kernel STOCK, launchd rechaza rtbuddyd: `posix_spawn(): 85: Bad executable (or shared library)` (AMFI rechaza la firma del jsc extraído del cache). Con kernel parcheado corre perfecto.
- Ideas para el untethered puro:
  1. Conseguir un jsc con firma Apple válida (el diseño de tihmstar asume "Apple's own binary with valid code signature") — p.ej. jsc standalone del iPhoneOS SDK, o verificar por qué la firma embebida (1584 bytes) no valida.
  2. Parchear AMFI de forma persistente... (imposible sin bootchain).
  3. Pedir el rtbuddyd del fork regulad/Blackb0x-- (mantenido 2026, quizá firma nueva).
  4. Inspeccionar desde el SSH tethered cómo validó AMFI (log de la firma).

## Accesos SSH (post-untether, 2026-11-10 noche)
- **PC Windows**: `ssh atv` (alias en `C:\Users\fasce\.ssh\config`, clave `atv`/`atv.pub` ed25519 instalada)
- **casa (Linux)**: `ssh atv` (alias en `~/.ssh/config`)
- **USB**: `iproxy 2222 22` en casa + `ssh -p 2222 root@localhost`
- El SSH tarda **~3-5 min** tras encender la ATV (la cadena del untether).
- IP: `192.168.0.109` (reservar en el router DHCP para que no cambie).
- En la ATV faltan instalar: `cat`, `grep`, `head`, `ifconfig` (binarios armv7 en `emu/extra/`).

## Próximos pasos / proyectos abiertos
1. **Kodi Helix 14.2** en la ATV (repo del fork regulad/Blackb0x--, mantenido 2026) — playback con aceleración HW + carpeta compartida con casa.
2. **"Stremio-ATV"**: adaptar PopcornTimeSE con catálogo de Cinemeta + streams de Torrentio (APIs JSON sin auth), motor torrent secuencial ya probado en la A5. Problema pendiente: iOS 8 no confía en CAs modernas → inyectar CAs de Debian (documentado en el fork de regulad). Prompt del proyecto guardado en el historial de la sesión.
3. Opcional: parche del dyld cache (daibutsu/haxx — compilado en `casa:/tmp/haxx`, cache parcheado en `casa:/tmp/dsc_patched`) si se quiere AMFI totalmente off para tweaks.

## Repo público
- Todo el proyecto subido a: `github.com/fascettob-collab/atv3-untethered-linux` (repo local: `Apple-TV/github-repo/`). README + docs/journey.md (traducción EN de estas notas), boot/ramdisk/kernel/tools/scripts. `docs/NOTAS-es.md` = este archivo.


Instalamos al disco (`/mnt1`, todo verificado byte-exacto con el streamer):
- `/usr/libexec/rtbuddyd` = jsc (Apple-signed) → en cada boot, launchd lo spawnea (label `com.apple.rtbuddyd` confirmado en el jetsam plist del sistema)
- `/--early-boot` y `/untether/expl.js` (exploit JavaScriptCore), `/untether/untether.bin` (la versión MODIFICADA por NSSpiral, no orig_untether.bin)
- `/usr/bin/orphan_commander`, `/private/etc/rc.d/daemonload` (corre `orphan_commander -w syslogd 'launchctl load /Library/LaunchDaemons'`), `/usr/bin/dirhelper` (remonta / rw + corre /etc/rc.d)
- `/Library/LaunchDaemons/com.bauti.sshd.plist` (los daemons van ahí, NO en /System/Library/LaunchDaemons — fue uno de nuestros bugs)
- sshd + bash + libcrypto + config + claves ya instalados de antes (verificados funcionando en el ramdisk)

**No funciona aún**: tvOS bootea normal pero el 22 queda cerrado. Sin crash reports de jsc. El syslog del boot no se llegó a capturar (idevicesyslog hay que dejarlo corriendo ANTES del power cycle; `/tmp/sysloop2.sh` en casa).

Próximos pasos de debug:
1. **Con el ramdisk, ejecutar a mano** `/mnt1/usr/libexec/rtbuddyd --early-boot` y ver qué pasa (¿corre el exploit? ¿muere jsc? ¿kernel panic?). Es el test directo de toda la cadena.
2. Capturar syslog durante el power cycle (sysloop2 andando antes de desenchufar).
3. Verificar cómo lanza launchd al rtbuddyd (¿con qué argv? ¿--early-boot?) — el jsc interpreta argv como archivos de script, el nombre "/--early-boot" viene de cwd=/.
4. Hipótesis si corre y falla: `untether.bin` con offsets para otro kernel (12H876/885 vs nuestro 12H1006). La versión modificada de Blackb0x decía soportar 8.4.x. Alternativa: usar el untether del fork `regulad/Blackb0x--` (mantenido 2026).

Herramientas creadas hoy: `hfsls.py` (decmpfs `uncat`), `macho_deps.py`, `unstream.py`, `apply_links.py`, streamer inverso (`receiver.sh`/`send_untether.sh` — parse del path: `path=${line#F $sz }`), canary markers. Todo en `casa:/tmp` y en `emu/`.


## SSH permanente en tvOS — diagnóstico intermedio (2026-11-10 tarde)
Instalación al disco real (`/mnt1`) verificada y sobreviviente (el "journal rollback" era falso: miré un /mnt1 sin montar). En el ramdisk todo funciona: `/mnt1/bin/touch` exec ✓, `/mnt1/usr/sbin/sshd -t` con config+claves instaladas → rc=0 ✓, `sshd -D` escucha ✓, `launchctl load` acepta el plist ✓.

En el arranque REAL de tvOS (tethered con kernel parcheado y untethered con kernel stock): puerto 22 cerrado, sin crash reports, y el syslog capturado con `idevicesyslog` muestra que launchd carga todos los daemons pero **ni menciona com.bauti.sshd**.

Canarios instalados en `/mnt1/System/Library/LaunchDaemons/com.bauti.canary.plist`:
- `CANARY2` = lo crea launchd (firmado) vía StandardOutPath → prueba que launchd corre nuestros jobs
- `CANARY` = lo crea /bin/touch (nuestro, sin firma) → prueba además que AMFI deja correr código sin firma

Lectura de resultados (tras idevicecrashreport):
- Solo CANARY2 → AMFI mata lo sin firma (kernel no parcheado o boot-args insuficiente) → seguir tethered o instalar untether etasonATV
- CANARY y CANARY2 → launchd+AMFI OK; el problema es del sshd (probable dyld/libs contra el cache)
- Ninguno → launchd no lee /mnt1 (partición o scan)

Otros datos:
- Blackb0x (github.com/NSSpiral/Blackb0x) = **jailbreak untethered público para AppleTV3,2 tvOS 8.4.x** (etasonATV jsc untether de tihmstar): confirma que el untethered es factible y cómo lo hace (explota JavaScriptCore al boot desde el disco). Es app de macOS.
- El USB del iBEC de fábrica en recovery a veces queda "desalineado" (comandos sin efecto): se arregla desenchufando TODO y re-enchufando (re-enumeración).
- `irecovery -n` desde ese estado puede no hacer nada; power cycle completo con auto-boot=true arranca tvOS normal.

### Backup completo (fase 1, 2026-11-10)
- `~/backup/apple-tv/{system,data}`: 15.704 archivos, 2.4 GB, 4.423 directorios (system = /mnt1, data = /mnt2).
- Stream crudo en `~/backup/apple-tv-backup.stream` + `emu/unstream.py` (reensamblador) + `emu/apply_links.py` (destinos de symlinks desde `~/backup/symlinks.tsv`).
- **Falta `readlink` en el ramdisk**: los symlinks se recuperan con `ls -l` (pase aparte, ver `/tmp/symlinks.sh` en casa).
- La partición de datos incluye `keybags` (claves de archivo) — un restore futuro tiene todo.
- Al terminar: `nvram auto-boot=true` antes de desenchufar (boot_ssh.sh lo deja en false).

Causas raíz encontradas (3 bugs encadenados):
1. **plist de `restored_external` reemplazado**: el kit apuntaba su plist a `boot_ssh.sh`, así que `restored_external` nunca corría → nadie levantaba el USB restore-mode → sin usbmux → sin SSH (y sin USB en el bus: el xHCI no veía NI un evento de conexión durante el ramdisk). Arrancarlo a mano desde bash no sirve: necesita el spawn de launchd. **Fix**: plist original de Apple restaurado (extraído del ramdisk de fábrica con decmpfs, ver `hfsls.py uncat`) + plist propio `com.bauti.bootssh.plist` para `boot_ssh.sh`.
2. **plist de bootssh estilo Apple no andaba**: con `POSIXSpawnType`/`StandardOutPath` launchd no lo spawneaba. La forma que funciona: `Label`/`ProgramArguments`/`RunAtLoad`/`KeepAlive=false`/`UserName=root` (la misma que tenía el plist reemplazado original).
3. **launchctl está en `/bin/launchctl`** (no `/usr/bin`).

Detalles del ramdisk en funcionamiento:
- El USB aparece como `05ac:12a7 TV Device` a los ~8 s del bootx (usbmux arriba).
- `restored_external` corre como PID 6 (visto con `/bin/launchctl list`).
- `bautlog` en NVRAM funciona si la variable se pre-crea con `setenv`+`saveenv` desde el iBEC de fábrica (el `nvram` del ramdisk no crea variables nuevas). Trace: `ini;sh;lo0=0;l=[lo0];en0:no;...;sshd=0;restored:no`(falso: launchctl en otra ruta).
- **`/` queda montado read-only** (`mount -u -w /` falla) → `/tmp/quedarse` no se puede tocar; el timer de reinicio se desarma con `launchctl remove com.bauti.bootssh`.
- **Abrir `/dev/rdisk*`/`/dev/disk*` da EPERM** incluso siendo root sin sandbox (mount via kernel sí funciona). Backup de la NAND cruda por dd: pendiente de resolver (¿entitlements?).
- **Backup a nivel de archivo**: `mount_hfs /dev/disk0s1s1 /mnt1` (sistema) y `disk0s1s2 /mnt2` (datos) OK. Streamer bash (`streamer.sh`: dd por archivo con cabecera F/D/L) + `emu/unstream.py` en la PC. Backup en `~/backup/apple-tv-backup.stream`.
- Faltan en el ramdisk: `libiconv.2.dylib` (rompe `/bin/cat`), `head/tail/wc` no están en /bin. `dd` no acepta sufijo `m` minúscula (usar `M`).
- `ideviceinfo` se cuelga contra el ramdisk (no hay lockdown) — sirve para distinguir ramdisk de tvOS normal.

## ✅ PWNED DFU LOGRADO (2026-11-09)
`Device is now in pwned DFU Mode.` y `iSerial 6 CPID:8947 … SRTG:[iBoot-1458.2] PWND:[checkm8]`, al 2.º intento.
Receta completa:
- PC Linux con el kernel `7.0.14-ckm8` (xHCI parcheado): `ckm8_enable=1`, `ckm8_partial_len=64`.
- ipwndfu: `large_leak=626`; paso async reemplazado por un DNLOAD 0x800 marcado (`wValue=0xC8C8`) que el kernel corta a 64 bytes sin STATUS.
- Overwrite: `'\0'*0x620 + struct.pack('<20xI4x', 0x340002A4)`.
- Payload: el de ipwndfu para el 8947 más un stub ARM (`emu/mk_flush_payload.py`) que llama al shellcode y después deshabilita EP0‑IN y vacía los TX FIFO. Sin el stub, las respuestas quedaban corridas una posición.

- **Volcado de la bootrom desde la propia Apple TV** (`ipwndfu --dump-rom`, con `USB_READ_LIMIT = 0x1000` en `usbexec.py` porque Linux no acepta pedidos de control de más de 4096 bytes): `SecureROM-s5l8947xsi-1458.2-RELEASE.dump`, 65536 bytes, SHA256 `59b9e378…2b5405`, **idéntico** al de securerom.fun.

- **Descifrado con la clave GID del chip** (`ipwndfu --decrypt-gid`): los builds 8.4.x (12H914…12H1006) de AppleTV3,2 vienen **sin encriptar**, sin KBAG. El iBSS de **12B466 (tvOS 8.1.3)** sí está encriptado: KBAG de producción `2f25a729…b0016225` → la Apple TV devolvió IV+clave `4c7933dc37a6ed5e253bceb8324ffac3` / `9aebfc6e666490560b3215abf2d7c526e52df1fd53c6d33d6ceac256755b95ac`. El iBSS desencriptado empieza con la tabla de vectores ARM (`0e0000ea 18f09fe5…`). Script: `emu/fw_keys.py`.

- **iBSS modificado arrancado sin firma** (`emu/boot_ibss.py` v2): la Apple TV aparece como `05ac:1227 Product: Apple Mobile Device (BAUT MOD)`, serial sin `SRTG` (`… IBFL:1B`). Claves: la rutina de salto de la bootrom necesita el stub de `0x6C74`, y hay que **saltear el apagado del USB** (`0x4E9C`/`0x71AC`), porque hace `free()` sobre el heap roto por checkm8 → panic. Reproducido y validado antes en `emu/exploit_then_ibss.py`.

- **iBEC sin firma arrancado por el iBSS parcheado**: parche en el iBSS `0x34005E6E` (`bl validar_IMG3` → `movs r0,#0; nop`) y envío por DFU con sufijo de 16 bytes y CRC (`emu/send_ibec.py`). La Apple TV aparece como `05ac:1281 Product: Apple Mobile Device (BAUT IBEC MOD)`, `IBFL:1A`. Validado antes en `emu/ibss_ibec.py` (el iBEC se carga en `0x8FE00000`).

- ✅ **ARRANQUE VERBOSE (`-v`) EN LA TELE.** El iBEC no prende el HDMI (bandera "pantalla inicializada" en `0x9FF44EB0` queda en 0). Solución: mandar el **iBoot normal disfrazado de iBEC** (`emu/send_iboot.py`: tipo `ibot`→`ibec` en la cabecera y en `TYPE`, `it ne`→nop en `0x9FF1CB94`, cadena `0x9FF3C87B` → `-v`). El iBoot prende el HDMI (720p@60Hz) y arranca tvOS desde la NAND. En pantalla: `boot-args = -v`, `root: disk0s1s1`, `Darwin Bootstrapper Version 2.1.8`, drivers de WiFi y USB, etc.
- Cadena completa: `auto-pwn.sh` (pwned DFU) → `boot_ibss.py` (iBSS parcheado) → `send_iboot.py ~/fw/iBoot.j33i.RELEASE.img3`.

## Jailbreak tethered — etapa A (kernel)
- `emu/kc_tool.py`: unpack/pack del kernelcache (IMG3 + complzss). Kernel 12H1006: 12.984.320 bytes, **con tabla de símbolos** (4.344).
- `emu/kpatch.py`: `_PE_i_can_has_debugger` (`0x803372D8`) → `if (r0) *r0 = 0; return 1;`. Genera `emu/kernelcache.patched` (7.713.136 bytes). Verificado: descomprime idéntico al parcheado y el adler32 de Apple coincide.
- Boot-args a usar: `-v cs_enforcement_disable=1 amfi_get_out_of_my_way=1`. **Sin confirmar** que AMFI los respete: no se encontró la referencia directa a esas cadenas. Se prueba en la etapa B.

## Jailbreak tethered — etapa B1 (disco de restauración)
- `048-72014-118.dmg` del IPSW 12H1006 = IMG3 tipo `rdsk`, **sin encriptar**, DATA = HFS+ de 16.621.568 bytes (4058 bloques de 4 KB, **0 libres**). Extraído en `emu/ramdisk.hfs`. Listado: `emu/ramdisk_listing.txt` (`emu/hfsls.py`, lector HFS+ propio).
- Los archivos están con **compresión HFS** (decmpfs: fork de datos vacío, contenido en el fork de recursos).
- Arranque: `launchd` → `/System/Library/LaunchDaemons/com.apple.restored_external.plist` → `/usr/local/bin/restored_external`.
- Herramientas presentes: `cat expr launchctl ln mkdir mv rm sed mount mount_hfs fsck_hfs newfs_hfs nvram asr fdisk reboot halt`. **No hay shell (`sh`), ni `ifconfig`, ni `ipconfig`, ni SSH.** Sí están `libSystem` y frameworks base (CoreFoundation, SystemConfiguration, IOKit, CFNetwork).
- Implicancias: hay que traer `sh`, `ifconfig` y `dropbear` para iOS ARMv7 (enlazados contra `libSystem`), agrandar la imagen y cambiar el plist de `restored_external` para que arranque nuestro script.

## Jailbreak tethered — etapa B3 (disco en RAM con SSH)
- `emu/hfsgrow.py` agranda el HFS+ a 40 MB (`emu/ramdisk_big.hfs`). `emu/mk_kit.py` arma `emu/rdkit.tar` (herramientas de Saurik + `overlay/`: `boot_ssh.sh`, plist de `restored_external`, `sshd_config`, passwd).
- En el disco original `/sbin/reboot` y `/sbin/halt` vienen en modo 0444 (no ejecutables): `build_ramdisk.sh` los pone en 755.
- `emu/build_ramdisk.sh` (se corre en Linux): monta `ramdisk_big.hfs` en lectura/escritura, extrae `rdkit.tar`, genera claves del servidor (RSA y ECDSA), copia `~/.ssh/id_ed25519.pub` a `authorized_keys`, verifica y envuelve como IMG3 `rdsk` con `emu/wrap_rdsk.py` (molde: `ramdisk_orig.dmg`). Todo junto en `emu/rdpack.tar`.

## Jailbreak tethered — etapa B2 (herramientas ARMv7)
- Fuente: repositorio de Saurik (`http://apt.saurik.com/dists/ios/main/binary-iphoneos-arm/`, índice en `emu/debs/Packages.txt`). **No tiene dropbear**: se usa **OpenSSH 6.7p1** (`sshd`, `ssh-keygen`).
- Bajados en `emu/debs/`: bash 4.0.44, readline 6.0, ncurses 5.7, network-cmds 307 (`ifconfig`; el paquete pide firmware ≥ 9.0, a probar en 8.4), openssh 6.7p1, openssl 0.9.8zg (`libcrypto`), coreutils-bin 8.12, inetutils 1.6 (`ping`), ldid (versión para iOS, no sirve en la PC).
- Extraídos con `emu/debx.py` a `emu/extra/` (19,7 MB, 577 entradas; permisos y symlinks en `extra/_manifest.json`).
- Todos los binarios son **ARM (subtipo ALL, corren en ARMv7)** y ya traen **firma ad hoc de ldid** (`LC_CODE_SIGNATURE`). Dependencias: `libSystem`, `libgcc_s`, `libz` (las tiene el disco), `libreadline`/`libncurses`/`libcrypto` (vienen en los paquetes). `ping` pide `libresolv.9.dylib`, que el disco no trae.

## Resultado en la Apple TV real (2026-11-09, antes del stub)
- Relleno **0x620** + salto `0x34000000` + payload real de ipwndfu (676 bytes): **la bootrom ejecuta el payload**. Después del reset: "device firmware changed", el serial pasa al índice 6 y el descriptor de configuración queda cambiado. El cambio **persiste tras `usbreset`**.
- En el emulador, el mismo payload deja `gUSBSerialNumber = "... PWND:[checkm8]"` y el índice 6, con todos los descriptores alineados → **las constantes de ipwndfu para el 8947 son correctas**.
- Problema abierto en el hardware real: **cada pedido IN recibe la respuesta del pedido anterior** (texto 6 → langids del texto 0; config → 9 bytes) y después EP0 deja de responder (timeout). Hipótesis: coherencia de caché/DMA (`0x8D94` antes de programar `DIEPDMA` en `0x3394`), o restos en el FIFO/DMA de EP0‑IN del stall de la fase C. El emulador no modela la caché ni el FIFO, así que ahí no aparece.

## Lo que sabemos por los experimentos (kernel `ckm8`)
- Overwrite de ≤0x5A0 bytes → vuelve en DFU limpio. De 0x5A4 bytes en adelante → se cuelga. Hay un **puntero en offset 0x5A0–0x5A3** del overwrite que la bootrom usa en el reset.
- Pisar ese puntero con cualquier valor (ceros, patrón, `0xDEADBEE0`, `0x34000001`) cuelga. **Hay que conservar su valor original.**
- De 0x600 bytes en adelante → sale a recuperación: hay otro campo entre 0x5C0 y 0x600.

## Próximas tareas de RE
1. **Allocator del heap:** desde el uso de `0x800` en `0xA6E0`, encontrar `malloc`/`free`. Describir la cabecera de bloque (tamaño, punteros prev/next, posible checksum). Hipótesis: el puntero de 0x5A0 es **metadata del heap** de un bloque libre o vecino (un enlace de la free list). Si es así, su valor es una dirección de SRAM predecible.
2. **Base del heap y orden de asignaciones** en el arranque DFU: buffer DFU, pedidos USB, descriptores. Con eso se calcula qué hay a +0x5A0 del buffer liberado.
3. **Ruta del reset USB:** desde `usb_core_do_io` y los handlers de eventos, encontrar dónde se recorren los pedidos pendientes y se llama a su callback. Eso da el offset real del callback en la estructura del pedido.
4. Con 1 a 3: armar un overwrite que **reescriba el valor original en 0x5A0** y ponga la estructura falsa donde corresponde. Probar primero con `BX LR` contra una dirección inválida.
