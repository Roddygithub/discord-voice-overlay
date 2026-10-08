import definePlugin, { PluginNative } from "@utils/types";
import { findByPropsLazy, findStoreLazy } from "@webpack";

// Voice controls for the Omarchy bar, straight from Vesktop's renderer.
// The plugin hosts a local Unix socket (via its native module) and speaks the
// same line-JSON contract as the omarchy-discord plugin's rpc.py, minus OAuth:
// commands in, state snapshots out. No token, no client id, no gateway.

type NativeModule = PluginNative<typeof import("./native")>;
let Native: NativeModule;

const VoiceStateStore = findStoreLazy("VoiceStateStore");
const ChannelStore = findStoreLazy("ChannelStore");
const GuildStore = findStoreLazy("GuildStore");
const UserStore = findByPropsLazy("getUser", "getCurrentUser");
const VoiceActions = findByPropsLazy("toggleSelfMute", "toggleSelfDeaf");
const ChannelActions = findByPropsLazy("selectVoiceChannel");

let pollTimer: ReturnType<typeof setInterval> | null = null;

// rpc.py tracks these across calls, and so do we: the panel reads mute/deaf
// even in the moments where the voice state store has no self entry.
let lastMute = false;
let lastDeaf = false;
let inputVolume = 100;

const speakingUsers = new Set<string>();

function currentUser(): any {
    try {
        return UserStore.getCurrentUser();
    } catch {
        return null;
    }
}

function selfVoiceState(): any {
    const me = currentUser();
    if (!me) return null;
    try {
        return VoiceStateStore.getVoiceStateForUser(me.id) ?? null;
    } catch {
        return null;
    }
}

function applyInputVolume(value: number) {
    try {
        const actions = findByPropsLazy("setInputVolume") as any;
        actions?.setInputVolume?.(value);
    } catch (error) {
        console.error("[VesktopVoiceControl] setInputVolume unavailable:", error);
    }
}

function buildStateLine(): string {
    const me = currentUser();
    const voiceState = selfVoiceState();
    const channelId: string | null = voiceState?.channelId ?? null;
    const inVoice = !!channelId;

    let channel = "";
    let guild = "";
    if (channelId) {
        try {
            const ch = ChannelStore.getChannel(channelId);
            channel = ch?.name ?? "";
            const guildId = ch?.guild_id ?? null;
            if (guildId) guild = GuildStore.getGuild(guildId)?.name ?? "";
        } catch {
            // Names are cosmetic; the call rows survive without them.
        }
    }

    if (voiceState) {
        lastMute = !!(voiceState.selfMute || voiceState.mute);
        lastDeaf = !!(voiceState.selfDeaf || voiceState.deaf);
    }

    const speaking: string[] = [];
    if (channelId) {
        try {
            const states = VoiceStateStore.getVoiceStatesForChannel(channelId) ?? {};
            for (const userId of Object.keys(states)) {
                if (userId === me?.id || !speakingUsers.has(userId)) continue;
                const user = UserStore.getUser(userId);
                speaking.push(user?.globalName ?? user?.username ?? userId);
            }
        } catch {
            // Speaking names are cosmetic.
        }
    }

    return JSON.stringify({
        type: "state",
        inVoice,
        channel,
        guild,
        mute: lastMute,
        deaf: lastDeaf,
        inputVolume,
        speaking: speaking.sort(),
        ping: 0,
        voiceState: inVoice ? "VOICE_CONNECTED" : "DISCONNECTED",
    });
}

function publish() {
    if (!Native) return;
    void Native.publishState(buildStateLine());
}

function handleCommand(line: string) {
    let message: any;
    try {
        message = JSON.parse(line);
    } catch {
        return;
    }
    const name = message?.cmd;

    if (name === "mute" || name === "deaf") {
        const want = message.value === true;
        const current = name === "mute" ? lastMute : lastDeaf;
        // toggleSelfMute toggles, so only act when the request differs.
        if (want !== current) {
            try {
                if (name === "mute") VoiceActions.toggleSelfMute();
                else VoiceActions.toggleSelfDeaf();
            } catch (error) {
                console.error("[VesktopVoiceControl] toggle failed:", error);
            }
        }
        publish();
        return;
    }

    if (name === "inputVolume") {
        const value = Math.round(Number(message.value));
        if (!Number.isFinite(value)) return;
        inputVolume = Math.max(0, Math.min(100, value));
        applyInputVolume(inputVolume);
        publish();
        return;
    }

    if (name === "disconnect") {
        try {
            ChannelActions.selectVoiceChannel(null);
        } catch (error) {
            console.error("[VesktopVoiceControl] leave call failed:", error);
        }
        publish();
        return;
    }

    if (name === "refresh") {
        publish();
        return;
    }
}

function poll() {
    if (!Native) return;
    void (async () => {
        try {
            const lines = await Native.pollCommands();
            for (const line of lines) handleCommand(line);
        } catch (error) {
            console.error("[VesktopVoiceControl] poll failed:", error);
        }
    })();
}

export default definePlugin({
    name: "VesktopVoiceControl",
    description: "Exposes Vesktop's voice call state and controls on a local socket for the Omarchy bar",
    authors: [{ name: "Roddy", id: 0n }],
    tags: ["Voice", "Integration"],
    start() {
        Native = VencordNative.pluginHelpers
            .VesktopVoiceControl as NativeModule;

        void (async () => {
            const socketPath = await Native.getSocketPath();
            await Native.startControlSocket(socketPath);
            publish();
        })();

        pollTimer = setInterval(poll, 150);
    },
    stop() {
        if (pollTimer) clearInterval(pollTimer);
        pollTimer = null;
        void Native?.stopControlSocket();
    },
    flux: {
        VOICE_STATE_UPDATES() {
            publish();
        },
        VOICE_CHANNEL_SELECT() {
            publish();
        },
        SPEAKING(event: any) {
            if (!event?.userId) return;
            const speaking = event.speakingFlags !== undefined
                ? event.speakingFlags !== 0
                : event.speaking !== false && event.speaking !== 0;
            if (speaking) speakingUsers.add(event.userId);
            else speakingUsers.delete(event.userId);
            publish();
        },
        STOP_SPEAKING(event: any) {
            if (!event?.userId) return;
            speakingUsers.delete(event.userId);
            publish();
        },
    },
});
