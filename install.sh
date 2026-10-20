#!/usr/bin/env bash
#
# scuolagrab — guided server installer for Debian/Ubuntu
#
# Usage:
#   sudo bash install.sh              # guided install
#   sudo bash install.sh --dry-run    # show what it would do, change nothing
#
# What it does:
#   - installs python3, venv, pip, git
#   - creates the "scuolagrab" system user
#   - copies this project to /opt/scuolagrab (or the folder you choose)
#   - creates the virtualenv, installs the requirements and Chromium
#   - writes and starts the systemd service
#   - optionally opens the port in ufw
#
set -euo pipefail

NAME="scuolagrab"
SERVICE_USER="scuolagrab"
DEFAULT_DIR="/opt/scuolagrab"
DEFAULT_HOST="0.0.0.0"
DEFAULT_PORT="8749"
DRY=0
NO_SERVICE=0

BOLD="$(printf '\033[1m')"
GREEN="$(printf '\033[32m')"
YELLOW="$(printf '\033[33m')"
RED="$(printf '\033[31m')"
RESET="$(printf '\033[0m')"

for arg in "$@"; do
	case "$arg" in
		--dry-run) DRY=1 ;;
		--no-service) NO_SERVICE=1 ;;
		-h|--help)
			sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
			exit 0
			;;
		*)
			echo "Unknown option: $arg (try --help)" >&2
			exit 2
			;;
	esac
done

step() { printf '\n%s==>%s %s\n' "$BOLD$GREEN" "$RESET" "$*"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '%s    ! %s%s\n' "$YELLOW" "$*" "$RESET"; }
die() { printf '%s    x %s%s\n' "$RED" "$*" "$RESET" >&2; exit 1; }

run() {
	if [ "$DRY" = 1 ]; then
		printf '    + %s\n' "$*"
	else
		"$@"
	fi
}

runuser_cmd() {
	if [ "$DRY" = 1 ]; then
		printf '    + sudo -u %s %s\n' "$SERVICE_USER" "$*"
	else
		sudo -u "$SERVICE_USER" "$@"
	fi
}

ask() {
	# ask <question> <default> -> echoes the answer
	local question="$1" default="$2" answer=""
	if [ "$DRY" = 1 ] && [ ! -t 0 ]; then
		echo "$default"
		return
	fi
	read -r -p "    $question [$default]: " answer || true
	echo "${answer:-$default}"
}

ask_yes() {
	# ask_yes <question> <y|n>
	local question="$1" default="$2" answer=""
	if [ "$DRY" = 1 ] && [ ! -t 0 ]; then
		[ "$default" = "y" ]
		return
	fi
	read -r -p "    $question [$default]: " answer || true
	answer="${answer:-$default}"
	case "$answer" in y|Y|yes|s|S|si|sì) return 0 ;; *) return 1 ;; esac
}

[ "$(id -u)" = 0 ] || [ "$DRY" = 1 ] || die "Run it with sudo: sudo bash install.sh"
command -v apt-get >/dev/null 2>&1 || die "This installer supports Debian/Ubuntu (apt) only. Follow the manual steps in README.md."

SRC="$(cd "$(dirname "$0")" && pwd)"

printf '%s\n' "${BOLD}${GREEN}"
printf '  scuolagrab — guided server install\n'
printf '%s\n' "${RESET}"

step "Configuration"
DIR="$(ask "Install folder" "$DEFAULT_DIR")"
HOST="$(ask "Listen address (0.0.0.0 = all interfaces)" "$DEFAULT_HOST")"
PORT="$(ask "Port" "$DEFAULT_PORT")"

case "$PORT" in
	''|*[!0-9]*) die "The port must be a number" ;;
esac
[ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] || die "Port out of range"

[ -n "$DIR" ] || die "The install folder cannot be empty"
case "$DIR" in
	/*) ;;
	*) die "Use an absolute path for the install folder (e.g. $DEFAULT_DIR)" ;;
esac
if [ "$DIR" != "$SRC" ]; then
	case "$DIR/" in
		"$SRC/"*) die "Choose a folder outside the source tree ($SRC)" ;;
	esac
fi

info "Folder:   $DIR"
info "Address:  $HOST:$PORT"
info "Service:  $NAME (user $SERVICE_USER)"
info "Source:   $SRC"

step "System dependencies"
run apt-get update -y
run apt-get install -y python3 python3-venv python3-pip git ca-certificates

step "Service user"
if id -u "$SERVICE_USER" >/dev/null 2>&1; then
	info "User $SERVICE_USER already exists"
else
	run useradd --system --home-dir "$DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
	[ "$DRY" = 1 ] || info "Created user $SERVICE_USER"
fi

step "Project files"
if [ "$SRC" = "$DIR" ]; then
	info "Project already in $DIR"
else
	run mkdir -p "$DIR"
	if [ "$DRY" = 0 ]; then
		cp -a "$SRC/." "$DIR/"
		info "Copied $SRC -> $DIR"
	else
		info "Would copy $SRC -> $DIR"
	fi
fi
run chown -R "$SERVICE_USER:$SERVICE_USER" "$DIR"

step "Python environment"
if [ -d "$DIR/.venv" ]; then
	info "Reusing $DIR/.venv"
else
	runuser_cmd python3 -m venv "$DIR/.venv"
fi
runuser_cmd "$DIR/.venv/bin/pip" install --upgrade pip
runuser_cmd "$DIR/.venv/bin/pip" install -r "$DIR/requirements.txt"

step "Chromium for the Sanoma login (~130 MB)"
runuser_cmd "$DIR/.venv/bin/python" -m playwright install chromium
run "$DIR/.venv/bin/python" -m playwright install-deps chromium

if [ "$NO_SERVICE" = 1 ]; then
	step "Done (systemd skipped)"
	info "Start it with: sudo -u $SERVICE_USER $DIR/.venv/bin/python $DIR/server/app.py --host $HOST --port $PORT"
	exit 0
fi

step "systemd service"
UNIT="/etc/systemd/system/$NAME.service"
if [ "$DRY" = 1 ]; then
	printf '    + write %s\n' "$UNIT"
	printf '    + systemctl daemon-reload\n'
	printf '    + systemctl enable %s\n' "$NAME"
	printf '    + systemctl restart %s\n' "$NAME"
else
	cat > "$UNIT" <<EOF
[Unit]
Description=$NAME server
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$DIR
Environment=SBG_HOST=$HOST
Environment=SBG_PORT=$PORT
ExecStart=$DIR/.venv/bin/python server/app.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
	systemctl daemon-reload
	systemctl enable "$NAME" >/dev/null 2>&1
	systemctl restart "$NAME"
fi

step "Firewall"
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
	if ask_yes "Open port $PORT/tcp in ufw?" "y"; then
		run ufw allow "$PORT/tcp"
	fi
else
	info "ufw not active: remember to open port $PORT/tcp if you use a firewall"
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
step "Done"
printf '    %sURL:%s  http://%s:%s\n' "$BOLD" "$RESET" "${IP:-SERVER-IP}" "$PORT"
printf '    %sLog:%s  sudo journalctl -u %s -f\n' "$BOLD" "$RESET" "$NAME"
printf '    %sStop:%s sudo systemctl stop %s\n' "$BOLD" "$RESET" "$NAME"
printf '    %sData:%s %s/server/data/server.db and %s/files/\n' "$BOLD" "$RESET" "$DIR" "$DIR"

if [ "$DRY" = 0 ]; then
	printf '\n'
	systemctl --no-pager --lines=0 status "$NAME" || true
fi
