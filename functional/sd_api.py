import aiohttp, requests
import asyncio


import json
from PIL import Image
import io
import base64

from typing import Coroutine, Optional
from dataclasses import dataclass

from .api_models import txt2img_params, img2img_params, SDModel, SDProgress

def b64_img(image: Image):
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    img_base64 = 'data:image/png;base64,' + str(base64.b64encode(buffered.getvalue()), 'utf-8')
    return img_base64


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
    def __init__(self, def_limit = 4, custom_limits:dict = {}, max_tasks = 10, update_sleep = 2):
        self.configure(def_limit, custom_limits, max_tasks, update_sleep)

    @dataclass
    class Params():
        user_id: str
        func: Coroutine
        update_func: Coroutine = None
        end_func: Coroutine = None

    def configure(self, def_limit = 4, custom_limits:dict = {}, max_tasks = 10, update_sleep = 2):
        self.limit = def_limit
        self.custom_limits = custom_limits
        self.update_sleep = update_sleep

        self.queue = asyncio.Queue(max_tasks)
        self.counts = {}
        
    async def __get_one(self) -> Params:
        return await self.queue.get()

    #special update coroutine
    async def __process_update(self, update_coro):
        while True:
            try:
                await update_coro() #create new coro and run it
            except Exception as E:
                print(f"[ERROR] Error occured in SD_API: {E}")
                break
            
            finally:
                await asyncio.sleep(self.update_sleep) 
            

    async def process_requests(self):
        update_task = None

        while True:
            params = await self.__get_one()
            user_id = params.user_id
            coro = params.func
            update_coro = params.update_func
            end_func = params.end_func

            # Если есть задача update_coro, создаем ее только один раз
            if update_coro and update_task is None:
                update_task = asyncio.create_task(self.__process_update(update_coro))

            try:
                await coro
            finally:
                if user_id in self.counts:
                    self.counts[user_id] -= 1
                    if self.counts[user_id] < 1:
                        del self.counts[user_id]
                self.queue.task_done()

                if update_task is not None:
                    update_task.cancel()
                    update_task = None

                if end_func is not None:
                    await end_func

    async def put(self, params:Params):
        user_id = params.user_id

        if user_id not in self.counts:
            self.counts[user_id] = 0

        max_count = self.limit
        if user_id in self.custom_limits:
            max_count = self.custom_limits[user_id]

        if self.counts[user_id] >= max_count:
            raise RuntimeError("Максимальное количество одновременных запросов достигнуто")
        
        self.counts[user_id] += 1
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
            result.append(SDModel(
                title=v["title"],
                model_name=v["model_name"],
                hash=v["hash"],
                sha256=v["sha256"],
                filename=v["filename"],
                config=v["config"]
            ))
        return result
    
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
            async with session.get(url=f'{self.baseurl}/progress',params={"skip_current_image": "True"}) as response:
                return SDProgress( **(await response.json()) )
    
    async def txt2img(self, params: txt2img_params) -> WebUIApiResult:
        payload = params.to_dict()

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url=f'{self.baseurl}/txt2img', json=payload) as response:
                return await self._to_api_result(response)