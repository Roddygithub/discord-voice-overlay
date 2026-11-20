#!/usr/bin/env bash
set -Eeuo pipefail

project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
service_name=discord-voice-overlay-auto-update.service
timer_name=discord-voice-overlay-auto-update.timer
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
service_path="$config_dir/$service_name"
timer_path="$config_dir/$timer_name"
ai_repair=0
remove=0

escape_systemd() {
    local value=$1
    value=${value//\\/\\\\}
    value=${value//\"/\\\"}
    value=${value//\$/\\\$}
    value=${value//%/%%}
    printf '"%s"' "$value"
}

service_content() {
    local use_ai_repair=${1:-0}
    printf '[Unit]\nDescription=Update Discord Voice Overlay for Vesktop and Vencord\nAfter=network-online.target\nWants=network-online.target\n\n[Service]\nType=oneshot\n'
    if (( use_ai_repair )); then
        printf 'Environment=DVO_AI_REPAIR=1\n'
    fi
    printf 'ExecStart=%s\n' "$(escape_systemd "$project/scripts/auto-update.sh")"
}

timer_content() {
    printf '[Unit]\nDescription=Check Discord Voice Overlay updates every two hours\n\n[Timer]\nOnBootSec=10m\nOnUnitActiveSec=2h\nRandomizedDelaySec=10m\nPersistent=true\nUnit=%s\n\n[Install]\nWantedBy=timers.target\n' "$service_name"
}

usage() {
    printf 'Usage: %s [--ai-repair | --remove]\n' "${0##*/}"
}

while (($#)); do
    case "$1" in
        --ai-repair) ai_repair=1 ;;
        --remove) remove=1 ;;
        --help|-h) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
    shift
done

[[ "$(id -u)" -ne 0 ]] || { printf 'Run this as your normal user.\n' >&2; exit 1; }
command -v systemctl >/dev/null 2>&1 || { printf 'systemctl is required.\n' >&2; exit 1; }

if (( remove )); then
    if [[ -e "$service_path" ]] && ! cmp -s <(service_content) "$service_path" &&
        ! cmp -s <(service_content 1) "$service_path"; then
        printf 'Leaving a modified or foreign service untouched: %s\n' "$service_path" >&2
        exit 1
    fi
    if [[ -e "$timer_path" ]] && ! cmp -s <(timer_content) "$timer_path"; then
        printf 'Leaving a modified or foreign timer untouched: %s\n' "$timer_path" >&2
        exit 1
    fi
    systemctl --user disable --now "$timer_name" >/dev/null 2>&1 || true
    rm -f -- "$service_path" "$timer_path"
    systemctl --user daemon-reload
    printf 'Automatic update timer removed.\n'
    exit 0
fi

[[ -d "$project/.git" ]] || { printf 'Automatic updates require a persistent Git checkout.\n' >&2; exit 1; }
[[ "$(git -C "$project" remote get-url origin)" == https://github.com/Roddygithub/discord-voice-overlay.git ]] || {
    printf 'Unexpected Git origin; refusing to install the updater.\n' >&2
    exit 1
}
if (( ai_repair )) && ! command -v codex >/dev/null 2>&1; then
    printf 'Codex CLI is not installed; install it and sign in before enabling AI repair.\n' >&2
    exit 1
fi

mkdir -p -- "$config_dir"
for path in "$service_path" "$timer_path"; do
    [[ ! -L "$path" ]] || { printf 'Refusing symlink unit path: %s\n' "$path" >&2; exit 1; }
done
if [[ -e "$service_path" ]] && ! cmp -s <(service_content) "$service_path" &&
    ! cmp -s <(service_content 1) "$service_path"; then
    printf 'Refusing to overwrite a modified or foreign service: %s\n' "$service_path" >&2
    exit 1
fi
if [[ -e "$timer_path" ]] && ! cmp -s <(timer_content) "$timer_path"; then
    printf 'Refusing to overwrite a modified or foreign timer: %s\n' "$timer_path" >&2
    exit 1
fi

service_content > "$service_path"
timer_content > "$timer_path"
chmod 644 "$service_path" "$timer_path"
systemctl --user daemon-reload
systemctl --user enable --now "$timer_name"
if (( ai_repair )); then
    printf 'Two-hour update timer enabled with Codex repair on build failure.\n'
else
    printf 'Two-hour update timer enabled. Codex repair remains disabled.\n'
fi
