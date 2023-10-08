import asyncio, logging
from functools import wraps

from sqlalchemy.orm import Session
from database import models

from time import time
from aiogram.utils.text_decorations import markdown_decoration as md
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup, Message, CallbackQuery, BufferedInputFile

from functional.sd_api import WebUIApi, APIQueue, StyleFactory
from functional.sd_api import txt2img_params, img2img_params

from .shared import ImageToBytes, KBCustom
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

    #command processor
    class __processor():
        def __init__(self, initial_message):
            #shared parameters
            self.start_time = time()
            self.update_message = initial_message

        #prevent message is not modified error
        async def __update_message(self, text):
            if self.update_message.text != text:
                self.update_message = await self.update_message.edit_text(text, parse_mode="MarkdownV2")

        async def process(self):
            self.start_time = time()
            self.update_message = await msg.answer("Generation...")

            params = txt2img_params()
            params.prompt = style.positive
            params.negative_prompt = style.negative
            params.steps = settings["steps"]
            params.batch_size = 4 #settings["n_iter"]
            params.sampler_name = settings["sampler"]
            
            try:
                result1 = await api.txt2img(params)

                if not result1:
                    await msg.answer("No data from server?")
                    return

                kb = IMAGE_KEYBOARD
                markup = InlineKeyboardMarkup(inline_keyboard=kb)

                it = 0
                for img in result1.images:
                    seed = result1.info['all_seeds'][it]
                    caption = f"`{style.full_clear}`"
                    caption = caption[:1023] if len(caption) > 1023 else caption
                
                    await msg.answer_document(document= BufferedInputFile(ImageToBytes(img), f"{seed}.png"),caption=caption, parse_mode="MarkdownV2", reply_markup=markup)
                    img.close()
                    it += 1
            
            except Exception as E:
                await msg.answer(f"Error: {E}")

        
        async def update(self):
            status = await api.get_progress()

            progress = status.progress
            negative_progress = 1 - progress
            
            waiting = (progress == 0.0)
            progress_str = f"`{int(progress*100)}\%`" if (not waiting) else "`Waiting`"
            
            count = 25
            progress_bar = f'\[{"━"*int(progress*count)}{ md.spoiler("━"*int(negative_progress*count)) }\]'

            message = f"{md.quote('Generating...')} "\
                    f"{progress_str}\n"\
                    f"{progress_bar if not waiting else ''}\n"
            await self.__update_message(message)

        async def end(self):
            execution_time = time() - self.start_time
            await self.__update_message(f"Done in `{int(execution_time)}` seconds")

    #register
    update_message = await msg.answer(f"Placed in queue: `{queue.human_size()}`", parse_mode="MarkdownV2")
    proc = __processor(initial_message=update_message)

    try:
        #put in queue
        await queue.put( queue.Params(
            user_id=user.telegram_id,
            func=proc.process,
            update_func=proc.update, #no ()! only coroutine fabric!
            end_func=proc.end,
        ))
    except errors.MaxQueueReached as E:
        await update_message.edit_text("You reached queue limit. Please wait before using it again")
        logger.info(f"User {msg.from_user.full_name} with ID:[{msg.from_user.id}] reached queue limit")

