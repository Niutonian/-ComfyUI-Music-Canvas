# Music Canvas · Audio to Video for ComfyUI

**Upload an MP3. Get a music video.**

[MIT-licensed source](LICENSE) · Local models · Block Party optional

Music Canvas is a local audio-to-video (A2V) pipeline for ComfyUI. Load a song, choose the range you want to turn into video, and queue the directed workflow. It analyzes the music's style, mood, instruments and rhythm, develops a visual concept and story, writes prompts for each scene, and renders an H3 video with your original soundtrack. After setup, those creative stages run automatically; you can also choose a concept, directing approach or animation medium yourself.

MOSS-Music provides music understanding, Beat This! measures beats, and a local Ollama model plans the visuals. Short-clip and sequential workflows cover previews and longer music videos. The sequential renderer saves progress between segments so interrupted runs can resume, and returns a video preview directly in ComfyUI.

## One song. Two interpretations.

The same **15-second excerpt**, two different visual directions. Both clips use Herbert & Momoko's *Need to Run*, from **00:30 to 00:45**, with the same render seed. The director's concept choice and seed differ between runs.

| Direction A | Direction B |
| --- | --- |
| [![Direction A — animated preview](docs/media/comparison-a.gif)](docs/media/comparison-a.mp4) | [![Direction B — animated preview](docs/media/comparison-b.gif)](docs/media/comparison-b.mp4) |
| [Watch the 15-second video with sound](docs/media/comparison-a.mp4) | [Watch the 15-second video with sound](docs/media/comparison-b.mp4) |

The animated previews are compressed and silent. Open the MP4s for the full-resolution, 24 fps versions with the same soundtrack. These are excerpts from existing local generations; no new scenes were generated for this comparison. [Comparison details and media credits](docs/media/README.md).

## Three examples

| Workflow | Purpose | Saved settings |
| --- | --- | --- |
| [music_canvas_simple](examples/music_canvas_simple/README.md) | Audio-guided rendering with your written prompt; no analysis or LLM | 15 seconds, 0.3 MP, 8 steps |
| [music_canvas_sequential_Good](examples/music_canvas_sequential_Good/README.md) | Analysis → concepts → story/editor → timeline → sequential video | 60 seconds in 15-second segments, 0.3 MP, 8 steps |
| [music_canvas_14sec_max](examples/music_canvas_14sec_max/README.md) | Analyze an excerpt and render one directed clip | Saved at 8 seconds, 0.8 MP, 8 steps |

Each folder contains UI/API workflows, a Block Party manifest, readiness status and notes. Only these three are publication workflow examples. No full source songs, weights or private analyses are included. The four showcase files in `docs/media/` are the only published generated media; their soundtrack and media rights are separate from the code's MIT license.

## Installation

**Block Party is optional.** You can install the nodes and download the models yourself using the steps below. The filenames and locations match the three supplied examples; all locations are relative to your ComfyUI installation.

### 1. Install the node pack and prerequisites

From your `ComfyUI/custom_nodes/` folder, clone the node pack:

```text
git clone https://github.com/Niutonian/-ComfyUI-Music-Canvas.git ComfyUI_LocalMusicCanvas
```

