# Discord Voice Overlay Installer

The installer is a user-run Bash manager for native Arch Linux installations.
It deliberately keeps package management separate from user-level Vencord
integration.

## Requirements

- Linux with a Wayland session and a layer-shell compositor
- Native Arch `vesktop` and/or `discord` package
- `git`, Node.js, pnpm 11.9+, `curl`, `sha256sum`, `realpath`, and systemd
- A working Vencord build environment; the manager uses the pinned revision
  `3374b8a9d8f6b051c64204917360293aad7f5d75`

## Commands

```text
install       detect and configure one native client
update        reuse current state and rebuild only when needed
repair        restore missing project-owned pieces
status        show clients, ownership, service, and build state
doctor        check commands, session, and supported clients
uninstall     remove project-owned integration and preserve config
```

`--client vesktop|discord` selects a client. When both are installed, selection
is mandatory. `--yes` explicitly approves Vesktop state switching or Discord
application-resource injection. `--dry-run` performs detection and prints
planned actions without mutation.

`--omarchy-voice-controls` is an explicit Vesktop-only opt-in. It builds the
additional `VesktopVoiceControl` Vencord plugin, enables it in Vesktop's
`~/.config/vesktop/settings/settings.json`, and installs the Thisisgm-compatible
adapter and bridge under the managed data tree. `--no-omarchy-voice-controls`
disables it. `update` and `repair` preserve the recorded choice unless one of
those options is supplied. The feature does not disable arRPC or replace
`rpc.py` for native Discord. See
[`../integrations/omarchy-discord/README.md`](../integrations/omarchy-discord/README.md)
for the local panel connection.

## Ownership

The manager owns only:

- `~/.local/share/discord-voice-overlay/`
- `~/.local/state/discord-voice-overlay/state.env`
- its exact user unit at `~/.config/systemd/user/vesktop-voice-overlay.service`
- the selected Vesktop `vencordDir` value, with a rollback copy
- a Discord injection only when the manager performed it through Vencord
- the Vesktop voice-control plugin source/build and its settings only when
  `--omarchy-voice-controls` was selected

The overlay configuration at
`~/.config/vesktop-voice-overlay/config.toml` is never written or removed.
Existing package-owned binaries, system units, custom Vencord source trees,
custom userplugins, and foreign Discord injections are not overwritten.

## Managed Vencord

The checkout is cloned from the official Vencord repository at the exact pinned
revision above. The five overlay plugin source files are copied into
`src/userplugins/vesktopVoiceOverlay/`. With the explicit opt-in, the two
`VesktopVoiceControl` source files are also copied into
`src/userplugins/vesktopVoiceControl/`. `pnpm install --frozen-lockfile` and
`pnpm build` run as the normal user; every requested plugin must be present in
both desktop bundles before the checkout is activated.

The manager enables `plugins.VesktopVoiceOverlay.enabled` in the settings
directory of the selected client: `~/.config/Vencord/settings/settings.json`
for native Discord and `~/.config/vesktop/settings/settings.json` for Vesktop.
Vesktop sets `VENCORD_USER_DATA_DIR` to its own data directory, so its settings
are not stored in the native Discord path. The opt-in `VesktopVoiceControl`
setting shares the Vesktop settings file. Each JSON file is parsed structurally
and written atomically; unrelated settings are preserved. Managed settings
backups are restored on conservative uninstall only if the corresponding file
has not changed since installation. Legacy Vesktop installs recorded with the
old `~/.config/Vencord` path migrate that managed setting safely.

Builds happen in a staging directory. The prior managed checkout is retained as
`vencord.previous` until a replacement has built successfully. No arbitrary
existing Vencord checkout is edited.

## Client Integration

For Vesktop, the manager changes only `~/.config/vesktop/state.json`'s
`vencordDir` field and preserves all other JSON fields. If another custom path
is already configured, explicit `--yes` is required and the original file is
backed up inside the managed tree.

For native Discord Desktop, the manager verifies the target under
`~/.config/discord/app-*/resources` and requires explicit `--yes`. It invokes
Vencord's official pinned `scripts/runInstaller.mjs` wrapper with the CLI's
explicit `--install`/`--uninstall -location <app-directory>` arguments. It
never patches an `app.asar` itself. An existing `_app.asar` backup is treated
as a foreign injection and blocks setup.

Switching clients is explicit and does not add multi-client socket arbitration.
The previously manager-owned integration is removed only when its recorded
rollback evidence still matches.

## Unsupported Variants

Flatpak clients, AppImages, arbitrary custom paths, and ambiguous existing
Vencord installations are not configured by this candidate. They are reported
without modifying their application trees. Existing custom Vencord adoption is
deferred until it can be made safe without overwriting user customizations.

## Uninstall And Recovery

Uninstall disables only the exact manager-owned user service, calls the official
Vencord uninject path when attributable, restores Vesktop state when it still
points at the managed build, and removes the managed data tree. Configuration
is preserved. If a user changes a managed client state after installation, the
manager leaves it untouched and reports the conflict.

State is a small mode-600 `key=value` manifest. It contains paths, versions,
revision, selected client, and rollback hashes only. It contains no token,
credential, message, session, or voice data.
