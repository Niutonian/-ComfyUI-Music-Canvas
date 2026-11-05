# Block Party exports

- [music_canvas_simple.zip](music_canvas_simple.zip)
- [music_canvas_sequential_Good.zip](music_canvas_sequential_Good.zip)
- [music_canvas_14sec_max.zip](music_canvas_14sec_max.zip)

Built with Block Party's native exporter, with no source audio or weights. Import through its library. UI graphs and detailed notes are in `examples/<name>/`.

Music Canvas is pinned to [published source commit f537649](https://github.com/Niutonian/-ComfyUI-Music-Canvas/commit/f537649f349e00bb6ce500f541d95b4bca3e4aae). The simple job has complete node/model dependency sources for Block Party preparation. The analysis jobs still require the audio runtime, pinned MOSS snapshot and local Ollama/model. Read each readiness report and the main README; compatible ComfyUI, FFmpeg, hardware and model access are required.

To repin a future release or fork, run `python tools/finalize_block_party.py --block-party-root <installed-BlockParty> --repository https://github.com/OWNER/REPOSITORY --commit <full-release-commit>`. It rebuilds three manifests/ZIPs; it does not install dependencies, render or push Git changes.
