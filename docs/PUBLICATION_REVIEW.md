# Publication review — 2026-11-05

Original source and documentation are now MIT-licensed. Git cleanup succeeded: historical scripts, old workflow bundles, local data and private runtime configuration were removed from the publication index without deleting working files. The selected publication files and actual staged content are scanned separately. No push has been performed and no remote is configured.

## Prepared deliverables

- Only `music_canvas_simple`, `music_canvas_sequential_Good` and `music_canvas_14sec_max` are included as examples, each with UI/API graphs, notes, Block Party manifest, readiness report and native ZIP.
- Shared copies exclude private song names, previous project labels, recovered prompts, preview text and duplicate widget state. Original saved ComfyUI workflows were not edited.
- Eight installed model/checkpoint files were fully hashed. Seven H3/encoder/VAE/LoRA hashes match exact HF LFS metadata; Beat This uses the authors' checkpoint URL and an expected SHA-256. The motion LoRA's renamed local file matches the mirror bytes.
- MOSS snapshot inventory and public Ornith GGUF import instructions are separate from Block Party's single-file model selectors. The original Ollama alias has a different blob digest from that public GGUF; identical results are not promised.
- Manual model downloads, folder locations, filename changes and Ollama setup are now documented in the main README. Block Party is optional.
- Original source licensing is MIT; external licenses and 46 observed dependency license declarations are documented separately. H3's territorial restrictions and conflicting derivative badges remain external license considerations.

## Runtime changes and verification

The worker verifies the default Beat This checkpoint before loading, requires safetensors for MOSS, disables checkpoint Python auto-loading and rejects custom generation code before it can fetch anything. The candidate installer targets Torch/torchaudio 2.10.0, setuptools 84.2.1 and Transformers 4.57.6. It builds a fresh environment and activates it only after dependency/import/tiny-model checks. Existing environments and ComfyUI dependencies are preserved. The legacy inventory is explicitly labeled historical rather than reused as the install input.

All **89 portable unit tests passed**. Offline MOSS imports, a small text forward pass, audio-encoder forward pass, small-model generation and safetensors reload passed in the legacy interpreter. A real 20-second CPU Beat This inference passed with its checkpoint verified before loading. The report explicitly marks the legacy dependencies unpatched. The final full unit run succeeded under Windows PowerShell; attempts under the managed CMD execution context encountered temporary-directory access errors. No runtime code was weakened to turn those access errors into passing tests.

The actual patched candidate installation was attempted and failed because the package host connection was refused. The request for a network-enabled package command was rejected because escalation is disabled. The selected runtime config was unchanged after failure. Consequently, the new dependency set is prepared but **not installed or fully validated** on this machine. The safeguards do not justify calling the old libraries patched or the whole stack vulnerability-free. See [SECURITY.md](../SECURITY.md) and [RUNTIME_UPGRADE.md](RUNTIME_UPGRADE.md).

All three examples passed live ComfyUI validation with zero errors/warnings. An additional contract inspection checked 77 nodes and UI/API equivalence with zero findings. Native Block Party contracts passed; the simple/sequential jobs expose one audio input and one video output, and the single-clip job exposes one audio input and two video outputs. The staged/source/ZIP scans verify the actual selected files. No new full video render was needed for packaging.

## Remaining publication requirements

| Item | Current status |
| --- | --- |
| Code license and publication index | MIT added; obsolete paths removed and intended files staged. Re-run the index audit after any edits. |
| Patched runtime | Install/check the candidate where package network access is available, then run full pretrained inference and a fresh advisory audit. The current machine retains the legacy selection. |
| Public repository and source commit | No destination assigned. Set the real URL/commit and rebuild exports with `tools/finalize_block_party.py` before claiming automatic source installation. |
| Block Party's external prerequisites | Audio environment, MOSS snapshot and local Ollama/model still require setup. `readiness.json` reports these honestly. |
| External licensing | H3 terms and derivative-label conflicts still apply. MMH3Tools has no license file in the reviewed revision; its source is not bundled. |

The installed Music Canvas folder inherits ComfyUI's Git parent if queried carelessly. Export preparation explicitly prevents that incorrect source pin. No weights, complete source songs, credentials or upstream node implementations are bundled. At the author's request, the README now includes two 15-second generated showcase excerpts and their GIF previews. These four files are explicit, hash-checked media exceptions, with source workflow/prompt metadata stripped. The third-party soundtrack is credited and excluded from MIT; public-use rights for that recording have not been independently verified. See `docs/media/README.md`.

Historical scripts and notes remain in ignored `archive/`; supported tests live in `tests/`, maintained helpers in `tools/` and current documentation in `docs/`. Local inspection/test results and the move inventory remain under ignored `test_results/`. Run `python tools/audit_publication.py --working-tree` and `python tools/audit_publication.py --index` immediately before a commit/push. Release readiness remains limited by the runtime and source-pin items above.

## README comparison verification

The two showcase MP4s each decode completely to 360 frames at 24 fps, 688 × 1040, with an exact 15.000-second duration. Their decoded audio hashes match. The two GIF previews each contain 90 frames over 15 seconds. All four files pass complete media decoding and the metadata check found none of the source prompt/workflow tags. Three additional publication-guard tests passed, covering modified bytes, wrong file types and rejection of binary files outside the four named exceptions. The publication manifest records exact showcase sizes and SHA-256 values; the original media folders remain ignored.
