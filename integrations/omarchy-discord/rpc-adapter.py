#!/usr/bin/env python3
"""Run the native Vencord bridge for Vesktop or upstream rpc.py for Discord."""

import os
import sys

INTEGRATION_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    args = sys.argv[1:]
    try:
        index = args.index("--client")
    except ValueError:
        client = "discord"
    else:
        if index + 1 >= len(args):
            print("--client requires vesktop or discord", file=sys.stderr)
            return 2
        client = args[index + 1]
        del args[index:index + 2]

    if client not in ("vesktop", "discord"):
        print("unsupported Discord client: %s" % client, file=sys.stderr)
        return 2

    if client == "vesktop":
        if "--save" in args or "--setup" in args:
            print("Vesktop voice controls use the local Vencord bridge; OAuth setup is not needed.", file=sys.stderr)
            return 2
        target = os.path.join(INTEGRATION_DIR, "vbridge.py")
    else:
        config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        target = os.path.join(config_home, "omarchy/plugins/io.github.thisisgm.discord/rpc.py")

    if not os.path.isfile(target):
        print("voice bridge script not found: %s" % target, file=sys.stderr)
        return 1
    os.execv(sys.executable, [sys.executable, target, *args])


if __name__ == "__main__":
    sys.exit(main())
