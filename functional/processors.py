from functional.sd_api import txt2img_params, txt2img_sdupscale_params, img2img_params, StyleFactory, WebUIApi, APIQueue
from time import time

from aiogram import types
from aiogram.utils.text_decorations import markdown_decoration as md


class default_processor():
    def __init__(self, queue: APIQueue, process_func = None, update_func = None, end_func = None):
        self.queue = queue
        self.process_func = process_func
        self.update_func = update_func
        self.end_func = end_func
    
    async def on_process(self):
        await self.process_func()
    async def on_update(self):
        await self.update_func()
    async def on_end(self, result):
        await self.end_func(result)

    #setters
    def set_process_func(self, fn):
        self.process_func = fn
    def set_update_func(self, fn):
        self.update_func = fn
    def set_end_func(self, fn):
        self.end_func = fn
    
    async def to_queue(self, uid):
        await self.queue.put( APIQueue.Params (
            uid=uid,
            func=self.on_process,
            update_func=self.on_update, #no ()! only coroutine fabric!
            end_func=self.on_end,
        ))


class queue_processor(default_processor):
    def __init__(self, api:WebUIApi, queue: APIQueue, initial_message: types.Message):
        self.initial_message = initial_message
        self.api = api
        self.start_time = None

        super().__init__(queue, None, None, None)

    #prevent message is not modified error
    async def msg_update(self, text):
        if self.initial_message.text != text:
            self.initial_message = await self.initial_message.edit_text(text, parse_mode="MarkdownV2")

    def get_process_time(self):
        return time() - self.start_time

    async def on_update(self):
        status = await self.api.get_progress()

        progress = status.progress
        negative_progress = 1 - progress
        
        waiting = (progress == 0.0)
        progress_str = f"`{int(progress*100)}\%`" if (not waiting) else "`Waiting`"
        
        count = 25
        progress_bar = f'\[{"━"*int(progress*count)}{ md.spoiler("━"*int(negative_progress*count)) }\]'

        message = f"{md.quote('Generating...')} "\
                f"{progress_str}\n"\
                f"{progress_bar if not waiting else ''}\n"
        await self.msg_update(message)


class txt2img_processor(queue_processor):
    def __init__(self, api:WebUIApi, queue: APIQueue, params:txt2img_params, initial_message: types.Message):
        self.params = params
        super().__init__(api, queue, initial_message)

    async def on_process(self):
        self.start_time = time()
        self.initial_message = await self.initial_message.answer("Generation...") #update current message to new message
        
        try:
            return await self.api.txt2img(self.params)
        except Exception as E:
            await self.msg_update(f"Error: {E}")

class txt2img_sdupscale_processor(queue_processor):
    def __init__(self, api:WebUIApi, queue: APIQueue, params:txt2img_sdupscale_params, initial_message: types.Message):
        self.params = params
        super().__init__(api, queue, initial_message)

    async def on_process(self):
        self.start_time = time()
        self.initial_message = await self.initial_message.answer("Generation...") #update current message to new message
        
        try:
            return await self.api.txt2img_sdupscale(self.params)
        except Exception as E:
            await self.msg_update(f"Error: {E}")

class img2img_processor(queue_processor):
    def __init__(self, api:WebUIApi, queue: APIQueue, params:img2img_params, initial_message: types.Message):
        self.params = params
        super().__init__(api, queue, initial_message)

    async def on_process(self):
        self.start_time = time()
        self.initial_message = await self.initial_message.answer("Generation...") #update current message to new message
        
        try:
            return await self.api.img2img(self.params)
        except Exception as E:
            await self.msg_update(f"Error: {E}")

