# music_canvas_simple

Direct prompt-driven rendering: audio → selected range → H3 with your written visual prompt → preview/SaveVideo. No MOSS, Beat This, Ollama or story planning. Longer ranges reuse the supplied prompt across segments; use the directed sequential example for narrative development.

Saved at 15 seconds, start 0, 15-second segments, 0.3 MP at 2:3, 8 steps. Sequential rendering rounds dimensions down to multiples of 16. Models: Singularity INT8, Qwen NVFP4/AWQ encoder, both H3 VAEs, 4-step turbo LoRA at 0.8 and Better Motion at 0.74. The LoRA name does not force the sampler's step count; eight is retained from the original graph.

Load `workflow.json`, select your audio and edit the multiline prompt. Its generic sample replaces a private recovered prompt. The project label is `music_canvas_simple`; run folders receive revisions automatically. Matching inputs can resume. The native VIDEO output is connected to SaveVideo.

The matching Block Party ZIP has one audio slot, one video output and six verified model downloads. `readiness.json` states the missing Music Canvas public source pin. FFmpeg, the compatible host/loaders, hardware and model permissions are required. No audio is included; the user's saved original was not modified.
