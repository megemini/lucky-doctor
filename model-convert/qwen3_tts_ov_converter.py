"""
qwen3_tts_ov_converter.py - Convert Qwen3-TTS models to OpenVINO IR.

A fully self-contained port of the conversion path (originally shared with the
Lucky Doctor skill's helper). This module intentionally does NOT depend on the
skill in any way - it only needs the public PyPI packages listed in
model-convert/requirements.txt.

Public API:
    convert_qwen3_tts_model(model_id, output_dir, quantization_config=None, use_local_dir=False)
        Convert a full Qwen3-TTS checkpoint (CustomVoice or Base) into OpenVINO
        IR files under output_dir. For the Base variant this also converts the
        speaker encoder and the speech tokenizer (used for voice cloning).

    convert_speech_tokenizer(model_id, output_dir, use_local_dir=False)
        Convert just the 12 Hz speech tokenizer (encoder + decoder).

Output layout under output_dir:
    config.json / preprocessor_config.json / processor files
    openvino_talker_language_model.{xml,bin}
    openvino_talker_embedding_model.{xml,bin}
    openvino_talker_text_embedding_model.{xml,bin}
    openvino_talker_text_projection_model.{xml,bin}
    openvino_talker_code_predictor_embedding_model.{xml,bin}
    openvino_talker_code_predictor_model.{xml,bin}
    openvino_speaker_encoder_model.{xml,bin}          (Base variant only)
    speech_tokenizer/openvino_speech_tokenizer_{encoder,decoder}_model.{xml,bin}
"""

import gc
import sys
import types
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import openvino as ov
import torch

try:
    from openvino import opset13
except ImportError:  # openvino < 2025.0 fallback
    from openvino.runtime import opset13

from openvino.frontend.pytorch.patch_model import __make_16bit_traceable

from transformers.cache_utils import DynamicCache

# nncf is only needed for optional weight compression (quantization_config).
try:
    import nncf

    NNCF_AVAILABLE = True
except ImportError:
    NNCF_AVAILABLE = False


# ============================================================================
# Small shared helpers (ported verbatim from the original conversion pipeline)
# ============================================================================


def patch_cos_sin_cached_fp32(model):
    if (
        hasattr(model, "layers")
        and hasattr(model.layers[0], "self_attn")
        and hasattr(model.layers[0].self_attn, "rotary_emb")
        and hasattr(model.layers[0].self_attn.rotary_emb, "dtype")
        and hasattr(model.layers[0].self_attn.rotary_emb, "inv_freq")
        and hasattr(model.layers[0].self_attn.rotary_emb, "max_position_embeddings")
        and hasattr(model.layers[0].self_attn.rotary_emb, "_set_cos_sin_cache")
    ):
        for layer in model.layers:
            if layer.self_attn.rotary_emb.dtype != torch.float32:
                layer.self_attn.rotary_emb._set_cos_sin_cache(
                    seq_len=layer.self_attn.rotary_emb.max_position_embeddings,
                    device=layer.self_attn.rotary_emb.inv_freq.device,
                    dtype=torch.float32,
                )


def model_has_state(ov_model: ov.Model):
    return len(ov_model.get_sinks()) > 0


def model_has_input_output_name(ov_model: ov.Model, name: str):
    return name in sum([list(t.get_names()) for t in ov_model.inputs + ov_model.outputs], [])


def fuse_cache_reorder(
    ov_model: ov.Model,
    not_kv_inputs: list[str],
    key_value_input_names: list[str],
    gather_dim: int,
):
    if model_has_input_output_name(ov_model, "beam_idx"):
        raise ValueError("Model already has fused cache")
    input_batch = ov_model.input("inputs_embeds").get_partial_shape()[0]
    beam_idx = opset13.parameter(name="beam_idx", dtype=ov.Type.i32, shape=ov.PartialShape([input_batch]))
    beam_idx.output(0).get_tensor().add_names({"beam_idx"})
    ov_model.add_parameters([beam_idx])
    not_kv_inputs.append(ov_model.inputs[-1])

    for input_name in key_value_input_names:
        parameter_output_port = ov_model.input(input_name)
        consumers = parameter_output_port.get_target_inputs()
        gather = opset13.gather(parameter_output_port, beam_idx, opset13.constant(gather_dim))
        for consumer in consumers:
            consumer.replace_source_output(gather.output(0))
    ov_model.validate_nodes_and_infer_types()


