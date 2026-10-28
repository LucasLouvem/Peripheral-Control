#!/bin/sh
set -eu

if [ "$(id -u)" -eq 0 ]; then
    echo 'Execute ./scripts/install.sh como usuário comum, sem sudo.' >&2
    exit 1
fi

PROJECT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
if ! command -v python3 >/dev/null 2>&1; then
    if [ -f /etc/arch-release ]; then
        echo 'Python é necessário. O pacman solicitará confirmação para instalá-lo.'
        sudo pacman -S --needed python
    else
        printf 'O produto não foi feito para seu sistema.\nGostaria de continuar? (s/N) '
        read -r answer || exit 1
        case "$answer" in s|S) ;; *) exit 1 ;; esac
        echo 'Instale Python 3.11 ou superior e execute novamente.' >&2
        exit 1
    fi
fi
exec python3 "$PROJECT_DIR/install.py" "$@"
