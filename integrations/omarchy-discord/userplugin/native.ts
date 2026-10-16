import { IpcMainInvokeEvent } from "electron";
import fs from "node:fs";
import net from "node:net";

// Line-delimited JSON over a user-only Unix socket. The renderer owns every
// decision; this module is a dumb, safe pipe: it broadcasts state lines from
// the renderer and queues command lines for the renderer to poll.

const PROTOCOL_HEADER = "VESKTOP_VOICE_CONTROL/1.0";
const MAX_COMMAND_LINE = 4096;
const MAX_COMMAND_BUFFER = MAX_COMMAND_LINE;
const MAX_QUEUED_COMMANDS = 100;
const MAX_CLIENTS = 4;
const MAX_PENDING_STATE_BYTES = 16 * 1024;

type Client = {
    socket: net.Socket;
    buffer: string;
    pendingState: string | null;
};

let server: net.Server | null = null;
let clients = new Set<Client>();
let commandQueue: string[] = [];

export function getSocketPath(_: IpcMainInvokeEvent): string {
    const uid = typeof process.getuid === "function" ? process.getuid() : 0;
    const runtimeDir = process.env.XDG_RUNTIME_DIR || `/run/user/${uid}`;
    return `${runtimeDir}/vesktop-voice-control.sock`;
}

export function startControlSocket(event: IpcMainInvokeEvent, _socketPath: string): void {
    stopControlSocket(event);
    const socketPath = getSocketPath(event);

    try {
        const stat = fs.lstatSync(socketPath);
        if (!stat.isSocket()) {
            throw new Error(`refusing to replace non-socket path: ${socketPath}`);
        }
        fs.unlinkSync(socketPath);
    } catch (error) {
        if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }

    server = net.createServer(client => {
        if (clients.size >= MAX_CLIENTS) {
            client.destroy();
            return;
        }
        const entry: Client = { socket: client, buffer: "", pendingState: null };
        clients.add(entry);
        client.write(`${PROTOCOL_HEADER}\n`);

        client.on("drain", () => {
            if (!entry.pendingState || client.destroyed) return;
            const pending = entry.pendingState;
            entry.pendingState = null;
            try {
                if (!client.write(pending)) entry.pendingState = pending;
            } catch {
                client.destroy();
            }
        });

        client.on("data", (data: Buffer) => {
            entry.buffer += data.toString();
            if (Buffer.byteLength(entry.buffer) > MAX_COMMAND_BUFFER) {
                client.destroy();
                return;
            }
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
    server.maxConnections = MAX_CLIENTS;

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
    if (typeof line !== "string" || line.length === 0 || Buffer.byteLength(line) > 8192) return;
    const payload = `${line}\n`;
    for (const entry of [...clients]) {
        if (entry.socket.destroyed) {
            clients.delete(entry);
            continue;
        }
        if (entry.pendingState || entry.socket.writableNeedDrain || entry.socket.writableLength > MAX_PENDING_STATE_BYTES) {
            entry.pendingState = payload;
            continue;
        }
        try {
            entry.socket.write(payload);
        } catch {
            entry.socket.destroy();
        }
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
