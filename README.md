# Discord Voice Overlay

[![CI](https://github.com/Roddygithub/discord-voice-overlay/workflows/CI/badge.svg)](https://github.com/Roddygithub/discord-voice-overlay/actions/workflows/ci.yml)
[![Release](https://github.com/Roddygithub/discord-voice-overlay/workflows/Release/badge.svg)](https://github.com/Roddygithub/discord-voice-overlay/actions/workflows/release.yml)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-blue.svg)](https://opensource.org/licenses/GPL-3.0)
[![Version](https://img.shields.io/github/v/tag/Roddygithub/discord-voice-overlay?label=version&sort=semver)](https://github.com/Roddygithub/discord-voice-overlay/releases)
[![Downloads](https://img.shields.io/github/downloads/Roddygithub/discord-voice-overlay/total)](https://github.com/Roddygithub/discord-voice-overlay/releases)

A native Wayland voice activity overlay for Discord Desktop and Vesktop on Linux.

See who is speaking without touching the game process: participant names and
avatars, speaking and mute/deaf indicators, configurable position and monitor,
and native click-through. It is a shared custom Vencord plugin plus a Rust
overlay, installed and managed by the v1.3.0 universal installer.

<!-- TODO: hero screenshot / GIF of the overlay in a voice channel -->

## Contents

- [Highlights](#highlights)
- [How it compares](#how-it-compares)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Auto-start (systemd user service)](#auto-start-systemd-user-service)
- [Manual build and development](#manual-build-and-development)
- [Architecture](#architecture)
- [Security and privacy](#security-and-privacy)
- [Socket protocol](#socket-protocol)
- [Supported compositors](#supported-compositors)
- [Distribution](#distribution)
- [Development](#development)
- [License](#license)

## Highlights

- 🔒 **Privacy-first** — no Discord token access, no self-bots, no separate Gateway connections
- 🖥️ **Wayland-native** — `layer-shell` with an empty input region, so mouse clicks pass through to whatever is underneath (wlroots compositors: Hyprland, sway, niri, etc.)
- 📺 **Monitor setting** — primary, cursor, or indexed output is exposed, but reliable hotplug behavior is deferred pending issue #21
- ⚡ **Low latency** — event-driven voice updates over a local Unix socket
- 🎮 **Game compatible** — click-through overlay works over fullscreen XWayland games
- 🔄 **Auto-reconnect** — fast bounded backoff (≤ 2 s) if Discord Desktop, Vesktop, or the overlay restarts; the latest settings and voice snapshot are replayed automatically so no voice activity is needed to repopulate the overlay
- 🚀 **Session autostart** — ships a `systemd --user` service (`vesktop-voice-overlay.service`)
- 🧰 **Universal manager** — v1.3.0 provides `install`, `status`, `doctor`, `update`, `repair`, and `uninstall` for supported native clients

## How it compares

There are other Discord overlays for Linux. This one exists because it draws
through Wayland layer-shell rather than a normal window, and because it never
touches your account token.

| | **Discord Voice Overlay** | [Overlayed](https://github.com/overlayeddev/overlayed) | [Discover](https://github.com/trigg/Discover) | [DiscordOverlayLinux](https://github.com/trigg/DiscordOverlayLinux) |
|---|---|---|---|---|
| Stack | Rust + GTK4 | TypeScript (Tauri) | Python + GTK3 | Python + Qt |
| Drawn as | layer-shell surface | desktop window | desktop window | X11 window |
| Compositors | Wayland (wlroots) | Win / macOS / Linux | X11 + wlroots | X11 |

Pick **Overlayed** if you want a polished cross-platform app with a UI of its
own. Pick **Discover** if you want maximum configurability or run X11. Pick
this one if you want the overlay to sit in the compositor's layer stack,
pass clicks to the game underneath, and stay out of the way of your Discord
session.

## Installation

### Universal installer (Arch Linux / Omarchy)

The primary v1.3.0 installation path manages the overlay and one native Vencord
client without changing pacman packages or requiring root. It supports native
Arch Linux Discord Desktop and Vesktop installations:

```bash
git clone https://github.com/Roddygithub/discord-voice-overlay.git
cd discord-voice-overlay
./install.sh
```

Use `./install.sh --client discord` or `./install.sh --client vesktop` when
both clients are installed. The manager keeps its Vencord checkout and overlay
under `~/.local/share/discord-voice-overlay/`, verifies release checksums,
enables only the managed plugin in Vencord settings, and preserves
`~/.config/vesktop-voice-overlay/config.toml`.

For the optional voice controls in the Thisisgm Omarchy Discord panel, opt in
when installing Vesktop:

```bash
./install.sh --client vesktop --omarchy-voice-controls
```

This compiles a second Vencord userplugin, installs its local bridge, and enables
its setting in Vesktop. Follow
[`integrations/omarchy-discord/README.md`](integrations/omarchy-discord/README.md)
to connect the panel while retaining the original Discord RPC backend. Use
`./install.sh update --no-omarchy-voice-controls` to turn the feature off; a
plain `update` or `repair` preserves the selected mode. When the Thisisgm plugin
is installed from Git, the manager also enables a daily safe updater that keeps
the local bridge adaptation across compatible upstream changes and rolls back
on conflicts.

```bash
./install.sh install    # install or reinstall
./install.sh status     # what is installed, who owns it
./install.sh doctor     # diagnose client / service / ownership problems
./install.sh update     # fetch and verify the latest release
./install.sh repair     # rebuild the managed Vencord checkout
./install.sh uninstall  # remove what the manager owns
```

Release binaries and plugin source bundles are available on the
[`v1.3.0` release page](https://github.com/Roddygithub/discord-voice-overlay/releases/tag/v1.3.0);
the manager normally downloads and verifies the matching assets for you.

Flatpak, AppImage, arbitrary custom installations, and existing foreign custom
Vencord/injected setups are detected or rejected safely — see
[`docs/installer.md`](docs/installer.md). `--dry-run` shows changes without
modifying client, service, or overlay state.

If an existing custom Vencord integration or injected Discord target is found,
the manager refuses to overwrite or silently adopt it. This protects existing
Vencord plugins and client modifications. Use `status` and `doctor` to inspect
ownership and supported-client problems, and review
[`docs/installer.md`](docs/installer.md) before deciding whether to remove or
reconfigure the foreign integration.

## Usage

1. Start the overlay: `systemctl --user start vesktop-voice-overlay` (or run
   `./target/release/vesktop-voice-overlay` directly)
2. Open Discord Desktop or Vesktop and join a voice channel
3. The overlay appears automatically with participant avatars
4. **Green ring** = currently speaking (static highlight)

Settings live in Vencord → Plugins → **VesktopVoice Overlay** (see
[Configuration](#configuration)); changes apply immediately.

## Configuration

Runtime behavior is driven by the plugin settings in Discord Desktop or
Vesktop. Changes apply immediately and are replayed automatically after any
restart.

| Setting | Options |
|---|---|
| `enabled` | show the voice widget in games |
| `position` | top right (default), top left, bottom right, bottom left, center, custom coordinates |
| `customX` / `customY` | horizontal / vertical offset when position is `custom` |
| `userDisplay` | speaking only (default), always |
| `nameDisplay` | speaking only (default), always, never |
| `avatarSize` | small (default), large |
| `monitor` | primary (default), cursor monitor, monitor 0–3; experimental, hotplug reliability unresolved (issue #21) |

An optional TOML file at `~/.config/vesktop-voice-overlay/config.toml` is
read at overlay startup if present — it is **never created or written** by
the overlay. The `[socket]` path and `[overlay].max_participants` are durable
local options. Other overlay display values act as startup defaults and are
overridden when plugin settings arrive. Legacy `[appearance]` and
`overlay.avatar_size` keys are ignored:

```toml
[socket]
path = "/run/user/1000/vesktop-voice-overlay.sock"   # default: $XDG_RUNTIME_DIR/vesktop-voice-overlay.sock
```

The plugin fails closed if `$XDG_RUNTIME_DIR` is unavailable. An explicit
overlay socket path is only useful for manual protocol clients because the
plugin always uses the runtime-directory path.

### Why is the plugin called `VesktopVoiceOverlay`?

`VesktopVoiceOverlay` is the historical internal Vencord plugin identifier.
Vencord uses it as part of plugin identity and persisted settings, so it is
intentionally retained for backward compatibility. The project itself is
Discord Voice Overlay and supports both Discord Desktop and Vesktop.

## Auto-start (systemd user service)

The packaging template installs `vesktop-voice-overlay.service` in
`/usr/lib/systemd/user/`. Once installed, it starts the overlay with your
graphical session, restarts it if it ever exits, and is independent of
Vesktop's lifecycle (the plugin reconnects whenever Vesktop appears).

```bash
# Enable autostart for every session:
systemctl --user enable --now vesktop-voice-overlay.service

# Manual control:
systemctl --user status vesktop-voice-overlay.service
journalctl --user -u vesktop-voice-overlay.service -f
```

If your compositor session does not activate `graphical-session.target`
(e.g. Hyprland started without uwsm), either start it from your Hyprland
config (`exec-once = systemctl --user start vesktop-voice-overlay`) or enable
the default.target variant:

```bash
systemctl --user enable vesktop-voice-overlay.service
```

Running a second instance manually while the service owns the socket fails
cleanly with `another vesktop-voice-overlay instance owns ...` and exit code 1.

## Manual build and development

The paths below are for development, unsupported packaging variants, or users
who intentionally manage the client integration themselves. They are not the
primary v1.3.0 installation path.

### Quick start (Arch Linux / Hyprland)

```bash
# 1. Install build/runtime dependencies
sudo pacman -S rust gtk4 gtk4-layer-shell pkg-config

# 2. Build the overlay
git clone https://github.com/Roddygithub/discord-voice-overlay.git
cd discord-voice-overlay/overlay
cargo build --release --locked

# 3. Build Vencord with the source userplugin (workflow below), then run
./target/release/vesktop-voice-overlay
```

### Prerequisites

```bash
# Arch
sudo pacman -S rust gtk4 libadwaita gtk4-layer-shell pkg-config

# Other distros: install rustc/cargo, GTK4, libadwaita and gtk4-layer-shell
# (on distros that do not package gtk4-layer-shell, build it from source:
#  https://github.com/wmww/gtk4-layer-shell)
```

### Build the overlay (Rust)

```bash
git clone https://github.com/Roddygithub/discord-voice-overlay.git
cd discord-voice-overlay/overlay
cargo build --release --locked
# Binary at: target/release/vesktop-voice-overlay
```

### Pack the plugin source (optional)

```bash
cd ~/discord-voice-overlay/plugin
npm ci
npm pack  # Produces a source bundle, not a directly installable Vesktop plugin
```

Vencord does not load arbitrary npm archives from Vesktop's plugin settings.
The plugin is currently distributed as a Vencord source userplugin and must be
included in a custom Vencord build. It has not been accepted into Vencord's
built-in plugin set.

### Vencord userplugin workflow (supported)

This is the workflow used for development and for custom Vencord client builds
(this is how the plugin is actually built and loaded when using a local
Vencord):

```bash
git clone https://github.com/Vendicated/Vencord.git
cd Vencord
git checkout 3374b8a9d8f6b051c64204917360293aad7f5d75

mkdir -p src/userplugins/vesktopVoiceOverlay
cp <repo>/plugin/src/{index.ts,native.ts,protocol.ts,resendCache.ts,voiceState.ts} \
   src/userplugins/vesktopVoiceOverlay/

pnpm install --no-frozen-lockfile
pnpm build

# REQUIRED: without this sentinel file, the client considers the dist dir
# invalid and silently downloads stock Vencord over your build at launch.
printf '{}\n' > dist/package.json
```

Then point Vesktop at the build: Developer Settings → Vencord Location →
select `.../Vencord/dist`, and fully restart the client.

Verification: `grep -c VesktopVoiceOverlay dist/vencordDesktopRenderer.js`
and `dist/vencordDesktopMain.js` must both be ≥ 1.

### Run

```bash
# Start overlay (keep running in background)
./target/release/vesktop-voice-overlay

# Or with debug logging
RUST_LOG=debug ./target/release/vesktop-voice-overlay
```

## Architecture

```
┌─────────────────┐     Unix Socket ($XDG_RUNTIME_DIR)      ┌──────────────────┐
│ Discord/Vesktop │ ──────────────────────────────────────► │  Overlay Client  │
│ (Vencord Plugin)│ ◄────────────────────────────────────── │  (Rust + GTK4)   │
└─────────────────┘            user-only (0700)             └──────────────────┘
```

| Component | Technology | Role |
|-----------|------------|------|
| **Vencord Plugin** | TypeScript / Node.js | Runs inside Discord Desktop or Vesktop, extracts voice state, sends JSON snapshots via Unix socket |
| **Overlay App** | Rust / GTK4 / layer-shell | Wayland click-through overlay, receives snapshots, renders avatars + speaking indicators |

## Security and privacy

- ✅ **No Discord token** — never reads, stores, or transmits your account token
- ✅ **No self-bots** — no separate Discord Gateway connections
- ✅ **Same-user IPC** — Unix domain socket under `$XDG_RUNTIME_DIR` with `0700` permissions + `SO_PEERCRED` UID validation
- ✅ **Minimal data boundary** — only required voice-state snapshots cross the local socket; avatar images may be fetched from Discord's CDN over HTTPS

## Socket protocol

See [`docs/protocol.md`](docs/protocol.md) for the full spec.

**Handshake:**

```
Server sends: "VESKTOP_VOICE_OVERLAY/1.0\n"
Client validates, then sends JSON Lines snapshots
```

On voice-channel leave, the plugin sends `{"type":"clear"}` so stale rows are
removed immediately and the clear state is replayed after reconnects.

**Snapshot:**

```json
{
  "version": 1,
  "timestamp": 1692000000000,
  "self": {
    "userId": "123...",
    "username": "You",
    "avatarUrl": "https://cdn.discordapp.com/...",
    "mute": false,
    "deaf": false,
    "speaking": true
  },
  "participants": [
    { "userId": "456...", "username": "Friend", "avatarUrl": "...", "speaking": false, "volume": 80 }
  ]
}
```

## Supported compositors

Layer-shell support is compositor-dependent:

- ✅ **Hyprland** (primary target) — validated end-to-end on Hyprland 0.56
  with Guild Wars 2 (windowed/borderless): overlay visibility, pointer
  click-through, game focus, speaking show/hide, avatar sizing
- ⚠️ **sway** / **niri** / **wayfire** — expected to work through layer-shell,
  but not individually validated
- ⚠️ **GNOME / KDE** (layer-shell support varies) — untested
- ⚠️ **Exclusive-fullscreen** games — untested; monitor selection is
  configurable, but hotplug may crash the candidate in GTK/Wayland dispatch.
  See issue #21; do not rely on it for hotplug until resolved.

## Distribution

| Component | Channel | Install command |
|-----------|---------|-----------------|
| **Overlay (Rust)** | Source build; unpublished AUR template | Build with Cargo |
| **Plugin (TypeScript)** | Source userplugin / GitHub source bundle | Build inside pinned Vencord source |

Both components are versioned together via Git tags (`v1.0.0`, `v1.1.0`, …) —
a matching plugin + overlay share a compatible socket protocol.

A `PKGBUILD` lives in [`packaging/aur/`](packaging/aur/), but **no package is
currently published in the AUR**; build from source in the meantime.

## Development

### Project structure

```
discord-voice-overlay/
├── plugin/                    # Vencord plugin (TypeScript)
│   ├── src/
│   │   ├── index.ts          # Plugin entry point + settings
│   │   ├── protocol.ts       # Socket protocol types + serialization
│   │   ├── native.ts         # Node.js socket client (main process, net)
│   │   ├── resendCache.ts    # Reconnect backoff + settings/snapshot replay
│   │   └── voiceState.ts     # Vencord voice state accessors
│   ├── package.json
│   └── tsconfig.json
├── overlay/                   # Overlay app (Rust)
│   ├── src/
│   │   ├── main.rs           # GTK4 app entry
│   │   ├── layer_shell.rs    # Wayland layer-shell setup + monitor resolution
│   │   ├── socket_server.rs  # Unix socket server + SO_PEERCRED
│   │   ├── lifecycle.rs      # Overlay show/hide logic
│   │   ├── protocol.rs       # Protocol deserialization
│   │   ├── config.rs         # Optional TOML config (loaded once at startup)
│   │   └── ui/               # GTK4 widgets
│   └── Cargo.toml
├── packaging/aur/             # AUR PKGBUILD
├── memory-bank/               # Engineering docs (PRD, Tech Stack, Plan)
├── docs/protocol.md           # Socket protocol v1 spec
├── docs/installer.md          # Universal installer reference
└── .github/workflows/         # CI/CD pipelines
```

### CI/CD pipeline

- **CI** (`.github/workflows/ci.yml`) — format check, build, test for both components
- **Release** (`.github/workflows/release.yml`) — tag push → validates and builds
  artifacts → GitHub Release → optional AUR update when credentials are present

```bash
# Local validation
cd overlay && cargo fmt --check && cargo clippy --all-targets --all-features -- -D warnings && cargo test --locked
cd ../plugin && npm run lint && npm test
```

## License

GPL-3.0 — see [LICENSE](LICENSE).

Compatible with upstream projects:

- [Discover Overlay](https://github.com/trigg/Discover) (GPL-3.0) — design inspiration
- [Vesktop](https://github.com/Vencord/Vesktop) (GPL-3.0) — supported client
- [Discord](https://discord.com/) — supported client
- [Vencord](https://github.com/Vendicated/Vencord) (GPL-3.0) — plugin platform

## Disclaimer

> This project is not affiliated with Discord, Vesktop, Vencord, or Discover
> Overlay. Client modifications may violate Discord's Terms of Service; use at
> your own risk.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. Significant architecture
or protocol changes should be discussed in an issue first.

---

**Built with** 🦀 Rust + 📘 TypeScript + 🎨 GTK4 + 🌊 Wayland layer-shell