def build_state_initializer(ov_model: ov.Model, batch_dim: int):
    input_ids = ov_model.input("inputs_embeds")
    batch = opset13.gather(
        opset13.shape_of(input_ids, output_type="i64"),
        opset13.constant([0]),
        opset13.constant(0),
    )
    for op in ov_model.get_ops():
        if op.get_type_name() == "ReadValue":
            dims = [dim.min_length for dim in list(op.get_output_partial_shape(0))]
            dims[batch_dim] = batch
            dims = [(opset13.constant(np.array([dim], dtype=np.int64)) if isinstance(dim, int) else dim) for dim in dims]
            shape = opset13.concat(dims, axis=0)
            broadcast = opset13.broadcast(opset13.constant(0.0, dtype=op.get_output_element_type(0)), shape)
            op.set_arguments([broadcast])
    ov_model.validate_nodes_and_infer_types()


def make_stateful(
    ov_model: ov.Model,
    not_kv_inputs: list[str],
    key_value_input_names: list[str],
    key_value_output_names: list[str],
    batch_dim: int,
    num_attention_heads: int,
    num_beams_and_batch: int = None,
):
    from openvino._offline_transformations import apply_make_stateful_transformation

    input_output_map = {}

    if num_beams_and_batch is not None:
        for input in not_kv_inputs:
            shape = input.get_partial_shape()
            if shape.rank.get_length() <= 2:
                shape[0] = num_beams_and_batch
                input.get_node().set_partial_shape(shape)

    for kv_name_pair in zip(key_value_input_names, key_value_output_names):
        input_output_map[kv_name_pair[0]] = kv_name_pair[1]
        if num_beams_and_batch is not None:
            input = ov_model.input(kv_name_pair[0])
            shape = input.get_partial_shape()
            shape[batch_dim] = num_beams_and_batch * num_attention_heads
            input.get_node().set_partial_shape(shape)

    if num_beams_and_batch is not None:
        ov_model.validate_nodes_and_infer_types()

    apply_make_stateful_transformation(ov_model, input_output_map)
    if num_beams_and_batch is None:
        build_state_initializer(ov_model, batch_dim)


def patch_stateful(ov_model, dim):
    key_value_input_names = [key.get_any_name() for key in ov_model.inputs[2:-1]]
    key_value_output_names = [key.get_any_name() for key in ov_model.outputs[dim:]]
    not_kv_inputs = [input for input in ov_model.inputs if not any(name in key_value_input_names for name in input.get_names())]
    if not key_value_input_names or not key_value_output_names:
        return
    batch_dim = 0
    num_attention_heads = 1

    fuse_cache_reorder(ov_model, not_kv_inputs, key_value_input_names, batch_dim)
    make_stateful(
        ov_model,
        not_kv_inputs,
        key_value_input_names,
        key_value_output_names,
        batch_dim,
        num_attention_heads,
        None,
    )


def cleanup_torchscript_cache():
    torch._C._jit_clear_class_registry()
    torch.jit._recursive.concrete_type_store = torch.jit._recursive.ConcreteTypeStore()
    torch.jit._state._clear_class_state()


# ============================================================================
# Output file names
# ============================================================================

TALKER_LANGUAGE_NAME = "openvino_talker_language_model.xml"
TALKER_EMBEDDING_NAME = "openvino_talker_embedding_model.xml"
TALKER_TEXT_EMBEDDING_NAME = "openvino_talker_text_embedding_model.xml"
TALKER_TEXT_PROJECTION_NAME = "openvino_talker_text_projection_model.xml"
TALKER_CODE_PREDICTOR_EMBEDDING_NAME = "openvino_talker_code_predictor_embedding_model.xml"
TALKER_CODE_PREDICTOR_NAME = "openvino_talker_code_predictor_model.xml"
SPEAKER_ENCODER_NAME = "openvino_speaker_encoder_model.xml"
SPEECH_TOKENIZER_ENCODER_NAME = "openvino_speech_tokenizer_encoder_model.xml"
SPEECH_TOKENIZER_DECODER_NAME = "openvino_speech_tokenizer_decoder_model.xml"


