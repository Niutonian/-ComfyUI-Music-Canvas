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

## Start here

Open [`music_canvas_start_here.json`](examples/music_canvas_start_here/music_canvas_start_here.json) in ComfyUI. This starter renders a 12-second excerpt in two 6-second segments at 0.25 MP and eight steps, with Fast direction, lyrics transcription off, and visual continuity on. Load your own audio to begin.

The sequential story planner checks that the overall story and ending agree before writing scenes, then reviews the story and expanded shots for continuity. Scene numbering and next-scene links are automatic. Approved plans are cached, so unchanged runs reuse their direction; after a failed edit, rerunning retries the repair while keeping valid earlier work. `regenerate` requests a fresh plan. The editor uses a conservative temperature independently of the creative writer. Checks review planned text, not rendered video, and an unresolved material contradiction still stops the job rather than silently exporting an inconsistent plan.

The production bible carries recurring designs, palette and animation style across cuts. In the sequential workflow, enable **visual_continuity** on the H3 renderer to add visual guidance. The first clip supplies one reference image for the rest of the film. Each later clip opens from the previous planned ending and starts a new action, with its own camera directions and audio guide. The reference guides appearance while shots can change pose, framing and location.

One queue run renders the selected range in order and exports an MP4 with the original audio. For longer projects, keep the director, planner and renderer seeds fixed if you want to resume after an interruption. Matching runs reuse completed segments and the saved reference; changed prompts or render settings start a new revision.

## Installation

**Block Party is optional.** You can install the nodes and download the models yourself using the steps below. The filenames and locations match the starter workflow; all locations are relative to your ComfyUI installation.

### 1. Install the node pack and prerequisites

From your `ComfyUI/custom_nodes/` folder, clone the node pack:

```text
git clone https://github.com/Niutonian/-ComfyUI-Music-Canvas.git ComfyUI_LocalMusicCanvas
```

