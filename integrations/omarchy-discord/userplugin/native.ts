import { IpcMainInvokeEvent } from "electron";
import fs from "node:fs";
import net from "node:net";

// Line-delimited JSON over a user-only Unix socket. The renderer owns every
// decision; this module is a dumb, safe pipe: it broadcasts state lines from
// the renderer and queues command lines for the renderer to poll.

const PROTOCOL_HEADER = "VESKTOP_VOICE_CONTROL/1.0";
const MAX_COMMAND_LINE = 4096;
const MAX_QUEUED_COMMANDS = 100;

type Client = {
    socket: net.Socket;
    buffer: string;
};

let server: net.Server | null = null;
let clients = new Set<Client>();
let commandQueue: string[] = [];

export function getSocketPath(_: IpcMainInvokeEvent): string {
    const runtimeDir = process.env.XDG_RUNTIME_DIR || `/run/user/${process.getuid()}`;
    return `${runtimeDir}/vesktop-voice-control.sock`;
}

export function startControlSocket(_: IpcMainInvokeEvent, socketPath: string): void {
    stopControlSocket(_);

    try {
        fs.unlinkSync(socketPath);
    } catch {
        // No stale socket; nothing to clean.
    }

    server = net.createServer(client => {
        const entry: Client = { socket: client, buffer: "" };
        clients.add(entry);
        client.write(`${PROTOCOL_HEADER}\n`);

        client.on("data", (data: Buffer) => {
            entry.buffer += data.toString();
            let index: number;
            while ((index = entry.buffer.indexOf("\n")) !== -1) {
                const line = entry.buffer.slice(0, index).trim();
                entry.buffer = entry.buffer.slice(index + 1);
                if (!line || line.length > MAX_COMMAND_LINE) continue;
                if (commandQueue.length >= MAX_QUEUED_COMMANDS) commandQueue.shift();
                commandQueue.push(line);
            }
        });

        const remove = () => clients.delete(entry);
        client.on("close", remove);
        client.on("error", remove);
    });

    server.on("error", err => {
        console.error("[VesktopVoiceControl] server error:", err.message);
    });

    server.listen(socketPath, () => {
        try {
            fs.chmodSync(socketPath, 0o600);
        } catch {
            // $XDG_RUNTIME_DIR is already 0700; the chmod is belt and braces.
        }
    });
}

export function publishState(_: IpcMainInvokeEvent, line: string): void {
    if (typeof line !== "string" || line.length === 0 || line.length > 8192) return;
    for (const entry of [...clients]) {
        if (entry.socket.destroyed) {
            clients.delete(entry);
            continue;
        }
        entry.socket.write(`${line}\n`);
    }
}

export function pollCommands(_: IpcMainInvokeEvent): string[] {
    const out = commandQueue;
    commandQueue = [];
    return out;
}

export function stopControlSocket(_: IpcMainInvokeEvent): void {
    for (const entry of clients) entry.socket.destroy();
    clients.clear();
    commandQueue = [];
    if (server) {
        try {
            server.close();
        } catch {
            // Already closed.
        }
        server = null;
    }
}