# ============================================================================
# Conversion
# ============================================================================


def convert_qwen3_tts_model(model_id, output_dir, quantization_config=None, use_local_dir=False):
    """
    Convert Qwen3-TTS model to OpenVINO format.

    Args:
        model_id: HuggingFace model ID or local checkpoint directory.
        output_dir: Directory to save the converted models.
        quantization_config: Optional quantization configuration for nncf.
        use_local_dir: If True and model_id is remote, download it first into
            <output_dir>/ckpt before converting.
    """
    from huggingface_hub import snapshot_download
    from qwen_tts.core.models.configuration_qwen3_tts import Qwen3TTSConfig
    from qwen_tts.core.models.modeling_qwen3_tts import Qwen3TTSForConditionalGeneration
    from qwen_tts.core.models import Qwen3TTSProcessor

    output_dir = Path(output_dir)

    talker_lang_path = output_dir / TALKER_LANGUAGE_NAME
    talker_embedding_path = output_dir / TALKER_EMBEDDING_NAME
    talker_text_embedding_path = output_dir / TALKER_TEXT_EMBEDDING_NAME
    talker_text_projection_path = output_dir / TALKER_TEXT_PROJECTION_NAME
    talker_code_predictor_embedding_path = output_dir / TALKER_CODE_PREDICTOR_EMBEDDING_NAME
    talker_code_predictor_path = output_dir / TALKER_CODE_PREDICTOR_NAME
    speaker_encoder_path = output_dir / SPEAKER_ENCODER_NAME

    if all(
        [
            talker_lang_path.exists(),
            talker_embedding_path.exists(),
            talker_text_embedding_path.exists(),
            talker_text_projection_path.exists(),
            talker_code_predictor_embedding_path.exists(),
            talker_code_predictor_path.exists(),
        ]
    ):
        print(f"✅ {model_id} model already converted. You can find results in {output_dir}")
        return

    print(f"⌛ {model_id} conversion started. Be patient, it may take some time.")
    print("⌛ Load Original model")

    if use_local_dir:
        ckpt = Path(output_dir) / "ckpt"
        if not ckpt.exists():
            snapshot_download(model_id, local_dir=ckpt, force_download=True)
    else:
        ckpt = model_id

    config = Qwen3TTSConfig.from_pretrained(ckpt)
    config.talker_config._attn_implementation_autoset = False
    config.talker_config._attn_implementation = "sdpa"
    config.talker_config.code_predictor_config._attn_implementation_autoset = False
    config.talker_config.code_predictor_config._attn_implementation = "sdpa"

    model = Qwen3TTSForConditionalGeneration.from_pretrained(ckpt, config=config, torch_dtype=torch.float16)
    model.eval()
    processor = Qwen3TTSProcessor.from_pretrained(ckpt)

    config.save_pretrained(output_dir)
    processor.save_pretrained(output_dir)

    # Clean up config.json after saving to remove model_type from speaker_encoder_config
    import json

    config_path = output_dir / "config.json"
    if config_path.exists():
        with open(config_path, "r") as f:
            config_json = json.load(f)
        if "speaker_encoder_config" in config_json and "model_type" in config_json["speaker_encoder_config"]:
            del config_json["speaker_encoder_config"]["model_type"]
            with open(config_path, "w") as f:
                json.dump(config_json, f, indent=2)
            print("✅ Cleaned up config.json (removed model_type from speaker_encoder_config)")

    print("✅ Original model successfully loaded")

    # Convert talker embedding model (codec embedding)
    if not talker_embedding_path.exists():
        print("⌛ Convert talker embedding model")
        __make_16bit_traceable(model.talker.get_input_embeddings())
        ov_model = ov.convert_model(
            model.talker.get_input_embeddings(),
            example_input=torch.ones([2, 2], dtype=torch.int64),
        )
        ov.save_model(ov_model, talker_embedding_path)
        del ov_model
        cleanup_torchscript_cache()
        gc.collect()
        print("✅ Talker embedding model successfully converted")

    # Convert talker text embedding model
    if not talker_text_embedding_path.exists():
        print("⌛ Convert talker text embedding model")
        __make_16bit_traceable(model.talker.get_text_embeddings())
        ov_model = ov.convert_model(
            model.talker.get_text_embeddings(),
            example_input=torch.ones([2, 2], dtype=torch.int64),
        )
        ov.save_model(ov_model, talker_text_embedding_path)
        del ov_model
        cleanup_torchscript_cache()
        gc.collect()
        print("✅ Talker text embedding model successfully converted")

    # Convert talker text_projection model
    if not talker_text_projection_path.exists():
        print("⌛ Convert talker text_projection model")
        __make_16bit_traceable(model.talker.text_projection)
        text_hidden_size = config.talker_config.text_hidden_size
        ov_model = ov.convert_model(
            model.talker.text_projection,
            example_input=torch.ones([1, 3, text_hidden_size], dtype=torch.float32),
            input=[ov.PartialShape([1, -1, text_hidden_size])],
        )
        ov.save_model(ov_model, talker_text_projection_path)
        del ov_model
        cleanup_torchscript_cache()
        gc.collect()
        print("✅ Talker text_projection model successfully converted")

    # Convert Talker Language model
    if not talker_lang_path.exists():
        print("⌛ Convert Talker Language model")

        def forward_wrap_talker(
            self,
            attention_mask: Optional[torch.Tensor] = None,
            position_ids: Optional[torch.LongTensor] = None,
            past_key_values: Optional[list[torch.FloatTensor]] = None,
            inputs_embeds: Optional[torch.FloatTensor] = None,
            use_cache: Optional[bool] = None,
            output_attentions: Optional[bool] = None,
            output_hidden_states: Optional[bool] = None,
            return_dict: Optional[bool] = None,
        ):
            if past_key_values is not None:
                past_key_values = DynamicCache.from_legacy_cache(past_key_values)

            outputs = self.model(
                attention_mask=attention_mask,
                position_ids=position_ids,
                past_key_values=past_key_values,
                inputs_embeds=inputs_embeds,
                use_cache=use_cache,
                output_attentions=output_attentions,
                output_hidden_states=True,
                return_dict=return_dict,
            )
            if past_key_values is not None:
                outputs["past_key_values"] = outputs["past_key_values"].to_legacy_cache()

            hidden_states = outputs[0]
            logits = self.codec_head(hidden_states)
            logits = logits.float()
            output = (logits,) + outputs[:]

            return output

        lang_model = model.talker
        num_pkv = lang_model.model.config.num_hidden_layers
        embedding_size = lang_model.model.config.hidden_size
        patch_cos_sin_cached_fp32(lang_model)
        if hasattr(lang_model, "model"):
            patch_cos_sin_cached_fp32(lang_model.model)
        lang_model._orig_forward = lang_model.forward
        lang_model.forward = types.MethodType(forward_wrap_talker, lang_model)

        pkv_shape = (
            2,
            lang_model.model.config.num_key_value_heads,
            2,
            lang_model.model.config.head_dim,
        )

        cache_position = torch.arange(2, 4)
        position_ids = cache_position.view(1, 1, -1).expand(3, 2, -1)

        input_embeds = torch.randn((2, 2, embedding_size))
        attention_mask = torch.ones([2, 4], dtype=torch.long)
        input_names = ["attention_mask", "position_ids"]
        output_names = ["logits", "hidden_states"]
        past_key_values = []
        for i in range(num_pkv):
            kv = [torch.randn(pkv_shape) for _ in range(2)]
            past_key_values.append(kv)
            input_names.extend([f"past_key_values.{i}.key", f"past_key_values.{i}.value"])
            output_names.extend([f"present.{i}.key", f"present.{i}.value"])
        input_names.append("inputs_embeds")

        example_input = {
            "inputs_embeds": input_embeds,
            "attention_mask": attention_mask,
            "position_ids": position_ids,
            "past_key_values": past_key_values,
        }

        head_dim = lang_model.model.config.head_dim
        input_shapes = [
            ov.PartialShape([-1, -1]),
            ov.PartialShape([3, -1, -1]),
        ]
        input_shapes += (
            [
                ov.PartialShape(
                    [
                        -1,
                        lang_model.model.config.num_key_value_heads,
                        -1,
                        head_dim,
                    ]
                )
            ]
            * 2
            * num_pkv
        )
        input_shapes += [ov.PartialShape([-1, -1, input_embeds.shape[-1]])]
        __make_16bit_traceable(lang_model)

        ov_model = ov.convert_model(lang_model, example_input=example_input, input=input_shapes)
        for input, input_name in zip(ov_model.inputs, input_names):
            input.get_tensor().set_names({input_name})

        for output, output_name in zip(ov_model.outputs, output_names):
            output.get_tensor().set_names({output_name})
        patch_stateful(ov_model, 2)
        print("✅ Talker language model successfully converted")

        if quantization_config is not None:
            if not NNCF_AVAILABLE:
                raise RuntimeError("nncf is required for weight compression but not installed")
            print(f"⌛ Weights compression with {quantization_config['mode']} mode started")
            ov_model = nncf.compress_weights(ov_model, **quantization_config)
            print("✅ Weights compression finished")

        ov.save_model(ov_model, talker_lang_path)
        del ov_model
        cleanup_torchscript_cache()
        gc.collect()
        print(f"✅ Talker model conversion finished. You can find results in {output_dir}")

    # Convert talker code predictor embedding model
    if not talker_code_predictor_embedding_path.exists():
        print("⌛ Convert talker code predictor embedding model")

        def forward_wrap_code_predictor_embedding(
            self,
            input_ids: Optional[torch.LongTensor] = None,
            generation_steps: Optional[int] = None,
        ):
            all_embeddings = torch.stack([self.get_input_embeddings()[i](input_ids) for i in range(len(self.get_input_embeddings()))])
            selected_embedding = all_embeddings[generation_steps]
            return selected_embedding

        talker_code_predictor = model.talker.code_predictor.model

        talker_code_predictor._orig_forward = talker_code_predictor.forward
        talker_code_predictor.forward = types.MethodType(forward_wrap_code_predictor_embedding, talker_code_predictor)

        __make_16bit_traceable(talker_code_predictor.get_input_embeddings())
        ov_model = ov.convert_model(
            talker_code_predictor,
            example_input={
                "input_ids": torch.ones([2, 2], dtype=torch.int64),
                "generation_steps": torch.tensor(1, dtype=torch.long),
            },
        )
        ov.save_model(ov_model, talker_code_predictor_embedding_path)
        del ov_model
        cleanup_torchscript_cache()
        gc.collect()
        talker_code_predictor.forward = talker_code_predictor._orig_forward
        print("✅ Talker Code Predictor Embedding model successfully converted")

    # Convert Talker Code Predictor model
    if not talker_code_predictor_path.exists():
        print("⌛ Convert Talker Code Predictor model")

        def forward_wrap_code_predictor(
            self,
            input_ids: Optional[torch.LongTensor] = None,
            attention_mask: Optional[torch.Tensor] = None,
            position_ids: Optional[torch.LongTensor] = None,
            past_key_values: Optional[list[torch.FloatTensor]] = None,
            inputs_embeds: Optional[torch.FloatTensor] = None,
            use_cache: Optional[bool] = None,
            output_attentions: Optional[bool] = None,
            output_hidden_states: Optional[bool] = None,
            return_dict: Optional[bool] = None,
            generation_steps: Optional[int] = None,
            **kwargs,
        ):
            if past_key_values is not None:
                past_key_values = DynamicCache.from_legacy_cache(past_key_values)

            if inputs_embeds is not None:
                inputs_embeds = self.small_to_mtp_projection(inputs_embeds)

            outputs = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                position_ids=position_ids,
                past_key_values=past_key_values,
                inputs_embeds=inputs_embeds,
                use_cache=use_cache,
                output_attentions=output_attentions,
                output_hidden_states=True,
                return_dict=return_dict,
                **kwargs,
            )
            if past_key_values is not None:
                outputs["past_key_values"] = outputs["past_key_values"].to_legacy_cache()

            hidden_states = outputs.last_hidden_state

            all_logits = torch.stack([head(hidden_states) for head in self.lm_head])
            logits = all_logits[generation_steps]

            output = (logits, outputs.hidden_states[0], outputs.past_key_values)
            return output

        code_predictor_model = model.talker.code_predictor
        patch_cos_sin_cached_fp32(code_predictor_model)
        if hasattr(code_predictor_model, "model"):
            patch_cos_sin_cached_fp32(code_predictor_model.model)
        num_pkv = code_predictor_model.model.config.num_hidden_layers

        code_predictor_model._orig_forward = code_predictor_model.forward
        code_predictor_model.forward = types.MethodType(forward_wrap_code_predictor, code_predictor_model)

        head_dim = code_predictor_model.model.config.head_dim
        pkv_shape = (
            2,
            code_predictor_model.model.config.num_key_value_heads,
            2,
            head_dim,
        )

        cache_position = torch.arange(2, 4)
        position_ids = cache_position.view(1, -1)  # Code predictor uses 2D position_ids

        embedding_dim = config.talker_config.hidden_size  # 2048
        input_embeds = torch.randn((2, 2, embedding_dim))
        attention_mask = torch.ones([2, 4], dtype=torch.long)
        generation_steps = torch.tensor(1, dtype=torch.long)

        input_names = ["attention_mask", "position_ids"]
        output_names = ["logits", "mid_residual_hiddens"]
        past_key_values = []
        for i in range(num_pkv):
            kv = [torch.randn(pkv_shape) for _ in range(2)]
            past_key_values.append(kv)
            input_names.extend([f"past_key_values.{i}.key", f"past_key_values.{i}.value"])
            output_names.extend([f"present.{i}.key", f"present.{i}.value"])
        input_names.extend(["inputs_embeds", "generation_steps"])

        example_input = {
            "inputs_embeds": input_embeds,
            "attention_mask": attention_mask,
            "position_ids": position_ids,
            "past_key_values": past_key_values,
            "generation_steps": generation_steps,
        }

        input_shapes = [
            ov.PartialShape([-1, -1]),  # attention_mask
            ov.PartialShape([-1, -1]),  # position_ids (2D for code predictor)
        ]
        input_shapes += (
            [
                ov.PartialShape(
                    [
                        -1,
                        code_predictor_model.model.config.num_key_value_heads,
                        -1,
                        head_dim,
                    ]
                )
            ]
            * 2
            * num_pkv
        )
        input_shapes += [
            ov.PartialShape([-1, -1, config.talker_config.hidden_size]),  # inputs_embeds with embedding_dim (2048)
            ov.PartialShape([]),  # generation_steps (scalar)
        ]

        __make_16bit_traceable(code_predictor_model)

        ov_model = ov.convert_model(code_predictor_model, example_input=example_input, input=input_shapes)
        for input, input_name in zip(ov_model.inputs, input_names):
            input.get_tensor().set_names({input_name})

        for output, output_name in zip(ov_model.outputs, output_names):
            output.get_tensor().set_names({output_name})

        patch_stateful(ov_model, 2)
        print("✅ Talker Code Predictor model successfully converted")

        if quantization_config is not None:
            if not NNCF_AVAILABLE:
                raise RuntimeError("nncf is required for weight compression but not installed")
            print(f"⌛ Weights compression with {quantization_config['mode']} mode started")
            ov_model = nncf.compress_weights(ov_model, **quantization_config)
            print("✅ Weights compression finished")

        ov.save_model(ov_model, talker_code_predictor_path)
        del ov_model
        cleanup_torchscript_cache()
        gc.collect()
        print(f"✅ Talker Code Predictor model conversion finished. You can find results in {output_dir}")

    # Convert Speaker Encoder model (only for base model type)
    if config.tts_model_type == "base" and model.speaker_encoder is not None:
        if not speaker_encoder_path.exists():
            print("⌛ Convert Speaker Encoder model")
            __make_16bit_traceable(model.speaker_encoder)

            mel_dim = config.speaker_encoder_config.mel_dim
            ov_model = ov.convert_model(
                model.speaker_encoder,
                example_input=torch.randn([1, 100, mel_dim], dtype=torch.float32),
                input=[ov.PartialShape([1, -1, mel_dim])],
            )
            ov.save_model(ov_model, speaker_encoder_path)
            del ov_model
            cleanup_torchscript_cache()
            gc.collect()
            print("✅ Speaker Encoder model successfully converted")

    # Convert Speech Tokenizer (if present in the checkpoint)
    model_id_path = Path(model_id)
    if model_id_path.exists() and model_id_path.is_dir():
        model_local_path = model_id_path
    elif use_local_dir:
        model_local_path = Path(ckpt)
    else:
        from huggingface_hub import try_to_load_from_cache

        cached_config = try_to_load_from_cache(model_id, "speech_tokenizer/config.json")
        if cached_config and cached_config != "_CACHED_NO_EXIST":
            model_local_path = Path(cached_config).parent.parent
        else:
            model_local_path = Path(
                snapshot_download(model_id, allow_patterns=["speech_tokenizer/**", "*.json", "*.txt"], ignore_patterns=["*.safetensors", "*.bin"])
            )

    speech_tokenizer_dir = model_local_path / "speech_tokenizer"
    speech_tokenizer_ov_dir = output_dir / "speech_tokenizer"

    if speech_tokenizer_dir.exists():
        print(f"✓ Found speech tokenizer at {speech_tokenizer_dir}")
        convert_speech_tokenizer(str(speech_tokenizer_dir), speech_tokenizer_ov_dir, use_local_dir=use_local_dir)
    else:
        print("ℹ️ No speech tokenizer found in model. Using PyTorch version during inference.")

    del model
    gc.collect()


