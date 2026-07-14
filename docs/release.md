# Release And Synchronization

Cloudx uses one product version and two independently built artifacts.

Each release contains:

- `cloudx-local-<version>.pyz`
- `cloudx-cloud-<version>.pyz`
- `manifest.json`
- `manifest.json.sig`
- `allowed_signers`
- an offline bundle containing the same immutable files

The manifest records the source commit, artifact hashes and sizes, protocol range, contract versions, minimum compatible endpoint, and whether activation may require a service restart.

Staging also executes the artifact's offline `cloudx.self-check.v1` response and requires its component, embedded product version, and protocol range to match the signed manifest. A correctly signed manifest cannot relabel an older zipapp or claim unsupported protocol compatibility.

`release/stable` contains a small signed index. Automatic checks may fetch and verify that index and record that an update exists. They may not stage, activate, change a symlink, or restart a service.

The tag-triggered release workflow verifies that `v<VERSION>` matches the source, proves the signed manifest was built from the workflow commit, and exercises the signed stable index with the built local artifact before publishing. Its temporary publication repositories copy only the checkout's ephemeral HTTP authorization header into Git configuration; authentication never becomes branch content. Artifact refs are immutable, while the signed `release/stable` ref is intentionally replaceable.

An operator stages and activates a release. The compatible cloud endpoint is activated before the local endpoint. A failed canary restores both previous symlinks. Production hosts never run `git pull` to update deployed code.

Phi has its own repository, release key, updater, and release lifecycle. Protocol compatibility, not shared deployment code, coordinates the products.
