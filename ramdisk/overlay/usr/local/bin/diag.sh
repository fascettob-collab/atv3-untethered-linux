#!/bin/bash
# diagnostico en el ramdisk: donde esta launchctl, que procesos hay
echo "command -v: $(command -v launchctl)"
for p in /usr/bin/launchctl /bin/launchctl /usr/sbin/launchctl /sbin/launchctl /usr/libexec/launchctl /usr/libexec/launchctl-static; do
  [ -e "$p" ] && echo "EXISTS $p"
done
echo "=== /usr/bin:"
/bin/ls /usr/bin 2>/dev/null
echo "=== /bin:"
/bin/ls /bin 2>/dev/null
echo "=== /sbin:"
/bin/ls /sbin 2>/dev/null
echo "=== /usr/sbin:"
/bin/ls /usr/sbin 2>/dev/null
