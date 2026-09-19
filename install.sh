#!/usr/bin/env bash
# OpenAurum installer: everything goes to ~/.local (your user only);
# sudo is used once, for the udev rule that lets you talk to the keyboard.
#
#   ./install.sh               install or update
#   ./install.sh --check       only check the dependencies
#   ./install.sh --no-udev     install without touching /etc (no sudo)
#   ./install.sh --uninstall   remove everything this script installed
set -euo pipefail

APP_ID=io.github.its_danilo.OpenAurum
SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOCAL=$HOME/.local
SHARE=$LOCAL/share/openaurum
BIN=$LOCAL/bin
DESKTOP=$LOCAL/share/applications/$APP_ID.desktop
ICON=$LOCAL/share/icons/hicolor/scalable/apps/$APP_ID.svg
UNIT_DIR=${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user
UNIT=$UNIT_DIR/openaurum-heatmap.service
RULE=/etc/udev/rules.d/70-openaurum.rules
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/openaurum
CONFIG=${XDG_CONFIG_HOME:-$HOME/.config}/openaurum
PROGRAMS=(openaurum openaurum-cli openaurum-heatmap)

bold=$'\e[1m' green=$'\e[32m' yellow=$'\e[33m' red=$'\e[31m' reset=$'\e[0m'
[[ -t 1 ]] || bold='' green='' yellow='' red='' reset=''
ok()   { echo "${green}✓${reset} $*"; }
warn() { echo "${yellow}!${reset} $*"; }
fail() { echo "${red}✗${reset} $*"; }
step() { echo; echo "${bold}$*${reset}"; }

packages() {
  # the command that installs the dependencies on this distro
  local id=""
  [[ -r /etc/os-release ]] && id=$(. /etc/os-release; echo "${ID:-} ${ID_LIKE:-}")
  case " $id " in
    *" arch "*)                echo "sudo pacman -S --needed python-gobject gtk4 libadwaita python-evdev" ;;
    *" debian "*|*" ubuntu "*) echo "sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 python3-evdev" ;;
    *" fedora "*)              echo "sudo dnf install python3-gobject gtk4 libadwaita python3-evdev" ;;
    *" suse "*|*" opensuse"*)  echo "sudo zypper install python3-gobject-Gdk typelib-1_0-Gtk-4_0 typelib-1_0-Adw-1 python3-evdev" ;;
    *)                         echo "(instale: Python 3, PyGObject, GTK 4, libadwaita 1.4+ e, opcional, python-evdev)" ;;
  esac
}

