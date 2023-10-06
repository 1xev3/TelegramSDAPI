import aiohttp
import asyncio

import json
from PIL import Image
import io
import base64

from typing import Optional
from dataclasses import dataclass

def b64_img(image: Image):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_base64 = 'data:image/png;base64,' + str(base64.b64encode(buffered.getvalue()), 'utf-8')
    return img_base64

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
    init_images = []
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
    
class StyleFactory():
    styles = {}

    @dataclass
    class Style():
        positive: str
        negative: str

        positive_clear: str
        negative_clear: str

        @property
        def full(self) -> str:
            neg = ""
            if self.negative != "": neg = "///"+self.negative
            return f"{self.positive}{neg}"
        
        @property
        def full_clear(self) -> str:
            neg = ""
            if self.negative_clear != "": neg = "///"+self.negative_clear
            return f"{self.positive_clear}{neg}"

    def add_new(self, name:str, positive:str, negative:str):
        self.styles[name] = {
            "name": name,
            "positive": positive,
            "negative": negative
        }

    def stylize(self, style_name:str, text:str, separator = "///"):
        splited = text.split(separator)
        prompt = splited[0]
        neg_prompt = ""
        if len(splited) > 1:
            neg_prompt = splited[1]

        pos = self.styles[style_name]["positive"].format(prompt)
        neg = self.styles[style_name]["negative"].format(neg_prompt)

        return self.Style(pos, neg, prompt, neg_prompt)
        

class APIQueue():
    def __init__(self, def_limit = 4, custom_limits:dict = {}, max_tasks = 10):
        self.configure(def_limit, custom_limits, max_tasks)

    def configure(self, def_limit = 4, custom_limits:dict = {}, max_tasks = 10):
        self.limit = def_limit
        self.custom_limits = custom_limits

        self.queue = asyncio.Queue(max_tasks)
        self.counts = {}

    async def process_requests(self):
        while True:
            user_id, request = await self.queue.get()

            try:
                await request
            finally:
                if user_id in self.counts:
                    self.counts[user_id] -= 1
                    if self.counts[user_id] < 1:
                        del self.counts[user_id]
                self.queue.task_done()

    async def put(self, user_id:str, coro):
        if user_id not in self.counts:
            self.counts[user_id] = 0

        max_count = self.limit
        if user_id in self.custom_limits:
            max_count = self.custom_limits[user_id]

        if self.counts[user_id] > max_count:
            raise RuntimeError("Максимальное количество одновременных запросов достигнуто")
        
        self.counts[user_id] += 1
        await self.queue.put((user_id, coro))



@dataclass
class WebUIApiResult:
    images: list[Image.Image]
    parameters: dict
    info: dict
        
    @property
    def image(self) -> Image.Image:
        return self.images[0]


class WebUIApi():
    def __init__(self, host, port):
        self.configure(host,port)

    def configure(self, host, port):
        self.host = host
        self.port = port
        self.baseurl = f'http://{host}:{port}/sdapi/v1'
        self.timeout = aiohttp.ClientTimeout(total=9999)

    async def _to_api_result(self, response) -> WebUIApiResult:
        if response.status != 200:
            raise RuntimeError(response.status, await response.text())
        
        r = await response.json()
        images = []
        if 'images' in r.keys():
            images = [Image.open(io.BytesIO(base64.b64decode(i))) for i in r['images']]
        elif 'image' in r.keys():
            images = [Image.open(io.BytesIO(base64.b64decode(r['image'])))]
        
        info = ''
        if 'info' in r.keys():
            try:
                info = json.loads(r['info'])
            except:
                info = r['info']
        elif 'html_info' in r.keys():
            info = r['html_info']

        parameters = ''
        if 'parameters' in r.keys():
            parameters = r['parameters']

        return WebUIApiResult(images, parameters, info)
    
    async def txt2img(self, params: txt2img_params) -> WebUIApiResult:
        payload = params.to_dict()

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url=f'{self.baseurl}/txt2img', json=payload) as response:
                return await self._to_api_result(response)


async def main():
    t = WebUIApi("localhost", "7860")

    params = txt2img_params()
    params.prompt = "programmer"
    result = await t.txt2img(params)

    img = result.image
    img.show()

# asyncio.run(main())
    


t = WebUIApi("localhost", "7860")

params = txt2img_params()
params.prompt = "programmer"


import asyncio

async def main():
    queue = asyncio.Queue()

    async def process():
        while True:
            message = await queue.get()
            print(message)
            result = await t.txt2img(params)
            result.show()

            # Обрабатываем сообщение
            # await asyncio.sleep(1)
            queue.task_done()

    asyncio.create_task(process())

    for i in range(3):
        await queue.put(f"hello {i}")



if __name__ == "__main__":
    asyncio.run(main())