# Block Party exports

- [music_canvas_simple.zip](music_canvas_simple.zip)
- [music_canvas_sequential_Good.zip](music_canvas_sequential_Good.zip)
- [music_canvas_14sec_max.zip](music_canvas_14sec_max.zip)

Built with Block Party's native exporter, with no source audio or weights. Import through its library. UI graphs and detailed notes are in `examples/<name>/`.

**Requires manual setup:** Music Canvas has no assigned public repository/commit. Null pins deliberately stop preparation rather than install the wrong repository. Install this pack manually for now. Analysis examples also need the audio runtime and local Ollama/model. Read their readiness reports and the main README.

After a release commit exists, run `python tools/finalize_block_party.py --block-party-root <installed-BlockParty> --repository https://github.com/OWNER/REPOSITORY --commit <full-release-commit>`. It rebuilds three manifests/ZIPs; it does not install dependencies, render or push Git changes.
