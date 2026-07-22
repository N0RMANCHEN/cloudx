# Local policy9 Agent Identity staging

Date: 2026-07-22

## Exact candidate

- version: `7.0.2-codexx-fast-service-tier-cloudx-policy.9-agent-identity`
- SHA-256: `174a46d58a95f56104d0bb3722c4fb5e7dffc125f2f525505d96f556291aa761`
- size: `41518146`
- capability: `codex-agent-identity-v1`
- signed Cloudx prerequisite: `0.1.27`

The candidate, exact installer, and deployment contract were copied from immutable source `7c30165395fef6c53aeb95965e1a7cb2d51b005a` into a private mode-`0700` operator bundle. The exact stage confirmation returned `staged`; repetition returned `already-staged`. The staged manifest binds the version, digest, size, target, and capability.

## Process-neutral acceptance

The active launcher remained SHA-256 `80535ade89c6f0de399a6dbab9f69280c933b8fe3c5cbba829f96c86d6325970`. The original active binary remained SHA-256 `cf9641b3e50ae486aec1698dec88f735589680f9ae98558c29cde184daac3a96`, PID `61859`, listening on loopback port `8317`. No capability sidecar was written and no process or service restarted.

## Deferred activation and watcher

Activation job `20260722T144535Z-564eaabf` copied the installer, contract, original launcher, independent recovery tool, and manual recovery command before detaching. Its separately confirmed watcher follower binds the same job, candidate digest/version, signed `0.1.27`, accepted communication receipt, and no-restart watcher contract.

After the 180-second deferral, the policy worker entered `quiescence-wait`. The direct recovery check reports `busy` with two established socket rows, representing the two endpoints of the same persistent `ClashX Pro` to local CPA TCP connection. No process may be terminated to manufacture zero samples. The policy and watcher roadmap items remain incomplete until their private receipts are accepted and independently verified.
