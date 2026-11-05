"""Small offline compatibility checks for a candidate audio interpreter."""
import argparse,importlib.metadata,json,os,sys,shutil,uuid
from pathlib import Path
from runtime_security import disable_custom_generation,version_tuple

def check(repository,allow_legacy=False,scratch_root=None):
    versions={name:importlib.metadata.version(name) for name in ('torch','torchaudio','transformers','setuptools','beat-this','bitsandbytes')}
    patched=(version_tuple(versions['torch'])>=(2,10,0) and version_tuple(versions['setuptools'])>=(84,2,1))
    if not patched and not allow_legacy:raise RuntimeError('Candidate runtime must provide Torch >=2.10.0 and setuptools >=84.2.1: '+json.dumps(versions))
    if version_tuple(versions['torch'])[:2]!=version_tuple(versions['torchaudio'])[:2]:raise RuntimeError('Torch and torchaudio versions do not match')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    import socket
    def blocked(*args,**kwargs):raise RuntimeError('Network disabled during the runtime compatibility check')
    socket.socket.connect=socket.socket.connect_ex=blocked
    sys.path.insert(0,str(Path(repository).resolve()))
    import torch
    torch.set_num_threads(min(4,torch.get_num_threads()))
    import torchaudio
    import bitsandbytes
    import soxr
    import soundfile
    from beat_this.inference import Audio2Beats
    from src.configuration_moss_music import MossMusicConfig
    from src.modeling_moss_music import MossMusicModel
    from src.processing_moss_music import MossMusicProcessor
    from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn
    disable_custom_generation(MossMusicModel)
    config=MossMusicConfig(audio_config=dict(d_model=16,output_dim=16,encoder_layers=1,encoder_attention_heads=2,
        encoder_ffn_dim=32,downsample_hidden_size=2,max_source_positions=64,deepstack_encoder_layer_indexes=[]),
        language_config=dict(vocab_size=128,hidden_size=16,intermediate_size=32,num_hidden_layers=1,num_attention_heads=2,
            num_key_value_heads=2,head_dim=8,max_position_embeddings=128,eos_token_id=2,bos_token_id=1,pad_token_id=0),adapter_hidden_size=32)
    model=MossMusicModel(config).eval()
    with torch.inference_mode():
        ids=torch.tensor([[1,3,4]])
        output=model(input_ids=ids,attention_mask=torch.ones_like(ids))
        if output.logits.shape!=(1,3,128) or not torch.isfinite(output.logits).all():raise RuntimeError('Tiny MOSS language forward failed')
        encoded=model.audio_encoder(torch.zeros(1,128,32),torch.tensor([32]))
        if not torch.isfinite(encoded.last_hidden_state).all():raise RuntimeError('Tiny MOSS audio encoder failed')
        generated=model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),max_new_tokens=2,do_sample=False,pad_token_id=0)
        if generated.shape[1]<=ids.shape[1]:raise RuntimeError('Tiny MOSS generation failed')
        # Store only random tiny-model weights under an explicit app-owned directory.
        # No real song/model contents or secrets are written by this diagnostic.
        scratch_root=Path(scratch_root or Path(__file__).resolve().parent/'test_results/runtime_check').resolve()
        temp=scratch_root/('tiny-model-'+uuid.uuid4().hex)
        temp.mkdir(parents=True,exist_ok=False)
        try:
            model.save_pretrained(str(temp),safe_serialization=True)
            restored=MossMusicModel.from_pretrained(str(temp),local_files_only=True,use_safetensors=True,trust_remote_code=False)
            restored.eval()
            if not torch.allclose(output.logits,restored(input_ids=ids,attention_mask=torch.ones_like(ids)).logits):raise RuntimeError('MOSS safetensors reload changed the small-model output')
        finally:
            if temp.resolve().parent!=scratch_root or not temp.name.startswith('tiny-model-'):raise RuntimeError('Refusing cleanup outside the diagnostic directory')
            shutil.rmtree(temp)
    return dict(passed=True,patched_version_requirements=patched,versions=versions,checks=['imports','MOSS text forward','MOSS audio encoder','MOSS text generation','MOSS safetensors reload','custom generation disabled'],
        full_model_inference_tested=False,network_disabled=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository',required=True,type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--allow-legacy',action='store_true',help='Compatibility diagnostic only; never marks an old environment patched')
    args=parser.parse_args();result=check(args.repository,args.allow_legacy,args.output.resolve().parent if args.output else None)
    text=json.dumps(result,indent=2)
    if args.output:args.output.write_text(text+'\n',encoding='utf-8')
    print(text)

if __name__=='__main__':main()
