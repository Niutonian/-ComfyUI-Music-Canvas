# Ollama setup

The examples select `ornith-1.5:35b`, a local alias, not a promised `ollama pull` registry entry.

1. Review the model card and download the GGUF from the pinned URL in [model.json](model.json). Put it beside `Modelfile`.
2. Verify its SHA-256 against that JSON, for example with PowerShell `Get-FileHash -Algorithm SHA256 ./Ornith-1.5-35B-Q4_K_M.gguf`.
3. Run `ollama create ornith-1.5:35b -f Modelfile` here.
4. Check `ollama list`, serve on `http://127.0.0.1:11434`, and refresh ComfyUI node definitions.

The GGUF is approximately 21.7 GB. Hardware/memory requirements still apply. Music Canvas unloads its tracked Ollama model before video generation. The original local alias has a different blob digest from this public GGUF: this is a documented public setup candidate, not a byte-identical recreation of that local model or its outputs. Another compatible installed Ollama model can be selected, with different creative results.
