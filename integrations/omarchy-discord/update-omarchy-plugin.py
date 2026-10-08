#!/usr/bin/env python3
"""Safely fast-forward omarchy-discord while preserving the local Vesktop adapter."""

import fcntl
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PLUGIN_ID = "io.github.thisisgm.discord"
PLUGIN_FILES = ("Model.js", "Panel.qml", "Rpc.qml", "Service.qml", "tests/tst_model.qml")
EXPECTED_REMOTE = os.environ.get("OMARCHY_UPDATE_EXPECTED_REMOTE", "https://github.com/thisisgm/omarchy-discord")
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
MANAGED_DIR = Path(os.environ.get("OMARCHY_UPDATE_MANAGED_DIR", str(Path(__file__).resolve().parent)))
PLUGIN_DIR = Path(os.environ.get("OMARCHY_UPDATE_PLUGIN_DIR", str(CONFIG_HOME / "omarchy/plugins" / PLUGIN_ID)))
PATCH_PATH = Path(os.environ.get("OMARCHY_UPDATE_PATCH_PATH", str(MANAGED_DIR / "panel-adaptation.patch")))
LOCK_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "omarchy-discord-update.lock"


class UpdateError(RuntimeError):
    pass


def run(args, *, cwd=None, check=True, capture=False, binary=False):
    result = subprocess.run(
        args,
        cwd=cwd,
        text=not binary,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and result.returncode:
        details = result.stderr.strip() if capture else ""
        raise UpdateError(f"command failed ({result.returncode}): {' '.join(map(str, args))} {details}")
    return result


def git(*args, check=True, capture=False, binary=False):
    return run(["git", "-C", str(PLUGIN_DIR), *args], check=check, capture=capture, binary=binary)


def notify(title, message, urgency="normal"):
    notify_send = shutil.which("notify-send")
    if notify_send:
        subprocess.run([notify_send, "--app-name=Omarchy Discord", "--urgency=" + urgency, title, message], check=False)


def validate_checkout():
    if PLUGIN_DIR.is_symlink():
        raise UpdateError(f"refusing symlinked plugin checkout: {PLUGIN_DIR}")
    if not (PLUGIN_DIR / ".git").is_dir():
        raise UpdateError(f"Omarchy Discord plugin is not a git checkout: {PLUGIN_DIR}")
    remote = git("remote", "get-url", "origin", capture=True).stdout.strip().removesuffix(".git")
    if remote not in (EXPECTED_REMOTE, "git@github.com:thisisgm/omarchy-discord"):
        raise UpdateError(f"unexpected plugin origin: {remote} (expected {EXPECTED_REMOTE})")


def local_patch():
    staged = git("diff", "--cached", "--name-only", capture=True).stdout.splitlines()
    if staged:
        raise UpdateError("staged plugin changes found; refusing automated update")
    changed = git("diff", "--name-only", capture=True).stdout.splitlines()
    unexpected = sorted(set(changed) - set(PLUGIN_FILES))
    if unexpected:
        raise UpdateError("unexpected local plugin edits: " + ", ".join(unexpected))
    untracked = git("ls-files", "--others", "--exclude-standard", capture=True).stdout.splitlines()
    if untracked:
        raise UpdateError("untracked files in plugin checkout: " + ", ".join(untracked))
    return git(
        "-c", "diff.mnemonicprefix=false", "diff", "--binary", "--", *PLUGIN_FILES,
        capture=True, binary=True,
    ).stdout


def write_patch(payload):
    if PATCH_PATH.is_symlink():
        raise UpdateError(f"refusing symlinked patch file: {PATCH_PATH}")
    MANAGED_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".panel-adaptation.", dir=MANAGED_DIR)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        os.chmod(temporary, 0o600)
        os.replace(temporary, PATCH_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def git_apply(payload, *args, check=True):
    result = subprocess.run(
        ["git", "-C", str(PLUGIN_DIR), "apply", *args],
        input=payload,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode:
        raise UpdateError("could not apply the saved local panel adaptation: " + result.stderr.decode("utf-8", "replace").strip())
    return result


def has_vesktop_process():
    result = subprocess.run(["pgrep", "-x", "vesktop"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return result.returncode == 0


def check_vesktop_bridge():
    if os.environ.get("OMARCHY_UPDATE_SKIP_VESKTOP_CHECK") == "1":
        return
    if not has_vesktop_process():
        return
    bridge = MANAGED_DIR / "vbridge.py"
    for attempt in range(3):
        result = subprocess.run([sys.executable, str(bridge), "--probe"], text=True, capture_output=True)
        if result.returncode == 0:
            print("Vesktop voice bridge: " + result.stdout.strip())
            return
        if attempt < 2:
            time.sleep(5)
    message = "Vesktop is running but its voice-control socket did not answer. Run install.sh repair --omarchy-voice-controls and inspect Vencord before testing a call."
    print("Warning: " + message, file=sys.stderr)
    notify("Vesktop voice controls unavailable", message, "critical")


def capture():
    if not (PLUGIN_DIR / ".git").is_dir():
        print("No git-managed omarchy-discord checkout; automatic plugin updates are not enabled.")
        return
    validate_checkout()
    payload = local_patch()
    if payload:
        if PATCH_PATH.exists() and PATCH_PATH.read_bytes() != payload:
            raise UpdateError("local panel adaptation changed; review it before replacing the saved update patch")
        if not PATCH_PATH.exists():
            write_patch(payload)
        print(f"Saved local panel adaptation: {PATCH_PATH}")
    else:
        print("No local panel adaptation to save.")


def restore_patch(payload):
    if payload:
        git_apply(payload)


def update_once():
    validate_checkout()
    if PATCH_PATH.is_symlink():
        raise UpdateError(f"refusing symlinked panel patch: {PATCH_PATH}")
    payload = PATCH_PATH.read_bytes() if PATCH_PATH.exists() else b""
    current = local_patch()
    if current and current != payload:
        raise UpdateError("working-tree adaptation differs from the saved copy; refusing automated update")

    if not PATCH_PATH.exists() and current:
        write_patch(current)
        payload = current

    run(["git", "-C", str(PLUGIN_DIR), "fetch", "--quiet", "origin", "HEAD"])
    old_head = git("rev-parse", "HEAD", capture=True).stdout.strip()
    remote_head = git("rev-parse", "FETCH_HEAD", capture=True).stdout.strip()
    patch_is_local = bool(current)
    patch_is_upstream = False

    if not current and payload:
        reverse_check = git_apply(payload, "--reverse", "--check", check=False)
        if reverse_check.returncode == 0:
            patch_is_upstream = True
        elif git_apply(payload, "--check", check=False).returncode != 0:
            raise UpdateError("saved panel adaptation no longer applies to this plugin revision")

    if remote_head == old_head:
        if not current and payload and not patch_is_upstream:
            git_apply(payload)
            write_patch(local_patch())
            run(["omarchy", "restart", "shell"])
            print("Restored the local Vesktop panel adaptation.")
        check_vesktop_bridge()
        print("omarchy-discord is up to date.")
        return

    if patch_is_local:
        git_apply(payload, "--reverse")
    if git("status", "--porcelain", capture=True).stdout.strip():
        restore_patch(payload if patch_is_local else b"")
        raise UpdateError("plugin checkout did not become clean before upstream update")

    result = subprocess.run(["omarchy", "plugin", "update", PLUGIN_ID, "--yes"])
    new_head = git("rev-parse", "HEAD", capture=True).stdout.strip()
    if result.returncode:
        if new_head != old_head:
            git("reset", "--hard", old_head)
        restore_patch(payload if patch_is_local else b"")
        raise UpdateError("Omarchy plugin updater failed; the previous plugin version was restored")

    if payload and not patch_is_upstream:
        if git_apply(payload, "--check", check=False).returncode == 0:
            git_apply(payload)
        elif git_apply(payload, "--reverse", "--check", check=False).returncode == 0:
            patch_is_upstream = True
        else:
            git("reset", "--hard", old_head)
            restore_patch(payload if patch_is_local else b"")
            raise UpdateError("upstream changed the same panel code; update rolled back and the local adapter was restored")

    try:
        run(["omarchy", "plugin", "validate", str(PLUGIN_DIR)])
        qmltestrunner = "/usr/lib/qt6/bin/qmltestrunner"
        if os.environ.get("OMARCHY_UPDATE_SKIP_QML_TEST") != "1" and os.path.isfile(qmltestrunner):
            run([qmltestrunner, "-input", str(PLUGIN_DIR / "tests")], capture=False)
    except UpdateError:
        git("reset", "--hard", old_head)
        restore_patch(payload if patch_is_local else b"")
        raise UpdateError("updated plugin failed local validation; the previous version was restored")

    current_after = local_patch()
    write_patch(current_after)
    run(["omarchy", "restart", "shell"])
    check_vesktop_bridge()
    if new_head != old_head:
        print(f"Updated omarchy-discord: {old_head[:8]} → {new_head[:8]}")
        notify("Omarchy Discord plugin updated", f"Updated to {new_head[:8]} and restored the Vesktop bridge adaptation.")


def main():
    MANAGED_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_path = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "omarchy-discord-update.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if "--capture" in sys.argv:
            capture()
        else:
            update_once()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except UpdateError as error:
        print("omarchy-discord-update: %s" % error, file=sys.stderr)
        notify("Omarchy Discord update needs attention", str(error), "critical")
        sys.exit(1)
