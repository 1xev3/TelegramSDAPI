from pydantic import BaseModel, Field
from typing import Optional

class SDModel(BaseModel):
    title: str
    mdl_name: str
    hash: str
    sha256: str
    filename: str
    config: Optional[str] #?


class SDProgress(BaseModel):
    progress: float = 0
    eta_relative: float = 0
    state: Optional[dict]
    current_image: Optional[str]
    text_info: Optional[str] = None


class txt2img_params():
    prompt = ""
    negative_prompt = ""
    styles = []
    seed = -1
    subseed = -1
    subseed_strength = 0
    seed_resize_from_h = -1
    seed_resize_from_w = -1
    sampler_name = "Euler a"
    batch_size = 1
    n_iter = 1
    steps = 22
    cfg_scale = 7
    width = 512
    height = 512
    restore_faces = False
    tiling = False
    do_not_save_samples = True
    do_not_save_grid = True
    eta = 0
    denoising_strength = 0
    s_min_uncond = 0
    s_churn = 0
    s_tmax = 0
    s_tmin = 0
    s_noise = 0
    override_settings = {}
    override_settings_restore_afterwards = True
    refiner_checkpoint = ""
    refiner_switch_at = 0
    disable_extra_networks = False
    comments = {}
    enable_hr = False
    firstphase_width = 0
    firstphase_height = 0
    hr_scale = 2
    hr_upscaler = ""
    hr_second_pass_steps = 0
    hr_resize_x = 0
    hr_resize_y = 0
    hr_checkpoint_name = ""
    hr_sampler_name = ""
    hr_prompt = ""
    hr_negative_prompt = ""
    sampler_index = "Euler"
    script_name = ""
    script_args = []
    send_images = True
    save_images = False
    alwayson_scripts = {}

    def to_dict(self):
        return {attr: getattr(self, attr) for attr in dir(self) if not callable(getattr(self, attr)) and not attr.startswith("__")}

class img2img_params():
    prompt = ""
    negative_prompt = ""
    styles = []
    seed = -1
    subseed = -1
    subseed_strength = 0
    seed_resize_from_h = -1
    seed_resize_from_w = -1
    sampler_name = "Euler a"
    batch_size = 1
    n_iter = 1
    steps = 22
    cfg_scale = 7
    width = 512
    height = 512
    restore_faces = False
    tiling = False
    do_not_save_samples = True
    do_not_save_grid = True
    eta = 0
    denoising_strength = 0.4
    s_min_uncond = 0
    s_churn = 0
    s_tmax = 0
    s_tmin = 0
    s_noise = 0
    override_settings = {}
    override_settings_restore_afterwards = True
    refiner_checkpoint = ""
    refiner_switch_at = 0
    disable_extra_networks = False
    comments = {}
    init_images: list[str] = []
    resize_mode = 0
    image_cfg_scale = 0
    mask = ""
    mask_blur_x = 4
    mask_blur_y = 4
    mask_blur = 0
    inpainting_fill = 0
    inpaint_full_res = True
    inpaint_full_res_padding = 0
    inpainting_mask_invert = 0
    initial_noise_multiplier = 0
    latent_mask = ""
    sampler_index = "Euler"
    include_init_images = False
    script_name = ""
    script_args = []
    send_images = True
    save_images = False
    alwayson_scripts = {}

    def to_dict(self):
        return {attr: getattr(self, attr) for attr in dir(self) if not callable(getattr(self, attr)) and not attr.startswith("__")}
    