do_check() {
  step "Dependências"
  local missing=0
  if command -v python3 >/dev/null; then
    ok "python3 $(python3 -c 'import platform; print(platform.python_version())')"
  else
    fail "python3 não encontrado"; missing=1
  fi
  if python3 - 2>/dev/null <<'PY'
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk
assert (Adw.MAJOR_VERSION, Adw.MINOR_VERSION) >= (1, 4)
PY
  then
    ok "GTK 4 + libadwaita $(python3 -c 'import gi; gi.require_version("Adw","1"); from gi.repository import Adw; print(f"{Adw.MAJOR_VERSION}.{Adw.MINOR_VERSION}")' 2>/dev/null) (app)"
  else
    fail "PyGObject com GTK 4 e libadwaita 1.4+ não encontrado (o app precisa; o openaurum-cli não)"
    missing=1
  fi
  if python3 -c "import evdev" 2>/dev/null; then
    ok "python-evdev (mapa de calor, opcional)"
  else
    warn "python-evdev ausente: só o mapa de calor precisa dele"
  fi
  local dev found=0
  for dev in /sys/bus/usb/devices/*; do
    [[ $(cat "$dev/idVendor" 2>/dev/null) == 36ae && $(cat "$dev/idProduct" 2>/dev/null) == fe9c ]] && found=1
  done
  if (( found )); then
    ok "Aurum V60 conectado (36ae:fe9c)"
  else
    warn "Aurum V60 (36ae:fe9c) não encontrado agora; conecte-o para usar"
  fi
  if (( missing )); then
    echo
    echo "Para instalar o que falta:"
    echo "  $(packages)"
  fi
  return $missing
}

migrate_calos() {
  # the author's calOS kept the same state under other names: carry it over once
  local old=$HOME/.local/state/calos a b
  [[ -d $old ]] || return 0
  mkdir -p "$STATE"
  for pair in keyboard.json:scenes.json keyboard-levels.json:levels.json \
              keyboard-writes.json:writes.json keyheat.json:heat.json; do
    a=$old/${pair%%:*} b=$STATE/${pair##*:}
    if [[ -f $a && ! -f $b ]]; then
      cp "$a" "$b" && ok "estado do calOS copiado: ${pair%%:*} → ${b/#$HOME/\~}"
    fi
  done
}

install_udev() {
  if [[ -f $RULE ]] && cmp -s "$SRC/data/70-openaurum.rules" "$RULE"; then
    ok "regra udev já instalada ($RULE)"
    return
  fi
  echo "A regra udev libera o teclado para o seu usuário (sem rodar nada como root)."
  echo "Vai pedir a senha do sudo para copiar $RULE:"
  sudo install -Dm644 "$SRC/data/70-openaurum.rules" "$RULE"
  sudo udevadm control --reload-rules
  sudo udevadm trigger --action=change --subsystem-match=hidraw
  ok "regra udev instalada ($RULE)"
}

do_install() {
  local udev=1
  [[ ${1:-} == --no-udev ]] && udev=0
  do_check || { echo; fail "Instale as dependências acima e rode ./install.sh de novo."; exit 1; }

  step "Instalando em ${LOCAL/#$HOME/\~}"
  rm -rf "$SHARE/openaurum"
  mkdir -p "$SHARE/openaurum" "$BIN"
  cp "$SRC"/openaurum/*.py "$SHARE/openaurum/"
  ok "biblioteca → ${SHARE/#$HOME/\~}"
  for p in "${PROGRAMS[@]}"; do
    install -m755 "$SRC/bin/$p" "$BIN/$p"
  done
  ok "programas → ${BIN/#$HOME/\~}: ${PROGRAMS[*]}"
  # absolute Exec: desktop launchers often don't have ~/.local/bin in their PATH
  mkdir -p "$(dirname "$DESKTOP")"
  sed "s|^Exec=openaurum|Exec=$BIN/openaurum|" "$SRC/data/$APP_ID.desktop" >"$DESKTOP"
  install -Dm644 "$SRC/data/$APP_ID.svg" "$ICON"
  ok "atalho no menu de aplicativos (OpenAurum)"
  install -Dm644 "$SRC/data/openaurum-heatmap.service" "$UNIT"
  if command -v systemctl >/dev/null; then
    systemctl --user daemon-reload 2>/dev/null || true
    # already counting (an update): restart it on the new code
    systemctl --user try-restart openaurum-heatmap.service 2>/dev/null || true
  fi
  ok "serviço do mapa de calor instalado (desligado; o app liga quando você quiser)"
  migrate_calos

  if (( udev )); then
    step "Permissão de acesso ao teclado"
    install_udev
  fi

  step "Pronto"
  case ":$PATH:" in
    *":$BIN:"*) ;;
    *) warn "${BIN/#$HOME/\~} não está no seu PATH: adicione  export PATH=\"\$HOME/.local/bin:\$PATH\"  ao seu shell" ;;
  esac
  if python3 -c "import evdev" 2>/dev/null && ! id -nG | tr ' ' '\n' | grep -qx input; then
    warn "para o mapa de calor: sudo usermod -aG input \$USER  (e entre de novo na sessão)"
  fi
  echo "Abra o ${bold}OpenAurum${reset} pelo menu de aplicativos, ou rode:  openaurum   /   openaurum-cli status"
  echo "Se o app disser \"sem acesso\", desconecte e reconecte o teclado uma vez."
}

do_uninstall() {
  step "Removendo o OpenAurum"
  if command -v systemctl >/dev/null; then
    systemctl --user disable --now openaurum-heatmap.service 2>/dev/null || true
  fi
  rm -f "$UNIT" "$DESKTOP" "$ICON"
  for p in "${PROGRAMS[@]}"; do rm -f "$BIN/$p"; done
  rm -rf "$SHARE"
  command -v systemctl >/dev/null && systemctl --user daemon-reload 2>/dev/null || true
  ok "programas, biblioteca, atalho, ícone e serviço removidos"
  if [[ -f $RULE ]]; then
    echo "Removendo a regra udev (pede a senha do sudo):"
    sudo rm -f "$RULE" && sudo udevadm control --reload-rules && ok "regra udev removida"
  fi
  if [[ -d $STATE || -d $CONFIG ]]; then
    read -rp "Apagar também as suas cenas/pinturas e configurações (${STATE/#$HOME/\~}, ${CONFIG/#$HOME/\~})? [s/N] " ans
    if [[ $ans == [sSyY]* ]]; then
      rm -rf "$STATE" "$CONFIG"
      ok "estado e configuração apagados"
    else
      ok "estado e configuração mantidos"
    fi
  fi
  echo "As cores gravadas no teclado continuam nele (ficam na memória do próprio teclado)."
}

case ${1:-} in
  ""|--no-udev) do_install "${1:-}" ;;
  --check)      do_check ;;
  --uninstall)  do_uninstall ;;
  -h|--help)    sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//' ;;
  *)            echo "uso: ./install.sh [--check | --no-udev | --uninstall]" >&2; exit 2 ;;
esac
