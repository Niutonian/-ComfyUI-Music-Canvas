# Security review — 2026-11-05

Original Music Canvas code is [MIT-licensed](LICENSE). Models, ComfyUI and external nodes retain their own terms. The publication allowlist excludes full source songs, bulk renders, weights, runtimes, credentials, local configuration, caches and historical scripts. Its only media exceptions are the two 15-second showcase MP4s and their GIF previews in `docs/media/`, verified by explicit file hashes and sizes. Their embedded workflow/prompt metadata was removed. The working-tree and staged-content audits are separate checks.

## Implemented safeguards

- The default Beat This checkpoint is SHA-256 verified before deserialization. Downloads are verified before installation, and mismatching existing files are rejected. Custom Beat This checkpoints require Torch 2.10.0 or later.
- MOSS loads safetensors explicitly, with checkpoint Python auto-loading disabled (`trust_remote_code=False`). Its unused custom-generation loader is replaced with a rejection before it can fetch Python. Inference network connections are disabled. The separately imported MOSS implementation is still trusted executable upstream source, pinned by commit; this is not a sandbox.
- Setup builds a separate candidate environment, checks dependencies and runs offline import/tiny-model checks, then updates runtime configuration only on success. It never upgrades ComfyUI's Python or overwrites the old environment. A failed candidate leaves the old selection intact; a previous config is retained for rollback.
- Ollama endpoints are restricted to HTTP loopback. Lyrics are treated as prompt evidence, not shell commands. Shared examples disable transcription/lyric approval. This does not eliminate every possible prompt injection into a creative model.

## Dependency update status

The candidate installer targets **Torch/torchaudio 2.10.0**, **setuptools 84.2.1** and **Transformers 4.57.6**, with other direct pins in `audio_requirements.txt`. Torch 2.10.0 addresses the reviewed [PyTorch checkpoint advisory](https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p); the setuptools target is above the [reviewed fixed version](https://github.com/pypa/setuptools/security/advisories/GHSA-5rjg-fvgr-3xxf). These targets are not a claim that every possible dependency advisory is resolved.

Transformers stays on the MOSS-compatible 4.57 series. The [custom-generation advisory](https://github.com/advisories/GHSA-x9r9-c232-4q39) still includes that version range. The worker blocks the affected custom loader instead of describing the upstream library as patched. This mitigation is scoped to Music Canvas's worker.

**The patched candidate could not be installed on the review machine:** package connections were refused, and a network-enabled package command was rejected because permission escalation is disabled. The existing isolated environment therefore still contains Torch 2.9.1, setuptools 78.1.0 and Transformers 4.57.1. Its tiny-model compatibility check passed but explicitly reports that its dependency versions are unpatched. It has not been relabeled as upgraded. Existing installed copies of this node pack require an explicit source update to receive the new worker safeguards.

All **89 portable unit tests passed**, including checksum rejection, blocking custom generation and preserving the selected runtime after a failed candidate. Offline MOSS imports, text/audio forward passes, tiny-model generation and safetensors reload passed with the legacy interpreter. A real 20-second CPU Beat This inference also passed after verifying the default checkpoint. The new Torch 2.10.0 environment, full pretrained inference there and a complete dependency advisory scan remain unverified. Package audit services were also unreachable. See [the upgrade procedure](docs/RUNTIME_UPGRADE.md).

## Remaining trust boundaries

Pinned Hugging Face URLs and checksums establish model identity, not harmlessness or license clearance. External custom nodes execute Python with your permissions. Keep ComfyUI/Ollama on trusted interfaces and use trusted source code and workflows.

The version inventory in `audio_environment.lock.txt` records the legacy environment; it is not the new installer input or a wheel-hash lock. Dependency license metadata likewise records that observed environment. The audio subprocess manages memory/lifecycle and does not restrict filesystem permissions.

Remove credentials, private paths, songs and lyrics from security reports. A private reporting contact can be added when the publication repository is assigned.
