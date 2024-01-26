import asyncio, logging, typing
from functools import wraps
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session
from database import models

from time import time
from io import BytesIO
from PIL import Image

from aiogram import Bot
from aiogram.utils.text_decorations import markdown_decoration as md
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup, Message, CallbackQuery, BufferedInputFile

from functional.sd_api import WebUIApi, WebUIApiResult, APIQueue, StyleFactory
from functional.api_models import txt2img_params, txt2img_sdupscale_params, img2img_params

from .shared import ImageToBytes, KBCustom, RoundTo8, ConvertRatioToSize, get_user, clamp
from .processors import default_processor, txt2img_processor, txt2img_sdupscale_processor, img2img_processor
from . import errors

from callbacks import models as cb_models
from functional.settings_router import SettingsMaster




logger = logging.getLogger("telebot")
api = WebUIApi("", "") #configured in app.py
queue = APIQueue()
styles = StyleFactory()


IMAGE_BASE_SIZE = RoundTo8(512)
IMAGE_KEYBOARD = KBCustom(["↪️ Повтор","📜 DeepBooru"],
                          [cb_models.ImageOptions(mode="sameprompt").pack(),
                           cb_models.ImageOptions(mode="deepboru").pack()],2)


############
# Commands #
############
async def start_command(msg:Message, db:Session):
    user = get_user(db, msg.from_user.id) #register if not exists

    # try:
    #     await queue.put(user.telegram_id, asyncio.sleep(1))
    #     # await add_request(user.telegram_id, asyncio.sleep(1))
    #     # await add_request(user.telegram_id, asyncio.sleep(1))
    # except Exception as E:
    #     await msg.answer(f"Error: {E}")
    #     raise E
    #     return


    await msg.answer("Hello!")




async def any_msg(msg:Message, db:Session):
    user = get_user(db, msg.from_user.id)
    settings = user.settings

    text = msg.text or msg.caption or ""
    if len(text) < 1:
        await msg.answer("Please, provide text for generation")

    style = styles.stylize(settings.quality_tag, text)

    if not settings.enable_hr:
        params = txt2img_params()
    else:
        params = txt2img_sdupscale_params()

    width, height = ConvertRatioToSize(IMAGE_BASE_SIZE, settings.aspect_x, settings.aspect_y)
    params.width = width
    params.height = height
    params.prompt = style.positive
    params.negative_prompt = style.negative
    params.steps = settings.steps
    params.batch_size = settings.n_iter
    params.sampler_name = settings.sampler

    update_message = await msg.answer(f"Placed in queue: `{queue.human_size()}`", parse_mode="MarkdownV2")

    if isinstance(params, txt2img_sdupscale_params):
        processor = txt2img_sdupscale_processor(api, queue, params, initial_message=update_message)
    elif isinstance(params, txt2img_params):
        processor = txt2img_processor(api, queue, params, initial_message=update_message)
    

    async def proc_end(result: WebUIApiResult):
        execution_time = processor.get_process_time()
        await processor.msg_update(f"Done in `{int(execution_time)}` seconds")
        if not result:
            await processor.msg_update("Error\. No data from server")
            return
        markup = InlineKeyboardMarkup(inline_keyboard=IMAGE_KEYBOARD)
        for it, img in enumerate(result.images):
            seed = result.info['all_seeds'][it]
            caption = f"`{style.full_clear}`"
        
            await msg.answer_document(document=BufferedInputFile(ImageToBytes(img), f"{seed}.png"),caption=caption, parse_mode="MarkdownV2", reply_markup=markup)
            img.close()

    processor.set_end_func(proc_end)

    try:
        await processor.to_queue(user.telegram_id)
    except errors.MaxQueueReached:
        await update_message.edit_text("You reached queue limit. Please wait before using it again")
        logger.info(f"User {msg.from_user.full_name} with ID:[{msg.from_user.id}] reached queue limit")



