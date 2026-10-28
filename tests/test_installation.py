"""Instalação, troca de versão e falhas, usando diretórios isolados e sem sudo/HID."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hidctl import installation as installer
from hidctl.gui.app import main


class InstallationCase(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="hidctl-install-test-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / "data/hidctl"
        self.root.mkdir(parents=True)
        self.command = self.base / "bin/hidctl-gui"
        self.desktop = self.base / "apps/hidctl.desktop"
        self.files = {self.command: ("launcher\n", 0o755), self.desktop: ("desktop\n", 0o644)}
        self.addCleanup(patch.stopall)
        patch.object(installer, "integration_files", return_value=self.files).start()
        patch("hidctl._paths.state_dir", return_value=self.base / "state").start()
        patch.object(installer, "configure_user_path", return_value=self.base / ".zshrc").start()

    def release(self, name):
        path = self.root / "releases" / name
        path.mkdir(parents=True)
        return path

    def installed(self):
        old = self.release("old")
        installer.activate(self.root, old)
        return old

    def test_install_then_update_switches_version_and_keeps_previous(self):
        old = self.installed()
        new = self.release("new")
        installer.activate(self.root, new)
        self.assertEqual((self.root / "current").resolve(), new)
        self.assertEqual((self.root / "previous").resolve(), old)
        self.assertEqual(self.command.read_text(), "launcher\n")
        self.assertEqual(self.command.stat().st_mode & 0o777, 0o755)
        self.assertEqual(json.loads((self.root / "install.json").read_text())["format"], 1)

    def test_failed_activation_restores_launcher_and_current_version(self):
        old = self.installed()
        new = self.release("new")
        self.command.write_text("previous launcher\n")
        real = installer.point_to

        def fail_current(root, name, target):
            if name == "current":
                raise OSError("disk error")
            real(root, name, target)

        with patch.object(installer, "point_to", side_effect=fail_current):
            with self.assertRaisesRegex(OSError, "disk error"):
                installer.activate(self.root, new)
        self.assertEqual((self.root / "current").resolve(), old)
        self.assertEqual(self.command.read_text(), "previous launcher\n")
        self.assertEqual(self.desktop.read_text(), "desktop\n")

    def test_failed_download_keeps_working_installation_and_user_data(self):
        old = self.installed()
        prefs = self.base / "state/profile-names.json"
        prefs.parent.mkdir()
        prefs.write_text('{"0":"Trabalho"}')
        with patch.object(installer, "build_release", side_effect=OSError("network")):
            with self.assertRaisesRegex(OSError, "network"):
                installer.deploy(self.root, None)
        self.assertEqual((self.root / "current").resolve(), old)
        self.assertEqual(prefs.read_text(), '{"0":"Trabalho"}')
        self.assertEqual(self.command.read_text(), "launcher\n")

    def test_failed_candidate_validation_removes_only_failed_release(self):
        old = self.installed()
        source = self.base / "checkout"
        for name in ("hidctl", "packaging"):
            (source / name).mkdir(parents=True)
        for name in ("pyproject.toml", "README.md", "LICENSE"):
            (source / name).write_text("test")
        with (
            patch.object(installer, "run"),
            patch.object(
                installer,
                "validate_candidate",
                side_effect=installer.InstallError("invalid candidate"),
            ),
        ):
            with self.assertRaisesRegex(installer.InstallError, "invalid candidate"):
                installer.build_release(self.root, source)
        self.assertEqual(sorted(p.name for p in (self.root / "releases").iterdir()), ["old"])
        self.assertEqual((self.root / "current").resolve(), old)

    def test_udev_denied_preserves_active_version(self):
        old = self.installed()
        new = self.release("new")
        with (
            patch.object(installer, "build_release", return_value=new),
            patch.object(
                installer, "configure_udev", side_effect=subprocess.CalledProcessError(1, ["sudo"])
            ),
        ):
            with self.assertRaises(subprocess.CalledProcessError):
                installer.deploy(self.root, None)
        self.assertEqual((self.root / "current").resolve(), old)
        self.assertEqual([p.name for p in (self.root / "releases").iterdir()], ["old"])

    def test_open_application_blocks_update_before_build(self):
        old = self.installed()
        with installer.lock(self.root / "runtime.lock", shared=True):
            with self.assertRaisesRegex(installer.InstallError, "Feche"):
                installer.deploy(self.root, None)
        self.assertEqual((self.root / "current").resolve(), old)

    def test_update_fetches_main_and_activates_validated_candidate(self):
        old = self.installed()
        remote = self.base / "remote"
        subprocess.run(["git", "init", "-b", "main", str(remote)], check=True, capture_output=True)
        (remote / "release.txt").write_text("main content")
        subprocess.run(["git", "-C", str(remote), "add", "."], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(remote),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-m",
                "fixture",
            ],
            check=True,
            capture_output=True,
        )
        expected = subprocess.check_output(
            ["git", "-C", str(remote), "rev-parse", "HEAD"], text=True
        ).strip()
        original_run = installer.run

        def commands(args, **kwargs):
            if str(args[0]) == "git":
                return original_run(args, **kwargs)
            # Package installation is a separate boundary; this test exercises Git and activation.
            return subprocess.CompletedProcess(args, 0)

        def validate(release):
            self.assertEqual((release / "source/release.txt").read_text(), "main content")
            self.assertEqual((release / "revision").read_text(), expected + "\n")

        with (
            patch.object(installer, "REPOSITORY", str(remote)),
            patch.object(installer, "run", side_effect=commands),
            patch.object(installer, "validate_candidate", side_effect=validate),
            patch.object(installer, "configure_udev"),
        ):
            installer.deploy(self.root, None)
        self.assertEqual((self.root / "current/source/release.txt").read_text(), "main content")
        self.assertEqual((self.root / "previous").resolve(), old)
        self.assertEqual((remote / "release.txt").read_text(), "main content")

    def test_inflight_device_operation_blocks_update(self):
        old = self.installed()
        with installer.lock(self.base / "state/device.lock"):
            with self.assertRaisesRegex(installer.InstallError, "Feche"):
                installer.deploy(self.root, None)
        self.assertEqual((self.root / "current").resolve(), old)

    def test_uninstall_preserves_preferences_and_modified_external_file(self):
        self.installed()
        prefs = self.base / "state/profile-names.json"
        prefs.parent.mkdir()
        prefs.write_text("my preferences")
        self.desktop.write_text("custom user desktop")
        with patch.object(installer, "confirm", return_value=True):
            installer.uninstall(self.root)
        self.assertEqual(prefs.read_text(), "my preferences")
        self.assertEqual(self.desktop.read_text(), "custom user desktop")
        with self.assertRaises(FileNotFoundError):
            self.command.read_text()

    def test_complete_uninstall_removes_app_data_but_preserves_unrelated_data(self):
        self.installed()
        state = self.base / "hidctl"
        (state / "backups").mkdir(parents=True)
        (state / "backups/original.json").write_text("original device settings")
        (state / "recent-colors.json").write_text('["#ff0000"]')
        unrelated = self.base / "another-app.json"
        unrelated.write_text("keep this")
        with (
            patch("hidctl._paths.state_dir", return_value=state),
            patch.object(installer, "confirm", return_value=True),
        ):
            installer.uninstall(self.root, purge=True)
        self.assertEqual(unrelated.read_text(), "keep this")
        self.assertFalse(state.exists())
        self.assertFalse(self.root.exists())

    def test_cancel_complete_uninstall_preserves_app_and_backups(self):
        old = self.installed()
        state = self.base / "hidctl"
        state.mkdir()
        backup = state / "backup.json"
        backup.write_text("original settings")
        with (
            patch("hidctl._paths.state_dir", return_value=state),
            patch.object(installer, "confirm", return_value=False),
        ):
            installer.uninstall(self.root, purge=True)
        self.assertEqual((self.root / "current").resolve(), old)
        self.assertEqual(backup.read_text(), "original settings")

    def test_cli_routes_complete_uninstall_without_opening_gui(self):
        with patch.object(installer, "maintenance", return_value=0) as maintenance:
            self.assertEqual(main(["--uninstall", "A"]), 0)
        maintenance.assert_called_once_with("uninstall", purge=True)


class ShellPathCase(unittest.TestCase):
    def test_zsh_configuration_preserves_settings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            rc = home / ".zshrc"
            rc.write_text("# existing configuration\nexport EDITOR=vim\n")
            with (
                patch.object(Path, "home", return_value=home),
                patch.dict(installer.os.environ, {"SHELL": "/bin/zsh", "ZDOTDIR": str(home)}),
            ):
                installer.configure_user_path()
                first = rc.read_text()
                installer.configure_user_path()
            self.assertEqual(rc.read_text(), first)
            self.assertEqual(
                (home / ".zshrc.hidctl-backup").read_text(),
                "# existing configuration\nexport EDITOR=vim\n",
            )
            self.assertEqual(first.count("# >>> Peripheral Control: PATH >>>"), 1)
            self.assertIn('export PATH="$HOME/.local/bin:$PATH"', first)
            self.assertTrue(first.startswith("# existing configuration\nexport EDITOR=vim\n"))

    def test_modified_path_block_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            rc = home / ".bashrc"
            original = "# >>> Peripheral Control: PATH >>>\ncustom code\n"
            rc.write_text(original)
            with (
                patch.object(Path, "home", return_value=home),
                patch.dict(installer.os.environ, {"SHELL": "/bin/bash"}),
            ):
                with self.assertRaisesRegex(installer.InstallError, "modificado"):
                    installer.configure_user_path()
            self.assertEqual(rc.read_text(), original)


class PlatformCase(unittest.TestCase):
    def test_unknown_distribution_defaults_to_cancel(self):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="ID=ubuntu\n"),
            patch("builtins.input", return_value=""),
        ):
            with self.assertRaisesRegex(installer.InstallError, "cancelada"):
                installer.check_platform()

    def test_unknown_distribution_can_continue_explicitly(self):
        with (
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value="ID=ubuntu\n"),
            patch("builtins.input", return_value="s"),
        ):
            self.assertEqual(installer.check_platform(), False)

    def test_other_distribution_never_uses_pacman(self):
        with (
            patch.object(installer.shutil, "which", return_value=None),
            patch.object(installer, "run") as run,
        ):
            with self.assertRaisesRegex(installer.InstallError, "pré-requisitos"):
                installer.prerequisites(False)
        self.assertEqual(len(run.call_args_list), 1)
        self.assertEqual(run.call_args.args[0][1:], ["-m", "venv", "--help"])

    def test_update_from_development_environment_is_refused_without_gui(self):
        with (
            patch.object(installer, "managed_root", return_value=None),
            patch.object(installer.os, "geteuid", return_value=1000),
            patch("hidctl.gui.app.run_gui") as gui,
        ):
            self.assertEqual(main(["--update"]), 1)
        gui.assert_not_called()

    def test_desktop_exec_quotes_paths_with_spaces_and_field_codes(self):
        self.assertEqual(
            installer.desktop_quote(Path("/tmp/my app/100%/run")), '"/tmp/my app/100%%/run"'
        )
        self.assertEqual(
            installer.launcher(Path("/tmp/my app")),
            "#!/bin/sh\nexec '/tmp/my app/current/venv/bin/python' -I -m hidctl.gui \"$@\"\n",
        )
