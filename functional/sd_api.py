import aiohttp, requests
import asyncio


import json, io, base64, logging
from PIL import Image

from typing import Coroutine, Optional
from pydantic import ValidationError
from dataclasses import dataclass

from .api_models import txt2img_params, txt2img_sdupscale_params, img2img_params, SDModel, SDProgress

from . import errors


logger = logging.getLogger("telebot")


class StyleFactory():
    def __init__(self):
        self.styles = {}
        self.quality_tags: self.Style("", "", "", "")
    

    @dataclass
    class Style():
        #full prompts
        positive: str
        negative: str

        #without added style
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
        
    def set_quality_tags(self, positive:str, negative:str):
        self.quality_tags = self.Style(positive, negative, "", "")

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

        #since telegram has limit in caption with 1024
        prompt = prompt[:512] if len(prompt) > 512 else prompt
        neg_prompt = neg_prompt[:510] if len(neg_prompt) > 510 else neg_prompt

        pos = self.styles[style_name]["positive"].format(prompt)
        neg = self.styles[style_name]["negative"].format(neg_prompt)

        return self.Style(pos, neg, prompt, neg_prompt)


class APIQueue():
    def __init__(self, def_limit = 4, custom_limits:dict = {}, max_tasks = 10, update_sleep = 2):
        self.busy = False
        self.configure(def_limit, custom_limits, max_tasks, update_sleep)

    def configure(self, def_limit = 4, custom_limits:dict = {}, max_tasks = 10, update_sleep = 2):
        self.limit = def_limit
        self.custom_limits = custom_limits
        self.update_sleep = update_sleep

        self.queue = asyncio.Queue(max_tasks)
        self.counts = {}

    @dataclass
    class Params():
        uid: str
        func: Coroutine
        update_func: Coroutine = None
        end_func: Coroutine = None

    def size(self) -> int:
        return self.queue.qsize()
    
    def human_size(self) -> int:
        count = self.size()+1
        if self.busy:
            count += 1
        return count
        
    async def __get_one(self) -> Params:
        return await self.queue.get()

    #special update coroutine
    async def __process_update(self, update_coro):
        while True:
            try:
                await update_coro() #create new coro and run it
            except Exception as E:
                logger.error(f"Error occured in SD_API: {E}")
                break
            
            finally:
                await asyncio.sleep(self.update_sleep) 
            

    async def process_requests(self):
        update_task = None

        while True:
            params = await self.__get_one()
            uid = params.uid
            coro = params.func
            update_coro = params.update_func
            end_func = params.end_func

            # Update worker
            if update_coro and update_task is None:
                update_task = asyncio.create_task(self.__process_update(update_coro))

            try:
                self.busy = True
                result = await coro()
            finally:
                self.busy = False
                self.queue.task_done() #end task

                #check user counter
                if uid in self.counts:
                    self.counts[uid] -= 1
                    if self.counts[uid] < 1:
                        del self.counts[uid]

                if update_task is not None:
                    update_task.cancel()
                    update_task = None

                if end_func is not None:
                    await end_func(result)

    async def put(self, params:Params):
        uid = params.uid

        if uid not in self.counts:
            self.counts[uid] = 0

        max_count = self.limit
        if uid in self.custom_limits:
            max_count = self.custom_limits[uid]

        if self.counts[uid] >= max_count:
            raise errors.MaxQueueReached("Максимальное количество одновременных запросов достигнуто")
        
        self.counts[uid] += 1
        await self.queue.put(params)



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
        self.models: list[SDModel] = []
        self.upscalers = []
        self.configure(host,port)

    def configure(self, host, port):
        self.host = host
        self.port = port
        self.baseurl = f'http://{host}:{port}/sdapi/v1'
        self.timeout = aiohttp.ClientTimeout(total=9999)
            
    def __recieve_models(self) -> list[SDModel]:
        response = requests.get(url=f'{self.baseurl}/sd-models')
        if response.status_code != 200:
            raise RuntimeError(f"Error getting models. Status: {response.status_code} {response.text}")
        models = response.json()
        result = []
        for v in models:
            try:
                model = SDModel(
                    title=v["title"],
                    mdl_name=v["model_name"],
                    hash=v["hash"],
                    sha256=v["sha256"],
                    filename=v["filename"],
                    config=v["config"]
                )
                result.append(model)
            except ValidationError as E:
                logger.error(f"Error validating model {v['title'] or 'Undefined'}. Maybe model broken?\n{E}")
        return result

    #TODO    
    def __recieve_samplers(self) -> list:
        pass
    
    def update_models(self):
        self.models = self.__recieve_models()

    def get_models(self) -> list[SDModel]:
        return self.models

        
        


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
    
    async def get_progress(self, skip_current_image = True) -> SDProgress:
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(url=f'{self.baseurl}/progress',params={"skip_current_image": str(skip_current_image)}) as response:
                return SDProgress( **(await response.json()) )
            
    async def get_upscalers(self):
        if len(self.upscalers) < 1:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(url=f'{self.baseurl}/upscalers') as response:
                    self.upscalers = await response.json()
                    return self.upscalers
        else:
            return self.upscalers
    
    async def upscaler_by_name(self, name):
        upscaler_id = -1
        ids = 0
        for v in await self.get_upscalers():
            if v["name"] == name:
                upscaler_id = ids
                break
            ids+=1
        return upscaler_id

    
    async def txt2img(self, params: txt2img_params) -> WebUIApiResult:
        payload = params.to_dict()

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url=f'{self.baseurl}/txt2img', json=payload) as response:
                return await self._to_api_result(response)
            
    async def img2img(self, params: img2img_params) -> WebUIApiResult:
        payload = params.to_dict()

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url=f'{self.baseurl}/img2img', json=payload) as response:
                return await self._to_api_result(response)
            
    async def txt2img_sdupscale(self, params: txt2img_sdupscale_params) -> WebUIApiResult:
        response = await self.txt2img(params)

        upscaler_id = await self.upscaler_by_name(params.upscaler)
        if upscaler_id < 0:
            logger.error("[txt2img_sdupscale] Argument upscaler is invalid!")
            raise ValueError("[txt2img_sdupscale] Argument upscaler is invalid!")

        own_images = []
        for img in response.images:
            pr = img2img_params()
            pr.init_images = [img]
            pr.prompt = "best quality, good quality, hdr, masterpiece" #params.prompt
            pr.negative_prompt = "(worst quality, low quality:1.4), (blurry:1.2), (lowres), (deformed, distorted, disfigured:1.3), (bad hands:1.1), jpeg compression, bad image" #params.negative_prompt
            pr.steps = params.steps
            pr.width = params.width
            pr.height = params.height
            pr.batch_size = 3
            pr.denoising_strength = 0.25
            pr.cfg_scale = params.cfg_scale

            pr.script_name = "SD Upscale"
            pr.script_args = ["_", params.overlap, upscaler_id, params.upscale_factor]

            # for k in dir(pr):
            #     if not k.startswith("__"):
            #         print("\t ", k, str(getattr(pr,k)))


            img2img_result = await self.img2img(pr)
            own_images.append(img2img_result.image)

        return WebUIApiResult(own_images,response.parameters,response.info)
