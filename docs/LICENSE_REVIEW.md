# License review — 2026-11-05

Original project source, sanitized examples and metadata are selected for publication, together with two explicitly identified 15-second showcase clips and their previews. No upstream node source, weights, complete source songs or training datasets are bundled. The showcase soundtrack is third-party material, is not covered by MIT, and its publication rights have not been independently verified. See [media credits and rights](media/README.md). A download URL is not a license grant.

**Original Music Canvas source is licensed under MIT**, at the author's instruction. See [LICENSE](../LICENSE). This permits commercial use, modification and redistribution subject to its notice requirements. MIT applies to this project's original code and documentation; it does not relicense external models, node packs, music or ComfyUI. The extension imports GPL-licensed ComfyUI, whose terms still apply to distribution of the host or a combined package.

**H3 is restricted.** Its [official community agreement](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) excludes the EU, UK, Republic of Korea and USA from its applicable territory, and addresses derivatives, outputs, redistribution and commercial use. Germany is in the EU. The reviewed text provides no personal-use exception. Separate authorization may be needed. Apache badges on H3 derivative repositories do not establish that the underlying terms disappeared.

| Component | Observed terms / status | Publication treatment |
| --- | --- | --- |
| Original Music Canvas source/prompts/examples | MIT | Full license included in LICENSE |
| [ComfyUI](https://github.com/Comfy-Org/ComfyUI/blob/master/LICENSE) | GPL-3.0 | External host |
| [MOSS-Music model](https://huggingface.co/OpenMOSS-Team/MOSS-Music-8B-Instruct), [source](https://github.com/OpenMOSS/MOSS-Music) | Model card Apache-2.0; source separately pinned | Fetch externally; retain upstream terms |
| [Beat This!](https://github.com/CPJKU/beat_this#license) | Code and published weights MIT; datasets separate | External author-hosted checkpoint |
| [H3 and its VAEs](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) | Restricted community agreement | No weights bundled |
| [Qwen3-VL](https://github.com/QwenLM/Qwen3-VL/blob/main/LICENSE) | Upstream Apache-2.0; H3 integration separate | External encoder |
| [Singularity](https://huggingface.co/WarmBloodAban/Minimax-h3_Singularity) | Card Apache-2.0 conflicts with unresolved underlying H3 terms | Source/hash supplied; not unrestricted clearance |
| [8-step LoRA](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI), [4-step LoRA](https://huggingface.co/Comfy-Org/MiniMax-H3) | H3-derived; preserve underlying restrictions | External downloads |
| [Better Motion, AdaptiveVision](https://civitai.com/models/2734359), [HF mirror](https://huggingface.co/Alex995647/loras-minimax-h3) | Author API: no-credit allowed; commercial Image/RentCivit/Rent; derivatives=false; different-license=false | Link exact matching bytes; no weights redistributed/relicensed |
| [Ornith 1.5 GGUF](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B-GGUF) | Card MIT; full base-model provenance still matters | External model import |
| [Ollama](https://github.com/ollama/ollama/blob/main/LICENSE) | MIT runtime, independent of model license | External service |
| [H3-Multishot](https://github.com/jlucasmcrell/ComfyUI-H3-Multishot/blob/main/LICENSE) | Installed repository MIT | External pack, pinned |
| [MMH3Tools](https://github.com/ckinpdx/ComfyUI-MMH3Tools) | No LICENSE found in the inspected installed revision | External only; clarify before copying source |
| [Block Party](https://github.com/Niutonian/Comfyui_BlockParty) | External tooling; implementation not copied | Native export format only |
| [FFmpeg](https://ffmpeg.org/legal.html) | LGPL/GPL depending on build | Not distributed |
| Input music, lyrics, artwork and outputs | Depends on input owner and model terms | Two credited showcase excerpts and previews included; excluded from MIT. No full source songs or raw lyrics |

Model revisions, filenames, hashes and URLs are in [model_sources.json](model_sources.json). External node revisions are in manifests. [Dependency license metadata](DEPENDENCY_LICENSES.json) records the observed Python environment; metadata does not replace upstream texts if you later distribute binaries. Model access does not establish permission to use it. This report is not worldwide legal clearance.