async def image_reaction(msg: CallbackQuery, callback_data: cb_models.ImageOptions, db: Session, bot: Bot):
    user = get_user(db, msg.from_user.id)
    settings = user.settings
    mode = callback_data.mode

    image = msg.message.document
    if msg.message.photo and len(msg.message.photo > 0):
        image = msg.message.photo[0]

    text = msg.message.text or msg.message.caption or ""

    style = styles.stylize(settings.quality_tag, text)

    with BytesIO() as file_in_io:
        await bot.download(image, destination=file_in_io)
        file_in_io.seek(0)
        with Image.open(file_in_io) as pil_img:
            width, height = pil_img.size
            width = RoundTo8(width)
            height = RoundTo8(height)

            await msg.answer()

            if mode == "upscale":
                params = img2img_params()
                params.width = width
                params.height = height
                params.prompt = style.positive
                params.negative_prompt = style.negative
                params.init_images = [pil_img.copy()]
                params.script_name = "SD Upscale"
                params.script_args=["_", 64, "R-ESRGAN 4x+ Anime6B", 2]

                update_message = await msg.message.answer(f"Placed in queue: `{queue.human_size()}`", parse_mode="MarkdownV2")
                processor = img2img_processor(api, queue, params, initial_message=update_message)

                async def proc_end(result: WebUIApiResult):
                    assert result
                    await processor.msg_update(f"Done in `{int(processor.get_process_time())}` seconds")
                    markup = InlineKeyboardMarkup(inline_keyboard=IMAGE_KEYBOARD)
                    for it, img in enumerate(result.images):
                        await msg.message.answer_document(document=BufferedInputFile(ImageToBytes(img), f"{result.info['all_seeds'][it]}.png"),caption=f"`{style.full_clear}`", parse_mode="MarkdownV2", reply_markup=markup)
                        img.close()

                processor.set_end_func(proc_end)

                try: await processor.to_queue(user.telegram_id)
                except errors.MaxQueueReached:
                    await update_message.edit_text("You reached queue limit. Please wait before using it again")
                    logger.info(f"User {msg.from_user.full_name} with ID:[{msg.from_user.id}] reached queue limit")

            elif mode == "sameprompt":
                if not settings.enable_hr:
                    params = txt2img_params()
                else:
                    params = txt2img_sdupscale_params()

                width, height = ConvertRatioToSize(IMAGE_BASE_SIZE, settings.aspect_x, settings.aspect_y)
                params.width = width
                params.height = height
                params.prompt = style.positive
                params.negative_prompt = style.negative
                params.steps = settings.steps
                params.batch_size = settings.n_iter
                params.sampler_name = settings.sampler

                update_message = await msg.message.answer(f"Placed in queue: `{queue.human_size()}`", parse_mode="MarkdownV2")
                msg = msg.message
                
                if isinstance(params, txt2img_sdupscale_params):
                    processor = txt2img_sdupscale_processor(api, queue, params, initial_message=update_message)
                elif isinstance(params, txt2img_params):
                    processor = txt2img_processor(api, queue, params, initial_message=update_message)

                async def proc_end(result: WebUIApiResult):
                    execution_time = processor.get_process_time()
                    await processor.msg_update(f"Done in `{int(execution_time)}` seconds")
                    if not result:
                        await processor.msg_update("Error\. No data from server")
                        return
                    markup = InlineKeyboardMarkup(inline_keyboard=IMAGE_KEYBOARD)
                    for it, img in enumerate(result.images):
                        seed = result.info['all_seeds'][it]
                        caption = f"`{style.full_clear}`"
                    
                        await msg.answer_document(document=BufferedInputFile(ImageToBytes(img), f"{seed}.png"),caption=caption, parse_mode="MarkdownV2", reply_markup=markup)
                        img.close()

                processor.set_end_func(proc_end)

                try:
                    await processor.to_queue(user.telegram_id)
                except errors.MaxQueueReached:
                    await update_message.edit_text("You reached queue limit. Please wait before using it again")
                    logger.info(f"User {msg.from_user.full_name} with ID:[{msg.from_user.id}] reached queue limit")





class CommandHandler(ABC):
    def __init__(self, master: SettingsMaster, query: CallbackQuery, data: list, db: Session):
        self.master = master
        self.query = query
        self.data = data
        self.db = db
        self.user = get_user(db, query.from_user.id)
        self.settings = self.user.settings
        self.prefix = data[0]
        self.mode = data[1]

    def db_save_changes(self):
        self.db.add(self.settings)
        self.db.commit()
        self.db.refresh(self.settings)

    @abstractmethod
    async def handle(self):
        pass

