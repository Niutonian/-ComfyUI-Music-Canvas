# music_canvas_14sec_max

Single-clip workflow: audio → frame-calculated excerpt → quick music analysis → Ollama concept/prompt → unload Ollama → audio-guided H3 → decode → two SaveVideo outputs (original audio and silent). No long-form story planner/editor.

Despite its name, the saved graph requests **8 seconds**. The calculator snaps to native `(17j+5)/24` durations at 24 fps; eight seconds is exactly 192 frames. The filename is not a hardcoded 14-second limit. Near 14 seconds, choose rounding deliberately and keep actual duration within the director's 15-second social-preview maximum.

Saved at start 0, 0.8 MP at 2:3, 8 steps, 4-step turbo LoRA at 0.8 and Better Motion at 0.65. Longer/higher-resolution clips increase memory use. The external MMH3Tools frame calculator is pinned in the manifest; its unresolved source-license status is documented in the license review.

`concept_index=0` and both style dropdowns at `none` retain music-guided automatic selection. Shared transcription/approval and downloads are off. Select your audio in `workflow.json`; follow the main README for runtime/models/Ollama.

The matching Block Party ZIP exposes one audio input, two video outputs and seven verified model references including Beat This. Music Canvas has a published source pin. MOSS snapshot/runtime and Ollama setup are separate prerequisites, so `readiness.json` still marks manual setup. No input song is shared, and the user's original graph was not altered.
