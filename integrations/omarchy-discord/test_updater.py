import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("update-omarchy-plugin.py")
def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, text=True, capture_output=True).stdout.strip()


class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="omarchy-discord-update-test.")
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.plugin = self.root / "plugin"
        self.upstream = self.root / "upstream"
        self.patch = self.root / "panel.patch"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        subprocess.run(["git", "init", "--bare", "--initial-branch=master", str(self.remote)], check=True, capture_output=True)
        subprocess.run(["git", "clone", str(self.remote), str(self.plugin)], check=True, capture_output=True)
        git(self.plugin, "config", "user.email", "test@example.invalid")
        git(self.plugin, "config", "user.name", "test")
        subprocess.run(["git", "-C", str(self.plugin), "remote", "set-url", "origin", str(self.remote)], check=True)
        (self.plugin / "Rpc.qml").write_text('readonly property string scriptPath: "rpc.py"\n')
        (self.plugin / "README.md").write_text("upstream base\n")
        git(self.plugin, "add", "Rpc.qml", "README.md")
        git(self.plugin, "commit", "-m", "base")
        git(self.plugin, "push", "-u", "origin", "master")
        self.old_head = git(self.plugin, "rev-parse", "HEAD")
        (self.plugin / "Rpc.qml").write_text('readonly property string scriptPath: "rpc-adapter.py"\n')
        subprocess.run(["git", "clone", str(self.remote), str(self.upstream)], check=True, capture_output=True)
        git(self.upstream, "config", "user.email", "test@example.invalid")
        git(self.upstream, "config", "user.name", "test")

        (self.bin / "omarchy").write_text(
            "#!/usr/bin/env bash\n"
            "set -e\n"
            'if [[ "$1 $2" == "plugin update" ]]; then git -C "$OMARCHY_UPDATE_PLUGIN_DIR" merge --ff-only FETCH_HEAD; exit; fi\n'
            'if [[ "$1 $2" == "plugin validate" ]]; then exit 0; fi\n'
            'if [[ "$1 $2" == "restart shell" ]]; then exit 0; fi\n'
            "exit 2\n"
        )
        (self.bin / "notify-send").write_text("#!/usr/bin/env bash\nexit 0\n")
        for executable in (self.bin / "omarchy", self.bin / "notify-send"):
            executable.chmod(0o755)

        self.env = os.environ.copy()
        self.env.update({
            "PATH": str(self.bin) + os.pathsep + self.env["PATH"],
            "OMARCHY_UPDATE_PLUGIN_DIR": str(self.plugin),
            "OMARCHY_UPDATE_PATCH_PATH": str(self.patch),
            "OMARCHY_UPDATE_MANAGED_DIR": str(self.root / "managed"),
            "OMARCHY_UPDATE_EXPECTED_REMOTE": str(self.remote).removesuffix(".git"),
            "OMARCHY_UPDATE_SKIP_VESKTOP_CHECK": "1",
            "OMARCHY_UPDATE_SKIP_QML_TEST": "1",
            "XDG_RUNTIME_DIR": str(self.root),
        })

    def tearDown(self):
        self.temp.cleanup()

    def capture_patch(self):
        result = subprocess.run(["python3", str(SCRIPT), "--capture"], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def advance_upstream(self, file_name, replacement):
        subprocess.run(["git", "-C", str(self.remote), "symbolic-ref", "HEAD", "refs/heads/master"], check=True)
        subprocess.run(["git", "-C", str(self.upstream), "pull", "--ff-only", "origin", "master"], check=True, capture_output=True)
        path = self.upstream / file_name
        path.write_text(replacement)
        git(self.upstream, "add", file_name)
        git(self.upstream, "commit", "-m", "upstream update")
        git(self.upstream, "push", "origin", "master")

    def run_update(self):
        return subprocess.run(["python3", str(SCRIPT)], env=self.env, text=True, capture_output=True)

    def test_unrelated_upstream_update_keeps_local_adapter(self):
        self.capture_patch()
        self.advance_upstream("README.md", "upstream update\n")
        result = self.run_update()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(git(self.plugin, "rev-parse", "HEAD"), git(self.remote, "rev-parse", "refs/heads/master"))
        self.assertIn("rpc-adapter.py", (self.plugin / "Rpc.qml").read_text())
        self.assertEqual(git(self.plugin, "diff", "--name-only"), "Rpc.qml")

    def test_conflicting_upstream_update_rolls_back_and_restores_adapter(self):
        self.capture_patch()
        self.advance_upstream("Rpc.qml", 'readonly property string scriptPath: "new-upstream.qml"\n')
        result = self.run_update()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(git(self.plugin, "rev-parse", "HEAD"), self.old_head)
        self.assertIn("rpc-adapter.py", (self.plugin / "Rpc.qml").read_text())
        self.assertEqual(git(self.plugin, "diff", "--name-only"), "Rpc.qml")


if __name__ == "__main__":
    unittest.main()
