import torch

import comfy.model_management
from comfy.nodes.common import MAX_RESOLUTION


class EmptyMochiLatentVideo:
    def __init__(self):
        self.device = comfy.model_management.intermediate_device()

    @classmethod
    def INPUT_TYPES(s):
        return {"required": {"width": ("INT", {"default": 848, "min": 16, "max": MAX_RESOLUTION, "step": 16}),
                             "height": ("INT", {"default": 480, "min": 16, "max": MAX_RESOLUTION, "step": 16}),
                             "length": ("INT", {"default": 25, "min": 7, "max": MAX_RESOLUTION, "step": 6}),
                             "batch_size": ("INT", {"default": 1, "min": 1, "max": 4096})}}

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "generate"

    CATEGORY = "latent/mochi"

    def generate(self, width, height, length, batch_size=1):
        latent = torch.zeros([batch_size, 12, ((length - 1) // 6) + 1, height // 8, width // 8], device=self.device)
        return ({"samples": latent},)


NODE_CLASS_MAPPINGS = {
    "EmptyMochiLatentVideo": EmptyMochiLatentVideo,
}
