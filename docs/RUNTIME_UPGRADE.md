# Audio runtime update

The supported setup command remains:

```text
uv run python setup_runtime.py --install-environment
```

It now creates a new environment under `.audio-env-candidates/`, installs Torch/torchaudio 2.10.0 from the official CUDA 12.8 wheel index, and installs the pinned dependencies in `audio_requirements.txt`, including setuptools 84.2.1 and Transformers 4.57.6. It runs the dependency checker plus offline imports, a small MOSS text forward pass, audio-encoder pass, text-generation pass and safetensors reload. It writes `runtime_config.json` only after those checks pass. Existing environments are not overwritten. A failed install/check leaves the current runtime selected.

The selected Torch version addresses the reviewed [PyTorch checkpoint advisory](https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p). It is a conservative compatibility target, not a claim to be the latest release or free of every possible advisory. The setuptools target is above the reviewed fixed version. Transformers remains on the MOSS-compatible 4.57 series: its custom-generation loader is explicitly disabled in the worker, checkpoint Python auto-loading is disabled, safetensors loading is required for MOSS, and inference stays offline. This is a scoped mitigation of the custom-generation advisory, not a claim that upstream Transformers 4.57.6 has no advisories.

The default Beat This checkpoint is verified against its expected SHA-256 **before deserialization**. Downloads are checked before becoming the installed file; an unexpected existing checkpoint is rejected. Nondefault Beat This checkpoints require Torch 2.10.0 or later. These checks do not establish the safety of arbitrary models or external source code.

The setup compatibility checks use a small random-weight model. They do not replace full pretrained MOSS/Beat This inference on real audio. Before calling an upgrade fully validated, run an uncached short real-song analysis with the candidate, then the portable tests and a dependency advisory scan. `runtime_check.py --allow-legacy --repository <pinned-MOSS-source>` is a diagnostic for the previous environment only; its report explicitly marks old dependencies as unpatched.

If setup succeeds, the old environment remains on disk and its configuration is saved as `runtime_config.previous.json`. To restore that selection, copy that file back to `runtime_config.json`. A separately installed node pack has its own configuration; use `--configure-pack <path>` only when deliberately activating the checked candidate there too.

On this review machine, package network access was refused and the request to run a network-enabled package command was rejected because permission escalation is disabled. Patched wheel installation and its compatibility checks could not be completed here. The existing environment has not been silently upgraded or declared security-cleared. The former environment inventory is retained as `audio_environment.lock.txt` for historical inspection; setup no longer installs those old pins.
