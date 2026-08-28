#!/usr/bin/env bash
# Idempotent setup for a self-hosted GitHub Actions runner on this
# workstation, following docs/RUNNER_SETUP.md phase by phase. Safe to
# re-run — every phase checks whether its own piece already exists
# before touching anything, so running this on an already-configured
# host is a fast no-op, and running it on a fresh host does the full
# setup. See RUNNER_SETUP.md for the reasoning behind each phase; this
# script is the "just do it" version of that document, not a
# replacement for reading it once.
#
# Usage:
#   ./setup-runner.sh [--url URL --token TOKEN] [--altera-src DIR]
#
#   --url/--token   Phase 2 (GitHub registration). Both required
#                    together, from Settings -> Actions -> Runners ->
#                    New runner on GitHub — the token expires in ~1h,
#                    so fetch it right before running this. Omit both
#                    to skip registration (e.g. re-running this script
#                    on an already-registered host to fix up the other
#                    phases only).
#   --altera-src    Phase 4's bind-mount source (default:
#                    /home/$SUDO_USER/altera_lite, i.e. the invoking
#                    admin's own Quartus install). Pass explicitly if
#                    that's wrong for this host, or skip Phase 4
#                    entirely with --no-altera.
#   --no-altera     Skip Phase 4 (no Quartus bind mount needed/wanted
#                    on this host).
#
# Password handling: asks for sudo authentication exactly once, up
# front (`sudo -v`), and lets sudo's own timestamp cache cover every
# subsequent `sudo` call in this script — nothing ever writes a
# password to a file, temp or otherwise. Re-enter it via prompts if a
# a step takes long enough for the cache to expire; that's sudo's own
# prompt, not this script's.
set -euo pipefail

RUNNER_USER=runner
RUNNER_HOME=/opt/actions-runner
RUNNER_URL=""
RUNNER_TOKEN=""
ALTERA_SRC="/home/${SUDO_USER:-$USER}/altera_lite"
SKIP_ALTERA=0

while [ $# -gt 0 ]; do
  case "$1" in
    --url) RUNNER_URL="$2"; shift 2 ;;
    --token) RUNNER_TOKEN="$2"; shift 2 ;;
    --altera-src) ALTERA_SRC="$2"; shift 2 ;;
    --no-altera) SKIP_ALTERA=1; shift ;;
    -h|--help) awk '/^#!/{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if { [ -n "$RUNNER_URL" ] && [ -z "$RUNNER_TOKEN" ]; } || { [ -z "$RUNNER_URL" ] && [ -n "$RUNNER_TOKEN" ]; }; then
  echo "--url and --token must be given together (or neither, to skip Phase 2)" >&2
  exit 1
fi

log() { echo "==> $*"; }
skip() { echo "    already done: $*"; }

log "Caching sudo credentials (asks once, up front) ..."
sudo -v

# ---------------------------------------------------------------
# Phase 1 — dedicated service user
# ---------------------------------------------------------------
if id "$RUNNER_USER" >/dev/null 2>&1; then
  skip "user '$RUNNER_USER' exists"
else
  log "Phase 1: creating system user '$RUNNER_USER' ..."
  sudo useradd -r -m -d "$RUNNER_HOME" -s /bin/bash "$RUNNER_USER"
  sudo passwd -l "$RUNNER_USER"
fi

if id -nG "$RUNNER_USER" | tr ' ' '\n' | grep -qx plugdev; then
  skip "'$RUNNER_USER' already in group 'plugdev'"
else
  log "Phase 1: adding '$RUNNER_USER' to group 'plugdev' (USB-Blaster access) ..."
  sudo usermod -aG plugdev "$RUNNER_USER"
fi

# ---------------------------------------------------------------
# Phase 2 — register with GitHub (needs a fresh token; optional)
# ---------------------------------------------------------------
if [ -f "$RUNNER_HOME/.runner" ]; then
  skip "runner already registered ($RUNNER_HOME/.runner exists)"
elif [ -z "$RUNNER_URL" ]; then
  log "Phase 2: SKIPPED (no --url/--token given)."
  echo "    Register manually later, or re-run with --url/--token from"
  echo "    Settings -> Actions -> Runners -> New runner (token expires ~1h)."
else
  log "Phase 2: downloading and registering the runner ..."
  RUNNER_TARBALL_URL=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
    | grep -oP '"browser_download_url":\s*"\K[^"]*linux-x64-[^"]*\.tar\.gz(?=")' | head -1)
  if [ -z "$RUNNER_TARBALL_URL" ]; then
    echo "Could not resolve the latest actions/runner linux-x64 tarball URL" >&2
    exit 1
  fi
  sudo -iu "$RUNNER_USER" bash -lc "
    set -euo pipefail
    cd '$RUNNER_HOME'
    curl -fsSL -o actions-runner.tar.gz '$RUNNER_TARBALL_URL'
    tar xzf actions-runner.tar.gz
    rm actions-runner.tar.gz
    ./config.sh --url '$RUNNER_URL' --token '$RUNNER_TOKEN' \
        --labels self-hosted,quartus,fpga --name workstation-fpga --unattended
  "
  echo "    Reminder: confirm the runner landed in the 'FPGA' runner group"
  echo "    (Org Settings -> Actions -> Runner groups) — config.sh's"
  echo "    interactive group picker only fires without --unattended, so an"
  echo "    unattended registration like this one lands wherever the org's"
  echo "    default runner group is, not necessarily 'FPGA'. See"
  echo "    RUNNER_SETUP.md's note on why the group name matters."