def convert_speech_tokenizer(model_id, output_dir, use_local_dir=False):
    """
    Convert Qwen3-TTS speech tokenizer (encoder and decoder) to OpenVINO format.

    Args:
        model_id: HuggingFace model ID or local path to speech_tokenizer
        output_dir: Directory to save the converted models
        use_local_dir: Whether to download to local directory first
    """
    from huggingface_hub import snapshot_download
    from qwen_tts.core import Qwen3TTSTokenizerV2Config, Qwen3TTSTokenizerV2Model
    from transformers import AutoConfig, AutoFeatureExtractor, AutoModel

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    encoder_path = output_dir / SPEECH_TOKENIZER_ENCODER_NAME
    decoder_path = output_dir / SPEECH_TOKENIZER_DECODER_NAME

    if encoder_path.exists() and decoder_path.exists():
        print(f"✅ Speech tokenizer already converted. You can find results in {output_dir}")
        return

    print("⌛ Speech tokenizer conversion started. Be patient, it may take some time.")
    print("⌛ Load Speech tokenizer model")

    # Register config and model
    AutoConfig.register("qwen3_tts_tokenizer_12hz", Qwen3TTSTokenizerV2Config)
    AutoModel.register(Qwen3TTSTokenizerV2Config, Qwen3TTSTokenizerV2Model)

    if use_local_dir:
        ckpt = Path(output_dir) / "speech_tokenizer_ckpt"
        if not ckpt.exists():
            snapshot_download(model_id, local_dir=ckpt, force_download=True)
    else:
        ckpt = model_id

    # Load model
    tokenizer_model = AutoModel.from_pretrained(ckpt, torch_dtype=torch.float32)
    tokenizer_model.eval()

    # Save feature extractor
    feature_extractor = AutoFeatureExtractor.from_pretrained(ckpt)
    feature_extractor.save_pretrained(output_dir)

    # Save config
    tokenizer_model.config.save_pretrained(output_dir)

    print("✅ Speech tokenizer model successfully loaded")

    # Convert encoder (MimiModel)
    if not encoder_path.exists():
        print("⌛ Convert speech tokenizer encoder")
        encoder = tokenizer_model.encoder

        class EncoderWrapper(torch.nn.Module):
            def __init__(self, encoder, valid_num_quantizers):
                super().__init__()
                self.encoder = encoder
                self.valid_num_quantizers = valid_num_quantizers

            def forward(self, input_values):
                encoded = self.encoder.encode(input_values=input_values, return_dict=True)
                audio_codes = encoded.audio_codes[:, : self.valid_num_quantizers]
                return audio_codes

        encoder_wrapper = EncoderWrapper(encoder, tokenizer_model.encoder_valid_num_quantizers)

        # Example input: [batch=1, channels=1, seq_len=24000] (1 second at 24kHz)
        example_input = torch.randn([1, 1, 24000], dtype=torch.float32)

        __make_16bit_traceable(encoder_wrapper)
        ov_model = ov.convert_model(
            encoder_wrapper,
            example_input=example_input,
            input=[ov.PartialShape([1, 1, -1])],  # dynamic sequence length
        )

        ov_model.inputs[0].get_tensor().set_names({"input_values"})
        ov_model.outputs[0].get_tensor().set_names({"audio_codes"})

        ov.save_model(ov_model, encoder_path)
        del ov_model
        cleanup_torchscript_cache()
        gc.collect()
        print("✅ Speech tokenizer encoder successfully converted")

    # Convert decoder
    if not decoder_path.exists():
        print("⌛ Convert speech tokenizer decoder")
        decoder = tokenizer_model.decoder

        # Patch masking_utils to use trace-compatible implementations.
        # transformers 4.57+ uses torch.vmap in create_causal_mask /
        # create_sliding_window_causal_mask, which is incompatible with
        # torch.jit.trace. Provide simple replacements producing identical masks.
        import transformers.masking_utils as _masking_utils

        _orig_causal = _masking_utils.create_causal_mask
        _orig_sliding = getattr(_masking_utils, "create_sliding_window_causal_mask", None)

        def _simple_causal_mask(**kwargs):
            input_embeds = kwargs["input_embeds"]
            batch_size, seq_len = input_embeds.shape[0], input_embeds.shape[1]
            dtype = input_embeds.dtype
            mask = torch.triu(
                torch.full((seq_len, seq_len), torch.finfo(dtype).min, dtype=dtype, device=input_embeds.device),
                diagonal=1,
            )
            return mask.unsqueeze(0).unsqueeze(0).expand(batch_size, 1, -1, -1)

        def _simple_sliding_window_causal_mask(**kwargs):
            config = kwargs["config"]
            input_embeds = kwargs["input_embeds"]
            batch_size, seq_len = input_embeds.shape[0], input_embeds.shape[1]
            dtype = input_embeds.dtype
            window_size = getattr(config, "sliding_window", None) or 72
            mask = torch.triu(
                torch.full((seq_len, seq_len), torch.finfo(dtype).min, dtype=dtype, device=input_embeds.device),
                diagonal=1,
            )
            sliding_mask = torch.tril(
                torch.full((seq_len, seq_len), torch.finfo(dtype).min, dtype=dtype, device=input_embeds.device),
                diagonal=-(window_size),
            )
            mask = mask + sliding_mask
            return mask.unsqueeze(0).unsqueeze(0).expand(batch_size, 1, -1, -1)

        _masking_utils.create_causal_mask = _simple_causal_mask
        if _orig_sliding:
            _masking_utils.create_sliding_window_causal_mask = _simple_sliding_window_causal_mask

        try:

            class DecoderWrapper(torch.nn.Module):
                def __init__(self, decoder):
                    super().__init__()
                    self.decoder = decoder

                def forward(self, audio_codes):
                    codes_transposed = audio_codes.transpose(1, 2)
                    wav = self.decoder(codes_transposed)
                    return wav.squeeze(1)

            decoder_wrapper = DecoderWrapper(decoder)

            num_quantizers = tokenizer_model.config.decoder_config.num_quantizers
            # Trace at 325 tokens = chunk_size(300) + left_context(25), matching chunked_decode
            example_input = torch.randint(0, 2048, [1, 325, num_quantizers], dtype=torch.long)

            traced = torch.jit.trace(decoder_wrapper, example_input)
            ov_model = ov.convert_model(
                traced,
                example_input=example_input,
                input=[ov.PartialShape([1, -1, num_quantizers])],
            )

            ov_model.inputs[0].get_tensor().set_names({"audio_codes"})
            ov_model.outputs[0].get_tensor().set_names({"audio_values"})

            ov.save_model(ov_model, decoder_path)
            del ov_model, traced
            cleanup_torchscript_cache()
            gc.collect()
            print("✅ Speech tokenizer decoder successfully converted")
        finally:
            _masking_utils.create_causal_mask = _orig_causal
            if _orig_sliding:
                _masking_utils.create_sliding_window_causal_mask = _orig_sliding

    del tokenizer_model
    gc.collect()
    print(f"✅ Speech tokenizer conversion finished. You can find results in {output_dir}")
