from __future__ import annotations

import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, nullcontext, redirect_stderr, redirect_stdout
from io import StringIO
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import synchronize_release_workflow_key as workflow_key  # noqa: E402


class ReleaseWorkflowKeyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name) / "repo"
        self.root.mkdir()
        (self.root / "VERSION").write_text("0.1.15\n", encoding="utf-8")
        self.key_parent = pathlib.Path(self.temp.name) / "keys"
        self.key_parent.mkdir(mode=0o700)
        self.private_key = self.key_parent / "release-key"
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "cloudx-release",
                "-f",
                str(self.private_key),
            ],
            check=True,
        )
        self.private_key.chmod(0o600)
        self.private_bytes = self.private_key.read_bytes()
        fields = self.private_key.with_suffix(".pub").read_text(encoding="utf-8").split()
        self.allowed = ("cloudx-release %s %s\n" % (fields[0], fields[1])).encode("ascii")
        for relative in workflow_key.trust.SIGNER_PATHS:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.allowed)
        workflow = self.root / ".github/workflows/release.yml"
        workflow.parent.mkdir(parents=True)
        workflow.write_text(
            "\n".join([
                "on:",
                "  workflow_dispatch:",
                "jobs:",
                "  release:",
                "    environment: release",
                "    steps:",
                "      - run: ./verify.sh",
                "      - run: echo ${{ secrets.CLOUDX_RELEASE_SIGNING_KEY }} >/dev/null",
                "      - run: python3 scripts/create_release.py",
                "      - run: python3 scripts/create_stable_index.py",
                "      - run: python3 scripts/verify_release.py",
                "      - run: python3 scripts/publish_release_refs.py",
                "        if: startsWith(github.ref, 'refs/tags/v')",
                "      - run: echo release",
                "        if: startsWith(github.ref, 'refs/tags/v')",
            ]) + "\n",
            encoding="utf-8",
        )
        self.head = "cdaaecfa1f1a4bcc5731ca33b11669c5addf3939"
        self.fingerprint = workflow_key.trust._fingerprint(self.allowed)
        self.refs = {"refs/heads/release/stable": "1" * 40}

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _completed(returncode: int = 0, stdout: bytes = b"") -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr=b"")

    def _base_patches(self):
        return [
            mock.patch.object(workflow_key, "_git_clean"),
            mock.patch.object(
                workflow_key,
                "_origin_repository",
                return_value=workflow_key.EXPECTED_REPOSITORY,
            ),
            mock.patch.object(workflow_key, "_head_commit", return_value=self.head),
            mock.patch.object(workflow_key, "_remote_head", return_value=self.head),
            mock.patch.object(workflow_key, "_safe_key_bytes", return_value=self.private_bytes),
            mock.patch.object(workflow_key, "_key_fingerprint", return_value=self.fingerprint),
            mock.patch.object(workflow_key, "_workflow_contract"),
            mock.patch.object(workflow_key, "_gh_auth"),
            mock.patch.object(
                workflow_key,
                "_environment_secret_present",
                side_effect=[True, True],
            ),
            mock.patch.object(workflow_key, "_release_refs", side_effect=[dict(self.refs), dict(self.refs)]),
            mock.patch.object(
                workflow_key,
                "_run_inventory",
                return_value=[{"databaseId": 41}],
            ),
            mock.patch.object(workflow_key, "_run", return_value=self._completed()),
            mock.patch.object(workflow_key, "_dispatch_run", return_value=42),
            mock.patch.object(workflow_key, "_wait_run"),
        ]

    def test_default_plan_is_offline_non_authorizing_and_path_free(self) -> None:
        output = StringIO()
        with mock.patch.object(workflow_key, "_safe_key_bytes") as key, mock.patch.object(
            workflow_key, "_gh_auth"
        ) as auth, mock.patch.object(workflow_key, "_run") as command, redirect_stdout(output):
            self.assertEqual(
                workflow_key.main(
                    ["--version", "0.1.15", "--private-key", "/private/secret/path"],
                    self.root,
                ),
                0,
            )
        key.assert_not_called()
        auth.assert_not_called()
        command.assert_not_called()
        document = json.loads(output.getvalue())
        example = json.loads(
            (ROOT / "shared/contracts/examples/release-workflow-key-plan.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(document, example)
        self.assertFalse(document["automaticAction"])
        self.assertFalse(any(document["authorization"].values()))
        self.assertNotIn("/private/secret/path", output.getvalue())

    def test_apply_requires_exact_confirmation_before_key_or_network_access(self) -> None:
        with mock.patch.object(workflow_key, "synchronize") as synchronize, mock.patch.object(
            workflow_key, "_run"
        ) as command, redirect_stderr(StringIO()):
            self.assertEqual(
                workflow_key.main([
                    "--version",
                    "0.1.15",
                    "--private-key",
                    str(self.private_key),
                    "--apply",
                    "--confirm",
                    "wrong",
                ], self.root),
                1,
            )
        synchronize.assert_not_called()
        command.assert_not_called()

    def test_private_key_must_be_external_private_and_non_symlink(self) -> None:
        accepted = workflow_key._safe_key_bytes(self.private_key, self.root)
        self.assertEqual(accepted, self.private_bytes)
        self.key_parent.chmod(0o755)
        with self.assertRaisesRegex(workflow_key.WorkflowKeyRejected, "0700"):
            workflow_key._safe_key_bytes(self.private_key, self.root)
        self.key_parent.chmod(0o700)
        alias = self.key_parent / "alias"
        alias.symlink_to(self.private_key)
        with self.assertRaisesRegex(workflow_key.WorkflowKeyRejected, "non-symlink"):
            workflow_key._safe_key_bytes(alias, self.root)
        inside_parent = self.root / "private"
        inside_parent.mkdir(mode=0o700)
        inside = inside_parent / "key"
        inside.write_bytes(self.private_bytes)
        inside.chmod(0o600)
        with self.assertRaisesRegex(workflow_key.WorkflowKeyRejected, "outside"):
            workflow_key._safe_key_bytes(inside, self.root)

    def test_private_key_must_match_all_committed_public_roots(self) -> None:
        self.assertEqual(
            workflow_key._key_fingerprint(self.private_key, self.root),
            self.fingerprint,
        )
        first = self.root / workflow_key.trust.SIGNER_PATHS[0]
        first.write_text("cloudx-release ssh-ed25519 AAAAinvalid\n", encoding="utf-8")
        with self.assertRaisesRegex(workflow_key.WorkflowKeyRejected, "public trust roots"):
            workflow_key._key_fingerprint(self.private_key, self.root)

    def test_workflow_contract_requires_dispatch_environment_and_tag_only_publication(self) -> None:
        workflow_key._workflow_contract(self.root)
        path = self.root / ".github/workflows/release.yml"
        path.write_text(path.read_text(encoding="utf-8").replace("workflow_dispatch:", "push:"), encoding="utf-8")
        with self.assertRaisesRegex(workflow_key.WorkflowKeyRejected, "incomplete"):
            workflow_key._workflow_contract(self.root)

    def test_remote_main_must_equal_clean_local_head_before_key_access(self) -> None:
        patches = self._base_patches()
        patches[3] = mock.patch.object(workflow_key, "_remote_head", return_value="0" * 40)
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            with self.assertRaisesRegex(workflow_key.WorkflowKeyRejected, "pushed"):
                workflow_key._synchronize(self.root, "0.1.15", self.private_key)
        entered[4].assert_not_called()
        entered[7].assert_not_called()
        entered[11].assert_not_called()

    def test_existing_release_tag_or_artifact_ref_blocks_secret_write(self) -> None:
        patches = self._base_patches()
        patches[9] = mock.patch.object(
            workflow_key,
            "_release_refs",
            return_value={"refs/tags/v0.1.15": "2" * 40},
        )
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            with self.assertRaisesRegex(workflow_key.WorkflowKeyRejected, "already exists"):
                workflow_key._synchronize(self.root, "0.1.15", self.private_key)
        entered[11].assert_not_called()
        entered[12].assert_not_called()

    def test_success_updates_only_environment_secret_and_accepts_nonpublishing_canary(self) -> None:
        patches = self._base_patches()
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            document = workflow_key._synchronize(self.root, "0.1.15", self.private_key)
        example = json.loads(
            (ROOT / "shared/contracts/examples/release-workflow-key.json").read_text(encoding="utf-8")
        )
        example["signerFingerprint"] = self.fingerprint
        self.assertEqual(document, example)
        secret_call = entered[11].call_args
        self.assertEqual(secret_call.args[0][:4], ["gh", "secret", "set", workflow_key.SECRET_NAME])
        self.assertIn("--env", secret_call.args[0])
        self.assertNotIn(self.private_bytes.decode("ascii"), " ".join(secret_call.args[0]))
        self.assertEqual(secret_call.kwargs["input_bytes"], self.private_bytes)
        entered[12].assert_called_once_with(workflow_key.EXPECTED_REPOSITORY, self.head, {41})
        entered[13].assert_called_once_with(workflow_key.EXPECTED_REPOSITORY, 42, self.head)

    def test_secret_update_failure_does_not_dispatch_and_says_do_not_tag(self) -> None:
        patches = self._base_patches()
        patches[11] = mock.patch.object(workflow_key, "_run", return_value=self._completed(returncode=1))
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            with self.assertRaisesRegex(workflow_key.WorkflowKeyRejected, "do not create"):
                workflow_key._synchronize(self.root, "0.1.15", self.private_key)
        entered[12].assert_not_called()

    def test_post_write_canary_failure_is_explicitly_non_rollbackable(self) -> None:
        patches = self._base_patches()
        patches[13] = mock.patch.object(
            workflow_key,
            "_wait_run",
            side_effect=workflow_key.WorkflowKeyRejected("canary failed"),
        )
        with ExitStack() as stack:
            entered = [stack.enter_context(patcher) for patcher in patches]
            with self.assertRaisesRegex(workflow_key.WorkflowKeyRejected, "updated.*do not create"):
                workflow_key._synchronize(self.root, "0.1.15", self.private_key)
        entered[11].assert_called_once()
        entered[12].assert_called_once()

    def test_ref_change_after_canary_is_rejected_without_claiming_success(self) -> None:
        patches = self._base_patches()
        patches[9] = mock.patch.object(
            workflow_key,
            "_release_refs",
            side_effect=[dict(self.refs), {**self.refs, "refs/tags/v0.1.15": "3" * 40}],
        )
        with ExitStack() as stack:
            for patcher in patches:
                stack.enter_context(patcher)
            with self.assertRaisesRegex(workflow_key.WorkflowKeyRejected, "updated.*do not create"):
                workflow_key._synchronize(self.root, "0.1.15", self.private_key)

    def test_transaction_lock_is_private(self) -> None:
        lock = pathlib.Path(self.temp.name) / "state/workflow-key.lock"
        with mock.patch.object(workflow_key, "DEFAULT_LOCK", lock):
            with workflow_key._transaction_lock():
                self.assertEqual(stat.S_IMODE(lock.parent.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)

    def test_cli_receipt_contains_no_private_path_or_key_material(self) -> None:
        receipt = json.loads(
            (ROOT / "shared/contracts/examples/release-workflow-key.json").read_text(encoding="utf-8")
        )
        output = StringIO()
        with mock.patch.object(workflow_key, "_transaction_lock", return_value=nullcontext()), mock.patch.object(
            workflow_key,
            "_synchronize",
            return_value=receipt,
        ), redirect_stdout(output):
            self.assertEqual(workflow_key.main([
                "--version",
                "0.1.15",
                "--private-key",
                str(self.private_key),
                "--apply",
                "--confirm",
                workflow_key.confirmation("0.1.15"),
            ], self.root), 0)
        serialized = output.getvalue()
        self.assertNotIn(str(self.private_key), serialized)
        self.assertNotIn(self.private_bytes.decode("ascii"), serialized)


if __name__ == "__main__":
    unittest.main()