- Use an H3-capable ComfyUI and install [ComfyUI-H3-Multishot](https://github.com/jlucasmcrell/ComfyUI-H3-Multishot) for the H3 model/encoder loaders. The `music_canvas_14sec_max` example also needs [ComfyUI-MMH3Tools](https://github.com/ckinpdx/ComfyUI-MMH3Tools) for its frame calculator.
- Install [FFmpeg](https://ffmpeg.org/download.html) on PATH for sequential video exports. ComfyUI supplies its usual Torch, audio, soundfile and video dependencies; this node pack does not upgrade ComfyUI's Torch.
- For the two audio-analysis examples, install Git, [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com/). The simple example does not need MOSS-Music, Beat This! or Ollama.

The examples were inspected against ComfyUI core commit `bc5f880dbdd43e426077f42ccec53bb577ffee9f`; saved workflow metadata reports 0.42.0. Exact external pack commits are recorded in each example's manifest.

### 2. Download the H3 video models

All three examples use these four files. The links download the exact pinned versions used by the exported workflows.

| Component / download | Save in | Approximate size |
| --- | --- | --- |
| [Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors](https://huggingface.co/WarmBloodAban/Minimax-h3_Singularity/resolve/1259cf16cd0b655ba691a32fb46a409142762972/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors) — video model | `models/diffusion_models/` | 21.0 GB |
| [qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/54472221d27c695fca9621b0c3ed52f06c4af707/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors) — text encoder | `models/text_encoders/` | 15.7 GB |
| [minimax_h3_video_vae_fp16.safetensors](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/54472221d27c695fca9621b0c3ed52f06c4af707/vae/minimax_h3_video_vae_fp16.safetensors) — video VAE | `models/vae/` | 5.2 GB |
| [minimax_h3_audio_vae_fp32.safetensors](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/54472221d27c695fca9621b0c3ed52f06c4af707/vae/minimax_h3_audio_vae_fp32.safetensors) — audio-conditioning VAE | `models/vae/` | 0.61 GB |

Download the LoRAs used by your chosen example into `models/loras/`:

| Download | Used by | Approximate size |
| --- | --- | --- |
| [minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/54472221d27c695fca9621b0c3ed52f06c4af707/loras/minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors) | `music_canvas_simple` and `music_canvas_14sec_max` | 1.96 GB |
| [minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI/resolve/bb2bc497cbaca89dadd0bcf1856eed4f8275be20/experimental/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors) | `music_canvas_sequential_Good` | 2.29 GB |
| [Better Motion: mvmt_h3_lora_v1_500.safetensors](https://huggingface.co/Alex995647/loras-minimax-h3/resolve/07b79f96579028828a829f6d52923385a93bff72/better-motion-ltx-minimax-h3/mvmt_h3_lora_v1_500.safetensors) | All three examples | 0.31 GB |

**Rename the Better Motion download to `better_motion_h3_lora_v1_500.safetensors`** so its filename matches the workflow selectors. Its bytes match the locally tested file. The examples retain eight sampling steps; the 4-step LoRA's filename does not change that sampler setting automatically.

Sizes are download/storage sizes, not VRAM requirements. SHA-256 checksums are listed in [model_sources.json](docs/model_sources.json). Model and LoRA licenses apply separately; read the [license review](docs/LICENSE_REVIEW.md), particularly the H3 and Better Motion terms, before downloading or using them.

### 3. Set up music analysis

Skip this section for `music_canvas_simple`.

From `ComfyUI/custom_nodes/ComfyUI_LocalMusicCanvas`, run:

```text
uv run python setup_runtime.py --install-environment
```

This builds a new isolated Python 3.12 candidate with the pinned MOSS source, Torch/torchaudio 2.10.0 and the requirements in `audio_requirements.txt`. It checks dependencies, imports and a small MOSS model before selecting the candidate in `runtime_config.json`; failure preserves the previous selection. Full pretrained inference is a separate validation. The candidate installation could not be completed in this review environment because package network access was blocked. See [the runtime upgrade notes](docs/RUNTIME_UPGRADE.md) and [SECURITY.md](SECURITY.md) for the exact validation status and scoped safeguards.

For manual model installation:

| Model / download | Required local location | Approximate size |
| --- | --- | --- |
| [MOSS-Music-8B-Instruct — complete pinned model snapshot](https://huggingface.co/OpenMOSS-Team/MOSS-Music-8B-Instruct/tree/fce7f8304e96cc2d3398b8106456cbb2ecec3139) | `models/moss_music/MOSS-Music-8B-Instruct/` | 18.1 GB |
| [Beat This! final0 checkpoint](https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt) | `models/beat_this/beat_this-final0.ckpt` | 81 MB |

For MOSS-Music, copy **all the files listed in [moss_snapshot.json](docs/moss_snapshot.json)**, preserving their relative paths. This includes the weight shards, weight index, configuration, processor/tokenizer files and model Python files. A single weights file is insufficient. The snapshot's `config.json` must sit directly inside `MOSS-Music-8B-Instruct/`, not in an extra nested download directory. Rename the Beat This download from `final0.ckpt` to `beat_this-final0.ckpt`.

The resulting layout is:

```text
ComfyUI/models/
  diffusion_models/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors
  text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
  vae/minimax_h3_video_vae_fp16.safetensors
  vae/minimax_h3_audio_vae_fp32.safetensors
  loras/...LoRAs for your chosen example...
  moss_music/MOSS-Music-8B-Instruct/config.json
  moss_music/MOSS-Music-8B-Instruct/...remaining snapshot files...
  beat_this/beat_this-final0.ckpt
```

If you prefer a setup downloader, run this from the node pack directory on Windows, replacing the model-root path with your actual location:

```powershell
$audioPython = (Get-Content .\runtime_config.json -Raw | ConvertFrom-Json).python
& $audioPython .\audio_assets.py --models-root "C:\path\to\ComfyUI\models"
```

On Linux, run `audio_assets.py --models-root /path/to/ComfyUI/models` with the configured interpreter printed by setup (the candidate's `bin/python`). This downloads the pinned MOSS snapshot and the checksum-verified author-hosted Beat This checkpoint without Block Party. You can alternatively enable `allow_model_download` in Analyze Audio. For manually installed models, leave that switch off; it is off in the shared examples. ComfyUI model discovery also supports matching roots in `extra_model_paths.yaml`.

### 4. Set up the local prompt director

Skip this section for `music_canvas_simple`.

The analysis examples select the local Ollama alias `ornith-1.5:35b`. To reproduce the documented public setup, download [Ornith-1.5-35B-Q4_K_M.gguf](https://huggingface.co/ornith-ai/Ornith-1.5-35B-A3B-GGUF/resolve/12393612fd4f730ff5aadc23e9b8f9648aa49ceb/Ornith-1.5-35B-Q4_K_M.gguf) (21.7 GB), verify its checksum in [model.json](docs/ollama/model.json), and place it beside `docs/ollama/Modelfile`. From `docs/ollama/`, run:

```text
ollama create ornith-1.5:35b -f Modelfile
```

Ollama imports this file into its own model store; it does not belong in a ComfyUI model folder. Keep Ollama serving at `http://127.0.0.1:11434`. You can instead select another compatible model already installed in Ollama; it will affect the generated direction. See [the Ollama notes](docs/ollama/README.md) for details and the difference from the original workstation's local model.

### 5. Generate your first video

1. Restart ComfyUI so it discovers the node pack and models.
2. Drag the chosen example's `workflow.json` into ComfyUI. The UI files are in the three folders under `examples/`; `workflow.api.json` is for API execution.
3. In Load Audio, replace `SELECT_YOUR_AUDIO.wav` with your own track. In the timing/trim node, choose the start and duration. Begin with a short range and adjust resolution for your hardware.
4. For `music_canvas_simple`, enter a visual prompt. For the directed examples, confirm the audio model dropdowns and local Ollama model; keep the style dropdowns at `none` for automatic music-guided direction.
5. Queue the workflow. Watch the video preview and find the exports under ComfyUI's `output/music_canvas/` directory. The sequential workflow also saves its segment checkpoints there.

## Optional: Block Party

Install [Comfyui_BlockParty](https://github.com/Niutonian/Comfyui_BlockParty) and import one of the [three native ZIP exports](share/README.md). Model entries contain direct commit-pinned Hugging Face URLs, sizes and SHA-256 checksums; the Beat This checkpoint has an explicit model mapping. No weights are embedded.

The exports pin Music Canvas to [source commit f537649](https://github.com/Niutonian/-ComfyUI-Music-Canvas/commit/f537649f349e00bb6ce500f541d95b4bca3e4aae), alongside the external node and model sources. The simple workflow's dependency sources are ready for Block Party preparation. The two analysis workflows also need a configured audio runtime, MOSS snapshot and local Ollama/model; their `readiness.json` files list those manual prerequisites. Compatible ComfyUI, hardware, FFmpeg and access to the models remain required. Block Party's normal preparation confirmations still apply.

The motion LoRA's upstream filename differs from its local filename. Its verified source bytes are installed as `better_motion_h3_lora_v1_500.safetensors` to match these graphs. See [model_sources.json](docs/model_sources.json).

## Controls and limitations

`concept_index=0` automatically chooses among six music-grounded candidates; 1–6 selects one. Both style dropdowns at `none` retain automatic selection. New seed/regenerate values explore new directions; unchanged settings reuse cached results. `reanalyze` is a cache revision counter: increment it only to request fresh audio analysis.

The directed sequential workflow plans across the selected range with distinct scene prompts. Total duration is not limited to one H3 clip; processing time, planning limits and machine resources still apply. Separate segments do not guarantee character identity or seamless boundaries. Extending the simple workflow reuses its supplied prompt; use the directed workflow for story progression.

Native audio conditioning and beat-aware prompts do not guarantee exact beat synchronization. These examples do not enable optional postprocessing beat retiming. Their saved 2:3 development exports are not automatically finished Spotify Canvas loops.

Run `python tools/audit_publication.py --working-tree` before staging, then `python tools/audit_publication.py --index` to scan actual staged blobs. Run `python tools/run_unit_tests.py` for the portable unit suite. These checks do not generate videos or download models. See the publication report for validation limits.

## Repository layout

The root Python files are the node pack's runtime modules and setup/download entry points. They stay beside `__init__.py` because ComfyUI imports this directory directly and the audio worker loads its sibling modules. Portable tests live in `tests/`, maintained command-line helpers in `tools/`, and the three published workflows in `examples/`. `docs/` contains current documentation; `share/` contains Block Party exports.

Historical development scripts, superseded notes and inspection dumps are retained locally in `archive/`, excluded from publication. They may depend on their former paths and are not supported installation commands. Runtime environments, assets, generated projects/videos and local configuration remain in their existing locations.

## Publication status

The three examples passed live ComfyUI validation, the publication/index cleanup succeeded, and the runtime unit tests and media-publication checks passed. The 89-file publication set, including the four showcase files, passes both the working-tree and staged-content scans. Original source is MIT-licensed, and Block Party exports now include a published source pin. Patched runtime installation/full-model validation remains pending because package network access was blocked; the existing environment was preserved. See the [publication review](docs/PUBLICATION_REVIEW.md), [license review](docs/LICENSE_REVIEW.md) and [security findings](SECURITY.md) for details. External model and soundtrack licenses remain separate from MIT.
