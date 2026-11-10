#!/usr/bin/env bash
# checkm8 en Apple TV 3 (A1469, CPID 8947) desde Linux con ipwndfu (axi0mX).
# Uso: bash linux-checkm8.sh setup   -> instala dependencias y baja ipwndfu
#      bash linux-checkm8.sh check   -> verifica que la Apple TV esté en DFU
#      bash linux-checkm8.sh pwn     -> corre el exploit (Apple TV recién entrada en DFU)
set -e
DIR="$HOME/ipwndfu"

case "$1" in
  setup)
    sudo apt-get update
    sudo apt-get install -y git libusb-1.0-0 usbutils curl build-essential \
      libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev
    # Python 2.7 ya no viene en Ubuntu/Debian recientes: se compila con pyenv.
    if ! command -v python2 >/dev/null; then
      if [ ! -d "$HOME/.pyenv" ]; then curl -fsSL https://pyenv.run | bash; fi
      export PYENV_ROOT="$HOME/.pyenv"; export PATH="$PYENV_ROOT/bin:$PATH"
      eval "$(pyenv init -)"
      pyenv install -s 2.7.18
    fi
    [ -d "$DIR" ] || git clone https://github.com/axi0mX/ipwndfu "$DIR"
    echo "Setup listo."
    ;;
  check)
    lsusb | grep -i 05ac || echo "No se ve ningun dispositivo Apple"
    lsusb -v -d 05ac:1227 2>/dev/null | grep -i iSerial || echo "No esta en DFU (05ac:1227)"
    ;;
  pwn)
    PY=python2
    if ! command -v python2 >/dev/null; then PY="$HOME/.pyenv/versions/2.7.18/bin/python"; fi
    cd "$DIR"
    sudo "$PY" ./ipwndfu -p
    sudo lsusb -v -d 05ac:1227 2>/dev/null | grep -i iSerial
    ;;
  *)
    echo "Uso: $0 setup|check|pwn"; exit 1;;
esac
