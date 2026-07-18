from __future__ import annotations

import hashlib
import http.server
import json
import os
import pathlib
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
RECOVERY = ROOT / "scripts/recover_local_cpa_policy.py"


class HealthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            return
        raw = b'{"status":"ok"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: object) -> None:
        return


@unittest.skipUnless(sys.platform == "darwin", "launchd recovery rehearsal requires macOS")
class LocalCpaPolicyRecoveryRehearsalTests(unittest.TestCase):
    def test_offline_service_recovers_through_the_exact_manual_command(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            job = root / "test-job"
            job.mkdir(mode=0o700)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state = root / "launchd.loaded"
            baseline = root / "cli-proxy-api"
            baseline.write_bytes(b"baseline-binary")
            baseline.chmod(0o700)
            launcher = root / "com.codexx.cliproxyapi.plist"
            codex_home = root / "codex-home"
            codex_home.mkdir()
            codex = fake_bin / "codex"
            codex.write_text("#!/bin/sh\necho LOCAL_CPA_POLICY_COMMUNICATION_OK\n", encoding="utf-8")
            codex.chmod(0o700)
            launchctl = fake_bin / "launchctl"
            launchctl.write_text(
                "#!/bin/sh\n"
                "case \"$1\" in\n"
                "  print)\n"
                "    test -f \"$FAKE_LAUNCHD_STATE\" || exit 113\n"
                "    echo \"program = $FAKE_BASELINE\"\n"
                "    echo \"pid = 12345\"\n"
                "    ;;\n"
                "  bootout) rm -f \"$FAKE_LAUNCHD_STATE\" ;;\n"
                "  bootstrap) : > \"$FAKE_LAUNCHD_STATE\" ;;\n"
                "  *) exit 2 ;;\n"
                "esac\n",
                encoding="utf-8",
            )
            launchctl.chmod(0o700)
            recovery = job / "recover_local_cpa_policy.py"
            shutil.copyfile(RECOVERY, recovery)
            recovery.chmod(0o600)
            with http.server.ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler) as server:
                port = int(server.server_address[1])
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                config = root / "config.yaml"
                config.write_text("host: 127.0.0.1\nport: %d\n" % port, encoding="utf-8")
                snapshot_raw = plistlib.dumps({
                    "Label": "com.codexx.cliproxyapi",
                    "ProgramArguments": [str(baseline), "--config", str(config)],
                    "RunAtLoad": True,
                })
                snapshot = job / "launcher.before"
                snapshot.write_bytes(snapshot_raw)
                snapshot.chmod(0o600)
                launcher.write_bytes(plistlib.dumps({
                    "Label": "com.codexx.cliproxyapi",
                    "ProgramArguments": [str(root / "candidate"), "--config", str(config)],
                }))
                launcher_digest = hashlib.sha256(snapshot_raw).hexdigest()
                confirmation = "RESTORE LOCAL CPA BASELINE test-job %s" % launcher_digest[:12]
                document = {
                    "schema": "cloudx.local-cpa-policy-activation-job.v2",
                    "jobId": job.name,
                    "baselineSha256": hashlib.sha256(baseline.read_bytes()).hexdigest(),
                    "launcherSnapshotSha256": launcher_digest,
                    "recoveryToolSha256": hashlib.sha256(recovery.read_bytes()).hexdigest(),
                    "baselineBinary": str(baseline),
                    "launcherPath": str(launcher),
                    "launcherMode": stat.S_IMODE(launcher.stat().st_mode),
                    "launcherUid": os.geteuid(),
                    "launcherGid": os.getegid(),
                    "serviceLabel": "com.codexx.cliproxyapi",
                    "configPath": str(config),
                    "codexBinary": str(codex),
                    "communicationCodexHome": str(codex_home),
                    "recoveryConfirmation": confirmation,
                    "quiescenceSamples": 3,
                    "quiescenceIntervalSeconds": 0,
                }
                job_json = job / "job.json"
                job_json.write_text(json.dumps(document), encoding="utf-8")
                job_json.chmod(0o600)
                environment = dict(os.environ)
                environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
                environment["FAKE_LAUNCHD_STATE"] = str(state)
                environment["FAKE_BASELINE"] = str(baseline)
                completed = subprocess.run(
                    [
                        sys.executable, str(recovery), "--apply", "--job", str(job),
                        "--confirm", confirmation,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                    check=False,
                    env=environment,
                )
                server.shutdown()
                thread.join(timeout=5)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertEqual(result["status"], "recovered")
            self.assertEqual(result["communicationCanary"], "passed")
            self.assertTrue(state.is_file())
            self.assertEqual(launcher.read_bytes(), snapshot_raw)
            receipt = json.loads((job / "recovery-receipt.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "recovered")


if __name__ == "__main__":
    unittest.main()
