# Omarchy Discord voice controls for Vesktop

Optional integration for the [Thisisgm Omarchy Discord panel](https://github.com/thisisgm/omarchy-discord). It reuses the panel's existing JSON-lines state and command contract while obtaining voice state from Vencord inside Vesktop. It does not disable arRPC, request OAuth credentials, or connect to a Discord Gateway.

The Vencord source plugin is compiled into the managed Vencord build only when `install.sh --client vesktop --omarchy-voice-controls` is requested. It creates a same-user Unix socket at `$XDG_RUNTIME_DIR/vesktop-voice-control.sock` with mode `0600`. The Python adapter dispatches Vesktop to this socket and leaves the panel's original `rpc.py` backend available for native Discord.

## Connect the panel

In `Rpc.qml`, set `scriptPath` to the adapter installed at:

```qml
readonly property string scriptPath: StandardPaths.writableLocation(StandardPaths.GenericDataLocation)
  + "/discord-voice-overlay/omarchy-discord/rpc-adapter.py"
```

Import `QtCore` for `StandardPaths`. Pass the running client ID to the bridge process and setup process:

```qml
command: ["python3", root.scriptPath, "--client", root.clientId]
```

The enclosing service should expose `clientId` as `vesktop` or `discord`, based on the main process/window, bind it to `Rpc.clientId`, and pass it to the process that runs the adapter. Pass it to the `--save` process too. The adapter delegates Discord to the plugin's original `rpc.py` and Vesktop to the local Vencord bridge. Keep the original `rpc.py` in the plugin directory.

The installer option installs the adapter and bridge under XDG data and enables `VesktopVoiceControl` in Vesktop's actual settings file. When the Thisisgm plugin is a Git checkout, it also snapshots the local panel adaptation and enables a daily user timer. The timer fast-forwards compatible upstream updates, reapplies and validates the adaptation, and rolls back/notifies on conflicts. Vesktop package updates leave the managed Vencord directory intact; the timer checks the bridge while Vesktop runs rather than rebuilding the same pinned Vencord version. Disabling the option removes the timer, bridge source, and managed setting; uninstall restores the prior setting when the settings file has not subsequently changed.

To stop only the scheduled check while keeping the voice bridge enabled:

```bash
systemctl --user disable --now discord-voice-overlay-omarchy-update.timer
```

## Validation

```bash
python3 vbridge.py --probe
```

The output should contain the active call's channel, guild, mute/deafen state, and input gain. A missing control socket means the opt-in plugin is not enabled in the running Vencord build.

## Source provenance

The first implementation was authored in `Roddygithub/vesktop-voice-control` at commit `6acdb3a546245c44b4985397e3b0d61c27d4ae61`; the TypeScript userplugin is retained from that source, and the bridge's initial-state handshake is hardened here. This copy is maintained under this repository's GPL-3.0 license. Its compatibility boundary is the JSON-lines contract of `thisisgm/omarchy-discord` `rpc.py`.