fi

# ---------------------------------------------------------------
# Phase 3 — systemd service
# ---------------------------------------------------------------
UNIT_PATH=/etc/systemd/system/gh-actions-runner.service
UNIT_CONTENT="[Unit]
Description=GitHub Actions self-hosted runner (FPGA workstation)
After=network.target

[Service]
Type=simple
User=$RUNNER_USER
WorkingDirectory=$RUNNER_HOME
ExecStart=$RUNNER_HOME/run.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"
if [ -f "$UNIT_PATH" ] && [ "$(sudo cat "$UNIT_PATH")" = "$UNIT_CONTENT" ]; then
  skip "systemd unit $UNIT_PATH matches"
else
  log "Phase 3: writing $UNIT_PATH ..."
  printf '%s' "$UNIT_CONTENT" | sudo tee "$UNIT_PATH" >/dev/null
  sudo systemctl daemon-reload
fi

if systemctl is-enabled --quiet gh-actions-runner 2>/dev/null && systemctl is-active --quiet gh-actions-runner; then
  skip "gh-actions-runner is enabled and active"
else
  log "Phase 3: enabling + starting gh-actions-runner ..."
  sudo systemctl enable --now gh-actions-runner
fi

# ---------------------------------------------------------------
# Phase 4 — bind mount for admin-owned tools (Quartus)
# ---------------------------------------------------------------
if [ "$SKIP_ALTERA" -eq 1 ]; then
  log "Phase 4: SKIPPED (--no-altera)."
elif ! [ -d "$ALTERA_SRC" ]; then
  log "Phase 4: SKIPPED — $ALTERA_SRC doesn't exist on this host (pass --altera-src to override, or --no-altera to silence this)."
else
  sudo mkdir -p /opt/altera_lite
  if grep -qF "$ALTERA_SRC /opt/altera_lite" /etc/fstab 2>/dev/null; then
    skip "/etc/fstab bind-mount entry for $ALTERA_SRC"
  else
    log "Phase 4: adding /etc/fstab bind-mount entry ..."
    echo "$ALTERA_SRC /opt/altera_lite none bind 0 0" | sudo tee -a /etc/fstab >/dev/null
  fi
  if mountpoint -q /opt/altera_lite; then
    skip "/opt/altera_lite already mounted"
  else
    log "Phase 4: mounting /opt/altera_lite ..."
    sudo mount --bind "$ALTERA_SRC" /opt/altera_lite
  fi
fi

# ---------------------------------------------------------------
# Phase 5 — shared toolchain cache
# ---------------------------------------------------------------
CACHE_DIR=/opt/riscv-foundation
if [ -d "$CACHE_DIR" ] && [ "$(stat -c '%U:%G' "$CACHE_DIR")" = "$RUNNER_USER:$RUNNER_USER" ]; then
  skip "$CACHE_DIR exists, owned by $RUNNER_USER:$RUNNER_USER"
else
  log "Phase 5: creating $CACHE_DIR ..."
  sudo mkdir -p "$CACHE_DIR"
  sudo chown "$RUNNER_USER:$RUNNER_USER" "$CACHE_DIR"
  sudo chmod 2775 "$CACHE_DIR"
fi

if [ -n "${SUDO_USER:-}" ]; then
  if id -nG "$SUDO_USER" | tr ' ' '\n' | grep -qx "$RUNNER_USER"; then
    skip "'$SUDO_USER' already in group '$RUNNER_USER'"
  else
    log "Phase 5: adding '$SUDO_USER' to group '$RUNNER_USER' (so it can write $CACHE_DIR without sudo) ..."
    sudo usermod -aG "$RUNNER_USER" "$SUDO_USER"
    echo "    Note: takes effect in a NEW shell session (or 'sg $RUNNER_USER -c \"<cmd>\"' in this one)."
  fi
fi

# ---------------------------------------------------------------
# Phase 7 (partial) — narrow sudoers grant for the CI JTAG-recovery step
# ---------------------------------------------------------------
SUDOERS_PATH=/etc/sudoers.d/runner-jtagd
SUDOERS_LINE="$RUNNER_USER ALL=(root) NOPASSWD: /usr/bin/killall jtagd"
if [ -f "$SUDOERS_PATH" ] && [ "$(sudo cat "$SUDOERS_PATH")" = "$SUDOERS_LINE" ]; then
  skip "$SUDOERS_PATH matches"
else
  log "Phase 7: granting '$RUNNER_USER' passwordless sudo for exactly 'killall jtagd' ..."
  echo "$SUDOERS_LINE" | sudo tee "$SUDOERS_PATH" >/dev/null
  sudo chmod 440 "$SUDOERS_PATH"
  sudo visudo -c -f "$SUDOERS_PATH" >/dev/null
fi

log "Done. Remaining manual steps (can't be scripted — see RUNNER_SETUP.md):"
echo "    - Phase 2's runner-group placement (Org Settings -> Actions -> Runner groups -> 'FPGA')"
echo "      and Repository access -> Selected repositories, if this is a fresh registration."
echo "    - Phase 6: repo secret FPGA_RUN_SECRET, if this project uses workflow_dispatch."
echo "    - Phase 7's USB autosuspend fix — host/device-specific, run the diagnostic in"
echo "      RUNNER_SETUP.md's Fase 7 and fix up the parent hub found there if needed."
echo ""
sudo systemctl status gh-actions-runner --no-pager || true