class CountHandler(CommandHandler):
    async def add(self, amount: int):
        new_value = clamp(self.settings.n_iter+amount, 1, 4)
        if new_value == self.settings.n_iter:
            await self.query.answer()
            return #no need to update and save

        self.settings.n_iter = new_value
        self.db_save_changes()
        await self.menu()

    async def menu(self):
        master = self.master
        prefix = self.prefix
        kb = []
        kb.append([
            IKB(text="-2", callback_data=master.arg_pack(prefix, "add", "-2")),
            IKB(text="-1", callback_data=master.arg_pack(prefix, "add", "-1")),
            IKB(text="+1", callback_data=master.arg_pack(prefix, "add", "1")),
            IKB(text="+2", callback_data=master.arg_pack(prefix, "add", "2"))
        ])
        kb.append([master.back_button()])
        markup = InlineKeyboardMarkup(inline_keyboard=kb)
        await self.query.message.edit_text(f"Current image generation count: `{self.settings.n_iter}` / `4`", reply_markup=markup, parse_mode="MarkdownV2")

        await self.query.answer()

    async def handle(self):
        match self.mode:
            case "add":
                await self.add(amount=int(self.data[2]))
            case _:
                await self.menu()

async def count_setting(master: SettingsMaster, query: CallbackQuery, data: list, db: Session):
    await CountHandler(master, query, data, db).handle()


class RatioHandler(CommandHandler):
    async def set(self, aspect_x: float, aspect_y: float):
        if (self.settings.aspect_x, self.settings.aspect_y) == (aspect_x, aspect_y):
            self.settings.aspect_x, self.settings.aspect_y = aspect_y, aspect_x
        else:
            self.settings.aspect_x, self.settings.aspect_y = aspect_x, aspect_y
        self.db_save_changes()
    
    async def inverse(self):
        self.settings.aspect_x, self.settings.aspect_y = self.settings.aspect_y, self.settings.aspect_x
        self.db_save_changes()
    
    async def menu(self):
        kb = []
        mode_buttons = []
        for ratio in ["1/1", "16/9", "19.5/9"]:
            vx, vy = map(float, ratio.split("/"))
            if  self.settings.aspect_x <  self.settings.aspect_y:
                vx, vy = vy, vx

            true_sign = ""
            if vx ==  self.settings.aspect_x and vy ==  self.settings.aspect_y:
                true_sign = "✅ "

            mode_buttons.append(
                IKB(text=f"{true_sign}{vx} / {vy}", callback_data= self.master.arg_pack( self.prefix, "set", str(vx), str(vy)))
            )

        ax, ay = float(self.settings.aspect_x), float(self.settings.aspect_y)

        kb.append(mode_buttons)
        kb.append([IKB(text="🔀 Inverse ratios", callback_data=self.master.arg_pack(self.prefix, "inverse"))])
        kb.append([self.master.back_button()])

        markup = InlineKeyboardMarkup(inline_keyboard=kb)
        ratio = f"`{ax}` / `{ay}`"
        await self.query.message.edit_text(f"Current ratio: {ratio}", reply_markup=markup, parse_mode="MarkdownV2")

        await self.query.answer()

    async def handle(self):
        match self.mode:
            case "set":
                await self.set(aspect_x=float(self.data[2]), aspect_y=float(self.data[3]))
            case "inverse":
                await self.inverse()
        await self.menu()

async def ratio_setting(master: SettingsMaster, query: CallbackQuery, data: list, db: Session):
    await RatioHandler(master, query, data, db).handle()




class UpscaleHandler(CommandHandler):
    async def mode_switch(self):
        self.settings.enable_hr = not self.settings.enable_hr
        self.db_save_changes()

    async def menu(self):
        kb = []
        kb.append([IKB(
            text="❌ Disable" if self.settings.enable_hr else "✅ Enable", 
            callback_data=self.master.arg_pack(self.prefix, "switch"))
        ])
        kb.append([self.master.back_button()])

        markup = InlineKeyboardMarkup(inline_keyboard=kb)
        await self.query.message.edit_text(
            f'Upscale settings\. Currently upscale is {"✅ Enabled" if self.settings.enable_hr else "❌ Disabled"}', 
            reply_markup=markup, 
            parse_mode="MarkdownV2"
        )
        await self.query.answer()

    async def handle(self):
        match self.mode:
            case "switch":
                await self.mode_switch()
        await self.menu()

async def upscale_setting(master: SettingsMaster, query: CallbackQuery, data: list, db: Session):
    await UpscaleHandler(master, query, data, db).handle()
