import logging

import torch
from torch.nn import LayerNorm

from comfy import model_management
from comfy.model_patcher import ModelPatcher
from comfy.nodes.package_typing import CustomNode, InputTypes

DIFFUSION_MODEL = "diffusion_model"


class TorchCompileModel(CustomNode):
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("MODEL",),
            },
            "optional": {
                "object_patch": ("STRING", {"default": DIFFUSION_MODEL}),
                "fullgraph": ("BOOLEAN", {"default": False}),
                "dynamic": ("BOOLEAN", {"default": False}),
                "backend": ("STRING", {"default": "inductor"}),
            }
        }

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "patch"
    INFERENCE_MODE = False

    CATEGORY = "_for_testing"
    EXPERIMENTAL = True

    def patch(self, model: ModelPatcher, object_patch: str | None = DIFFUSION_MODEL, fullgraph: bool = False, dynamic: bool = False, backend: str = "inductor") -> tuple[ModelPatcher]:
        if object_patch is None:
            object_patch = DIFFUSION_MODEL
        compile_kwargs = {
            "fullgraph": fullgraph,
            "dynamic": dynamic,
            "backend": backend
        }
        if backend == "torch_tensorrt":
            compile_kwargs["options"] = {
                # https://pytorch.org/TensorRT/dynamo/torch_compile.html
                # Quantization/INT8 support is slated for a future release; currently, we support FP16 and FP32 precision layers.
                "enabled_precisions": {torch.float, torch.half}
            }
        if isinstance(model, ModelPatcher):
            m = model.clone()
            m.add_object_patch(object_patch, torch.compile(model=m.get_model_object(object_patch), **compile_kwargs))
            return (m,)
        elif isinstance(model, torch.nn.Module):
            return torch.compile(model=model, **compile_kwargs),
        else:
            logging.warning("Encountered a model that cannot be compiled")
            return model,


_QUANTIZATION_STRATEGIES = [
    "torchao",
    "quanto",
    "torchao-autoquant"
]


class QuantizeModel(CustomNode):
    @classmethod
    def INPUT_TYPES(cls) -> InputTypes:
        return {
            "required": {
                "model": ("MODEL", {}),
                "strategy": (_QUANTIZATION_STRATEGIES, {"default": _QUANTIZATION_STRATEGIES[0]})
            }
        }

    FUNCTION = "execute"
    CATEGORY = "_for_testing"
    EXPERIMENTAL = True
    INFERENCE_MODE = False

    RETURN_TYPES = ("MODEL",)

    def warn_in_place(self, model: ModelPatcher):
        logging.warning(f"Quantizing {model} this way quantizes it in place, making it insuitable for cloning. All uses of this model will be quantized.")

    def execute(self, model: ModelPatcher, strategy: str = _QUANTIZATION_STRATEGIES[0]) -> tuple[ModelPatcher]:
        model = model.clone()
        unet = model.get_model_object("diffusion_model")
        # todo: quantize quantizes in place, which is not desired

        # default exclusions
        always_exclude_these = {
            "time_embedding.",
            "add_embedding.",
            "time_in.in",
            "txt_in",
            "vector_in.in",
            "img_in",
            "guidance_in.in",
            "final_layer",
        }
        if strategy == "quanto":
            logging.warning(f"Quantizing {model} will produce poor results due to Optimum's limitations")
            self.warn_in_place(model)
            from optimum.quanto import quantize, qint8  # pylint: disable=import-error
            exclusion_list = [
                name for name, module in unet.named_modules() if isinstance(module, LayerNorm) and module.weight is None
            ]
            quantize(unet, weights=qint8, activations=qint8, exclude=exclusion_list)
            _in_place_fixme = unet
        elif "torchao" in strategy:
            from torchao.quantization import quantize_, int8_dynamic_activation_int8_weight, autoquant  # pylint: disable=import-error
            model = model.clone()
            self.warn_in_place(model)
            unet = model.get_model_object("diffusion_model")

            def filter(module: torch.nn.Module, fqn: str) -> bool:
                return isinstance(module, torch.nn.Linear) and not any(prefix in fqn for prefix in always_exclude_these)

            if "autoquant" in strategy:
                _in_place_fixme = autoquant(unet, error_on_unseen=False)
            else:
                quantize_(unet, int8_dynamic_activation_int8_weight(), device=model_management.get_torch_device(), filter_fn=filter)
                _in_place_fixme = unet
        else:
            raise ValueError(f"unknown strategy {strategy}")

        model.add_object_patch("diffusion_model", _in_place_fixme)
        return model,


NODE_CLASS_MAPPINGS = {
    "TorchCompileModel": TorchCompileModel,
    "QuantizeModel": QuantizeModel,
}
