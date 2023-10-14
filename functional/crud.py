import asyncio, logging
from functools import wraps

from sqlalchemy.orm import Session
from database import models

from time import time
from io import BytesIO
from PIL import Image

from aiogram import Bot
from aiogram.utils.text_decorations import markdown_decoration as md
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup, Message, CallbackQuery, BufferedInputFile

from functional.sd_api import WebUIApi, WebUIApiResult, APIQueue, StyleFactory
from functional.sd_api import txt2img_params, img2img_params

from .shared import ImageToBytes, KBCustom, RoundTo8
from .processors import default_processor, txt2img_processor, img2img_processor
from . import errors

from dataclasses import dataclass

from callbacks import models as cb_models




logger = logging.getLogger("telebot")
api = WebUIApi("", "") #configured in app.py
queue = APIQueue()
styles = StyleFactory()


IMAGE_KEYBOARD = KBCustom(["⬆️ Апскейл","↪️ Повтор","♻️ Варианты","📜 DeepBooru", "✨ Стиль"],
                          [cb_models.ImageOptions(mode="upscale").pack(),
                           cb_models.ImageOptions(mode="sameprompt").pack(),
                           cb_models.ImageOptions(mode="variants").pack(),
                           cb_models.ImageOptions(mode="deepboru").pack(),
                           cb_models.ImageOptions(mode="style").pack()],2)

def get_user(db: Session, telegram_id: int) -> models.User:
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    
    #create new user
    if not user:
        logger.info(f"Created new user [{telegram_id}]")
        user = models.User(telegram_id=telegram_id)
        db.add(user)
        db.commit()
    
    return user


############
# Commands #
############
async def start_command(msg:Message, db:Session):
    user = get_user(db, msg.from_user.id) #register if not exists

    try:
        await queue.put(user.telegram_id, asyncio.sleep(1))
        await queue.put(user.telegram_id, asyncio.sleep(1))
        await queue.put(user.telegram_id, asyncio.sleep(1))
        await queue.put(user.telegram_id, asyncio.sleep(1))
        # await add_request(user.telegram_id, asyncio.sleep(1))
        # await add_request(user.telegram_id, asyncio.sleep(1))
    except Exception as E:
        await msg.answer(f"Error: {E}")
        raise E
        return


    await msg.answer("Hello!")

def settings_keyboard():
    kb = [
        [
            IKB(text="Соотношение сторон", callback_data=cb_models.MenuOptions(mode="scale").pack()), 
            IKB(text="Количество", callback_data=cb_models.MenuOptions(mode="count").pack())
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

async def config_command(msg:Message, db:Session):
    user = get_user(db, msg.from_user.id)

    markup = settings_keyboard()

    await msg.answer(f"Config for user [{msg.from_user.id}]", reply_markup=markup )

async def config_command_callaback(msg: CallbackQuery, callback_data: cb_models.MenuOptions, db: Session):
    user = get_user(db, msg.from_user.id)

    mode = callback_data.mode
    if mode == "root":
        markup = settings_keyboard()
        await msg.message.answer("Главное меню", reply_markup=markup)
    elif mode == "scale":
        markup = InlineKeyboardMarkup(inline_keyboard=KBCustom(
            ["Reverse", "Назад"],
            [
                cb_models.SetOptions(mode="scale", value="reverse").pack(),
                cb_models.MenuOptions(mode="root").pack()
            ], 
        1))
        await msg.message.answer("Scale", reply_markup=markup)

    await msg.answer()


async def any_msg(msg:Message, db:Session):
    user = get_user(db, msg.from_user.id)
    settings = user.settings

    text = msg.text or msg.caption or ""
    if len(text) < 1:
        await msg.answer("Please, provide text for generation")

    style = styles.stylize(settings["quality_tag"], text)

    params = txt2img_params()
    params.prompt = style.positive
    params.negative_prompt = style.negative
    params.steps = settings["steps"]
    params.batch_size = 4 #settings["n_iter"]
    params.sampler_name = settings["sampler"]

    update_message = await msg.answer(f"Placed in queue: `{queue.human_size()}`", parse_mode="MarkdownV2")
    processor = txt2img_processor(api, queue, params, initial_message=update_message)

    async def proc_end(result: WebUIApiResult):
        execution_time = processor.get_process_time()
        await processor.msg_update(f"Done in `{int(execution_time)}` seconds")

        if not result:
            await processor.msg_update("Error. No data from server")
            return

        markup = InlineKeyboardMarkup(inline_keyboard=IMAGE_KEYBOARD)

        for it, img in enumerate(result.images):
            seed = result.info['all_seeds'][it]
            caption = f"`{style.full_clear}`"
        
            await msg.answer_document(document= BufferedInputFile(ImageToBytes(img), f"{seed}.png"),caption=caption, parse_mode="MarkdownV2", reply_markup=markup)
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

    style = styles.stylize(settings["quality_tag"], text)

    with BytesIO() as file_in_io:
        await bot.download(image, destination=file_in_io)
        file_in_io.seek(0)
        with Image.open(file_in_io) as pil_img:
            width, height = pil_img.size
            width = RoundTo8(width)
            height = RoundTo8(height)

            if mode == "upscale":
                params = img2img_params()
                params.width = width
                params.height = height
                params.prompt = style.positive
                params.negative_prompt = style.negative
                params.init_images = [pil_img.copy()]
                # params.script_name = "SD Upscale"
                # params.script_args=["_", 64, upscaler_id, 2]

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


        
                

                

    await msg.answer()
        