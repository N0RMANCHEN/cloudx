from __future__ import annotations

import hashlib
import json
import os
import pathlib
import stat
import sys
import tempfile
import unittest
from contextlib import ExitStack, nullcontext, redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import remove_legacy_local_package as removal  # noqa: E402


class LegacyLocalRemovalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir(mode=0o700)
        self.artifact = self.root / "cloudx-local.pyz"
        self.artifact.write_bytes(b"artifact")
        self.selectors = {"current": "0.1.15", "previous": "0.1.14"}
        self.shell = {
            "zshrcSha256": "1" * 64,
            "zshrcMode": 0o600,
            "entrypoints": {
                "codexx": "../lib/cloudx/current/cloudx-local.pyz",
                "cloud": "../lib/cloudx/current/cloudx-local.pyz",
                "cloudx-update": "../lib/cloudx/current/cloudx-local.pyz",
            },
        }
        self.cpa = {"pid": 17165, "identity": "17165 external-cli-proxy-api"}
        self.runtime = [
            removal.FileRecord(relative="__init__.py", size=8, mode=0o600, sha256="2" * 64)
        ]
        self.launcher = b"#!/usr/bin/env python3\n"
        self.bundle = self.root / "legacy-backups/20260715T050707Z"
        self.quarantine = self.root / "legacy-removal-backups/20260717T120000Z"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _base_patches(self):
        moved = [(self.home / ".local/bin/codexx.py", self.quarantine / "live/legacyLauncher")]
        return [
            mock.patch.object(removal, "user_home", return_value=self.home),
            mock.patch.object(removal, "_transaction_lock", return_value=nullcontext()),
            mock.patch.object(
                removal,
                "_active_release",
                return_value=(self.artifact, dict(self.selectors)),
            ),
            mock.patch.object(removal, "_shell_snapshot", return_value=dict(self.shell)),
            mock.patch.object(removal, "_process_inventory", return_value=([], dict(self.cpa))),
            mock.patch.object(removal, "_port_open", side_effect=lambda port: port == 8317),
            mock.patch.object(removal, "_tree_records", return_value=list(self.runtime)),
            mock.patch.object(
                removal,
                "_safe_file",
                return_value=(self.launcher, SimpleNamespace(st_mode=stat.S_IFREG | 0o700)),
            ),
            mock.patch.object(removal, "_recovery_bundle", return_value=(self.bundle, {"files": []})),
            mock.patch.object(removal, "_verify_recovery_copy"),
            mock.patch.object(removal, "_native_import_dry_run"),
            mock.patch.object(removal, "_fresh_shell"),
            mock.patch.object(
                removal,
                "_prepare_quarantine",
                return_value=("20260717T120000Z", self.quarantine),
            ),
            mock.patch.object(removal, "_move_targets", return_value=moved),
            mock.patch.object(removal, "_restore_targets"),
        ]

    @staticmethod
    def _apply_arguments() -> list[str]:
        return [
            "--apply",
            "--confirm",
            removal.CONFIRMATION,
            "--release-version",
            "0.1.15",
        ]

    def test_default_plan_is_offline_and_non_authorizing(self) -> None:
        output = StringIO()
        with mock.patch.object(removal, "user_home") as home, mock.patch.object(
            removal, "_transaction_lock"
        ) as lock, mock.patch.object(removal, "_process_inventory") as processes, redirect_stdout(output):
            self.assertEqual(removal.main(["--release-version", "0.1.15"]), 0)
        home.assert_not_called()
        lock.assert_not_called()
        processes.assert_not_called()
        document = json.loads(output.getvalue())
        example = json.loads(
            (ROOT / "shared/contracts/examples/legacy-local-removal-plan.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(document, example)
        self.assertEqual(document["status"], "confirmation-required")
        self.assertEqual(document["confirmation"], removal.CONFIRMATION)
        self.assertFalse(document["automaticAction"])
        self.assertFalse(any(document["authorization"].values()))
        self.assertEqual(document["targets"], ["legacyRuntime", "legacyLauncher", "recoveryEntrypoint"])

    def test_apply_requires_exact_confirmation_before_home_or_lock(self) -> None:
        with mock.patch.object(removal, "user_home") as home, mock.patch.object(
            removal, "_transaction_lock"
        ) as lock:
            with self.assertRaisesRegex(RuntimeError, "confirmation"):
                removal.main(["--apply", "--confirm", "wrong", "--release-version", "0.1.15"])
        home.assert_not_called()
        lock.assert_not_called()

    def test_native_import_dry_run_uses_current_codexx_artifact_entrypoint(self) -> None:
        result = {
            "schema": "cloudx.local-cpa-import.v1",
            "status": "preview",
            "dryRun": True,
            "adapter": "cloudx_native_compatibility",
            "errors": [],
            "counts": {"parsed": 1},
            "externalService": {"managed": False, "restarted": False},
        }
        completed = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(result),
            stderr="",
        )
        with mock.patch.object(removal.subprocess, "run", return_value=completed) as run:
            removal._native_import_dry_run(self.artifact)
        command = run.call_args.args[0]
        self.assertEqual(
            command[:4],
            [sys.executable, str(self.artifact), "codexx", "import"],
        )
        self.assertEqual(command[-2:], ["--dry-run", "--json"])

    def test_fresh_shell_accepts_external_homebrew_git_and_cleared_exit_state(self) -> None:
        completed = SimpleNamespace(returncode=0, stdout="accepted\n", stderr="")

        def resolved(name: str, *, path: str) -> str:
            del path
            return {
                "codex": "/opt/homebrew/bin/codex",
                "git": "/opt/homebrew/bin/git",
            }[name]

        with mock.patch.object(removal.shutil, "which", side_effect=resolved), mock.patch.object(
            removal.subprocess,
            "run",
            return_value=completed,
        ) as run:
            removal._fresh_shell(self.home)
        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        script = command[-1]
        self.assertEqual(environment["EXPECTED_CODEX"], "/opt/homebrew/bin/codex")
        self.assertEqual(environment["EXPECTED_GIT"], "/opt/homebrew/bin/git")
        self.assertIn('"$EXPECTED_GIT"', script)
        self.assertIn('[[ -z "${CODEXX_ACTIVE_ACCOUNT:-}" ]]', script)
        self.assertIn('[[ -z "${CODEX_HOME:-}" ]]', script)

    def test_apply_rejects_when_requested_release_is_not_active(self) -> None:
        with mock.patch.object(removal, "user_home", return_value=self.home), mock.patch.object(
            removal, "_transaction_lock", return_value=nullcontext()
        ), mock.patch.object(
            removal,
            "_active_release",
            side_effect=RuntimeError("the requested native-import release is not active"),
        ), mock.patch.object(removal, "_shell_snapshot") as shell:
            with self.assertRaisesRegex(RuntimeError, "not active"):
                removal.main(self._apply_arguments())
        shell.assert_not_called()

    def test_success_quarantines_only_three_legacy_targets(self) -> None:
        output = StringIO()
        patches = self._base_patches()
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            stack.enter_context(redirect_stdout(output))
            self.assertEqual(removal.main(self._apply_arguments()), 0)
        document = json.loads(output.getvalue())
        example = json.loads(
            (ROOT / "shared/contracts/examples/legacy-local-removal.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(document, example)
        self.assertEqual(document["status"], "quarantined")
        self.assertEqual(document["backupId"], "20260717T120000Z")
        self.assertEqual(document["targetsQuarantined"], 3)
        self.assertTrue(document["cloudxEntrypointsUnchanged"])
        self.assertTrue(document["externalLocalCpaUnchanged"])
        self.assertTrue(document["privateRecoveryBundleRetained"])
        self.assertFalse(document["legacyRuntimeLive"])
        self.assertFalse(document["legacyLauncherLive"])
        self.assertFalse(document["recoveryEntrypointLive"])
        self.assertFalse(document["processTerminated"])
        self.assertFalse(document["serviceRestarted"])
        self.assertTrue(document["quarantineRetained"])
        entered[13].assert_called_once()
        entered[14].assert_not_called()

    def test_post_move_acceptance_failure_restores_all_live_paths(self) -> None:
        self.quarantine.mkdir(parents=True)
        patches = self._base_patches()
        patches[11] = mock.patch.object(
            removal,
            "_fresh_shell",
            side_effect=[None, RuntimeError("post-move shell failure")],
        )
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            with self.assertRaisesRegex(RuntimeError, "live paths were restored"):
                removal.main(self._apply_arguments())
        entered[14].assert_called_once_with(entered[13].return_value)
        self.assertFalse(self.quarantine.exists())

    def test_external_cpa_identity_change_restores_live_paths(self) -> None:
        self.quarantine.mkdir(parents=True)
        patches = self._base_patches()
        patches[4] = mock.patch.object(
            removal,
            "_process_inventory",
            side_effect=[
                ([], dict(self.cpa)),
                ([], {"pid": 99999, "identity": "99999 changed"}),
                ([], dict(self.cpa)),
            ],
        )
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            with self.assertRaisesRegex(RuntimeError, "live paths were restored"):
                removal.main(self._apply_arguments())
        entered[14].assert_called_once()

    def test_legacy_process_or_listener_blocks_before_inventory(self) -> None:
        for legacy, ports, message in (
            (["123 legacy"], lambda port: port == 8317, "processes"),
            ([], lambda port: True, "18317"),
        ):
            with self.subTest(message=message):
                patches = self._base_patches()
                patches[4] = mock.patch.object(
                    removal,
                    "_process_inventory",
                    return_value=(legacy, dict(self.cpa)),
                )
                patches[5] = mock.patch.object(removal, "_port_open", side_effect=ports)
                with ExitStack() as stack:
                    entered = [stack.enter_context(patcher) for patcher in patches]
                    with self.assertRaisesRegex(RuntimeError, message):
                        removal.main(self._apply_arguments())
                entered[6].assert_not_called()
                entered[13].assert_not_called()

    def test_partial_move_is_restored_in_place(self) -> None:
        runtime = self.home / ".local/bin/codexx_app"
        runtime.mkdir(parents=True)
        (runtime / "module.py").write_text("pass\n", encoding="utf-8")
        launcher = self.home / ".local/bin/codexx.py"
        launcher.write_text("launcher\n", encoding="utf-8")
        recovery = self.home / ".local/bin/codexx-legacy"
        recovery.symlink_to(launcher)
        quarantine = self.root / "quarantine"
        quarantine.mkdir()
        real_replace = os.replace

        def fail_second(source, target):
            if pathlib.Path(source) == launcher:
                raise OSError("injected move failure")
            return real_replace(source, target)

        with mock.patch.object(removal.os, "replace", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "injected"):
                removal._move_targets(self.home, quarantine)
        self.assertTrue(runtime.is_dir())
        self.assertTrue(launcher.is_file())
        self.assertTrue(recovery.is_symlink())

    def test_recovery_entrypoint_requires_exact_private_bundle_shape(self) -> None:
        backup_id = "20260715T050707Z"
        bundle = self.home / ".local/state/cloudx/legacy-backups" / backup_id
        target = bundle / "home/.local/bin/codexx"
        target.parent.mkdir(parents=True)
        (self.home / ".local/state/cloudx/legacy-backups").chmod(0o755)
        bundle.chmod(0o700)
        target.write_text("launcher\n", encoding="utf-8")
        manifest = bundle / "manifest.json"
        manifest.write_text(json.dumps({
            "schema": "cloudx.legacy-local-backup.v1",
            "home": str(self.home),
            "files": [],
        }), encoding="utf-8")
        manifest.chmod(0o600)
        entrypoint = self.home / ".local/bin/codexx-legacy"
        entrypoint.parent.mkdir(parents=True, exist_ok=True)
        entrypoint.symlink_to(target)
        accepted_bundle, document = removal._recovery_bundle(self.home)
        self.assertEqual(accepted_bundle, bundle.resolve())
        self.assertEqual(document["schema"], "cloudx.legacy-local-backup.v1")

        entrypoint.unlink()
        wrong = bundle / "unexpected/bin/codexx"
        wrong.parent.mkdir(parents=True)
        wrong.write_text("launcher\n", encoding="utf-8")
        entrypoint.symlink_to(wrong)
        with self.assertRaisesRegex(RuntimeError, "unexpected launcher"):
            removal._recovery_bundle(self.home)

    def test_runtime_inventory_rejects_symlinks_and_oversized_files(self) -> None:
        runtime = self.root / "runtime"
        runtime.mkdir()
        source = runtime / "module.py"
        source.write_text("pass\n", encoding="utf-8")
        records = removal._tree_records(runtime)
        self.assertEqual([record.relative for record in records], ["module.py"])
        alias = runtime / "alias.py"
        alias.symlink_to(source)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            removal._tree_records(runtime)
        alias.unlink()
        with mock.patch.object(removal, "MAX_FILE_BYTES", 1):
            with self.assertRaisesRegex(RuntimeError, "size limit"):
                removal._tree_records(runtime)

    def test_recovery_manifest_must_match_live_launcher_and_runtime(self) -> None:
        launcher_digest = hashlib.sha256(self.launcher).hexdigest()
        runtime_source = str(self.home / ".local/bin/codexx_app/__init__.py")
        launcher_source = str(self.home / ".local/bin/codexx.py")
        manifest = {
            "files": [
                {"source": runtime_source, "sha256": self.runtime[0].sha256},
                {"source": launcher_source, "sha256": launcher_digest},
            ]
        }
        removal._verify_recovery_copy(self.home, self.runtime, launcher_digest, manifest)
        manifest["files"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(RuntimeError, "runtime does not match"):
            removal._verify_recovery_copy(self.home, self.runtime, launcher_digest, manifest)

    def test_transaction_lock_is_private_and_rejects_broad_state_directory(self) -> None:
        with removal._transaction_lock(self.home):
            lock = self.home / ".local/state/cloudx/legacy-local-removal.lock"
            self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)
        state = self.home / ".local/state/cloudx"
        state.chmod(0o755)
        with self.assertRaisesRegex(RuntimeError, "permissions"):
            with removal._transaction_lock(self.home):
                pass


if __name__ == "__main__":
    unittest.main()