- Use an H3-capable ComfyUI and install [ComfyUI-H3-Multishot](https://github.com/jlucasmcrell/ComfyUI-H3-Multishot) for the H3 model/encoder loaders.
- Install [FFmpeg](https://ffmpeg.org/download.html) on PATH for sequential video exports. ComfyUI supplies its usual Torch, audio, soundfile and video dependencies; this node pack does not upgrade ComfyUI's Torch.
- For music analysis, install Git, [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com/).

Use a ComfyUI build with native MiniMax H3 reference conditioning. The starter manifest records the H3 loader pack's source commit.

### 2. Download the H3 video models

The starter uses these four files. The links download the pinned versions used by the workflow.

| Component / download | Save in | Approximate size |
| --- | --- | --- |
| [Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors](https://huggingface.co/WarmBloodAban/Minimax-h3_Singularity/resolve/1259cf16cd0b655ba691a32fb46a409142762972/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors) — video model | `models/diffusion_models/` | 21.0 GB |
| [qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/54472221d27c695fca9621b0c3ed52f06c4af707/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors) — text encoder | `models/text_encoders/` | 15.7 GB |
| [minimax_h3_video_vae_fp16.safetensors](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/54472221d27c695fca9621b0c3ed52f06c4af707/vae/minimax_h3_video_vae_fp16.safetensors) — video VAE | `models/vae/` | 5.2 GB |
| [minimax_h3_audio_vae_fp32.safetensors](https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/54472221d27c695fca9621b0c3ed52f06c4af707/vae/minimax_h3_audio_vae_fp32.safetensors) — audio-conditioning VAE | `models/vae/` | 0.61 GB |

Download these LoRAs into `models/loras/`:

| Download | Used by | Approximate size |
| --- | --- | --- |
| [minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI/resolve/bb2bc497cbaca89dadd0bcf1856eed4f8275be20/experimental/minimax_h3_dmd_ref2va_8step_turbo_pruned.safetensors) | Starter | 2.29 GB |
| [Better Motion: mvmt_h3_lora_v1_500.safetensors](https://huggingface.co/Alex995647/loras-minimax-h3/resolve/07b79f96579028828a829f6d52923385a93bff72/better-motion-ltx-minimax-h3/mvmt_h3_lora_v1_500.safetensors) | Starter | 0.31 GB |

**Rename the Better Motion download to `better_motion_h3_lora_v1_500.safetensors`** so its filename matches the workflow selectors. Its bytes match the locally tested file. The starter uses eight sampling steps.

Sizes are download/storage sizes, not VRAM requirements. SHA-256 checksums are listed in [model_sources.json](docs/model_sources.json). Model and LoRA licenses apply separately; read the [license review](docs/LICENSE_REVIEW.md), particularly the H3 and Better Motion terms, before downloading or using them.

### 3. Set up music analysis

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
  loras/...starter LoRAs...
  moss_music/MOSS-Music-8B-Instruct/config.json
  moss_music/MOSS-Music-8B-Instruct/...remaining snapshot files...
  beat_this/beat_this-final0.ckpt
```

If you prefer a setup downloader, run this from the node pack directory on Windows, replacing the model-root path with your actual location:

```powershell
$audioPython = (Get-Content .\runtime_config.json -Raw | ConvertFrom-Json).python
& $audioPython .\audio_assets.py --models-root "C:\path\to\ComfyUI\models"
```

On Linux, run `audio_assets.py --models-root /path/to/ComfyUI/models` with the configured interpreter printed by setup (the candidate's `bin/python`). This downloads the pinned MOSS snapshot and the checksum-verified author-hosted Beat This checkpoint without Block Party. You can alternatively enable `allow_model_download` in Analyze Audio. For manually installed models, leave that switch off; it is off in the starter. ComfyUI model discovery also supports matching roots in `extra_model_paths.yaml`.

### 4. Set up the local prompt director

The starter selects `ornith-1.5:9b`. Install the public [Ornith 1.5 9B Q4 model](https://huggingface.co/ornith-ai/Ornith-1.5-9B-GGUF) and create the local alias:

```text
ollama pull hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M
ollama cp hf.co/ornith-ai/Ornith-1.5-9B-GGUF:Q4_K_M ornith-1.5:9b
```

Keep Ollama serving at `http://127.0.0.1:11434`. You can also select another compatible installed model on the Ollama Model node.

### 5. Generate your first video

1. Restart ComfyUI so it discovers the node pack and models.
2. Drag [`music_canvas_start_here.json`](examples/music_canvas_start_here/music_canvas_start_here.json) into ComfyUI.
3. In Load Audio, replace `SELECT_YOUR_AUDIO.wav` with your own track. Confirm the selected Ollama model and keep the saved range and resolution for the first run.
4. Leave Story Helper blank for music-guided direction, or enter a short idea.
5. Queue the workflow. Watch the video preview and find the exports under ComfyUI's `output/music_canvas/` directory. The sequential workflow also saves its segment checkpoints there.

## Optional: Block Party

Import the [Block Party package for the same starter](share/music_canvas_start_here.zip). It includes pinned Hugging Face model links, checksums and the Beat This checkpoint mapping. Install the current Music Canvas pack, set up the MOSS runtime and Ollama, and supply your own audio.

## Controls and limitations

`director_mode` offers **Fast (3 concepts)** for iteration and **Full (6 concepts)** for broader exploration. `concept_index=0` chooses automatically. Use 1–3 in Fast or 1–6 in Full to pick a specific candidate. Both style dropdowns at `none` retain automatic selection. The director uses measured beats to plan visible movement accents and phrase changes, with choreography carrying the progression when it fits the music. New seed or regenerate values explore new directions. Unchanged settings reuse cached results. Increment `reanalyze` only to request fresh audio analysis.

Use **Music Canvas · Story Helper** to enter a short creative reference. Connect its `inspiration` output to the Director’s `artist_direction` to influence concept selection, or to the Story Planner’s `story_inspiration` to develop the selected concept. The helper passes text through without an extra model call. Musical pacing still comes from the audio analysis.

**Music Canvas · Export H3 Continuity Timeline** prepares a Music Canvas plan for the separately installed [H3 Continuity Studio](https://github.com/KadoBOT/ComfyUI-H3-Continuity-Studio). Connect the Ollama Timeline’s `timeline_json` and the Duration and Test Range node’s selected `AUDIO` to the exporter. Queue its output to save the Studio Timeline JSON and its source audio together in `output/music_canvas/continuity_studio`. Use that JSON as the `timeline` value in an `H3C_Timeline` graph with your H3 renderer. The export uses exact clip lengths and fresh cuts. With `visual_memory` enabled, later clips use Studio’s Same scene memory. Disable it for a comparison without visual memory. Render the resulting Timeline in Studio to assess the joins.

The directed sequential workflow plans across the selected range with distinct scene prompts. Total duration is not limited to one H3 clip; processing time, planning limits and machine resources still apply. Separate segments do not guarantee character identity or seamless boundaries.

Native audio conditioning and beat-aware prompts do not guarantee exact beat synchronization. The starter produces a landscape preview. Spotify Canvas requires a separate vertical loop export.

Run `python tools/audit_publication.py --working-tree` before staging, then `python tools/audit_publication.py --index` to scan actual staged blobs. Run `python tools/run_unit_tests.py` for the portable unit suite. These checks do not generate videos or download models. See the publication report for validation limits.

## Repository layout

The root Python files are the node pack's runtime modules and setup/download entry points. They stay beside `__init__.py` because ComfyUI imports this directory directly and the audio worker loads its sibling modules. Portable tests live in `tests/`, maintained command-line helpers in `tools/`, and the starter workflow in `examples/music_canvas_start_here/`. `docs/` contains current documentation; `share/` contains Block Party exports.

Historical development scripts, superseded notes and inspection dumps are retained locally in `archive/`, excluded from publication. They may depend on their former paths and are not supported installation commands. Runtime environments, assets, generated projects/videos and local configuration remain in their existing locations.

## Publication status

Music Canvas source is MIT-licensed. External model and soundtrack licenses are separate. See the [license review](docs/LICENSE_REVIEW.md) and [security findings](SECURITY.md) for runtime validation and dependency details.
