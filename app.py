import asyncio
from asyncio import run as async_run
from functools import wraps

from dataclasses import dataclass

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

import logging
from sys import stdout

from sqlalchemy.orm import Session
from database import DB_INITIALIZER
import config

from functional.settings_router import SettingsMaster
import functional.crud as crud
from callbacks import models as cb_models

## INIT ##
logger = logging.getLogger("telebot")
logging.basicConfig(level=logging.INFO,stream=stdout, 
                    format="[%(levelname)s][%(name)s][%(filename)s, line %(lineno)d]: %(message)s")

logger.info("Configuration loading...")
cfg: config.Config = config.load_config(_env_file='.env')
logger.info(
    'Service configuration loaded:\n' +
    f'{cfg.model_dump_json(by_alias=True, indent=4)}'
)

logger.info('Database initialization...')
SessionLocal = DB_INITIALIZER.init_db(cfg.DB_DNS)
logger.info('Database initialized...')

#config
API_URL = cfg.API_URL.split(":")
crud.api.configure(API_URL[0], API_URL[1])
crud.api.update_models()
crud.queue.configure(cfg.QUEUE_LIMIT, {}, 10,1)
bot = Bot(cfg.TOKEN.get_secret_value(), parse_mode=ParseMode.HTML)

#styles register
crud.styles.add_new(
    name="Основной", 
    positive="masterpiece, absurdres, highres, {}, award winning, ultra detailed, 8k, ultra resolution",
    negative="(disfigured:1.2), (worst quality, low quality:1.4), {}, (lowres), (deformed, distorted:1.3), bad hands, missing fingers, text, watermark, frame, poorly drawn, bad anatomy, wrong anatomy, extra limb, missing limb, (mutated hands and fingers:1.3), mutant, disconnected limbs, mutation, mutated, ugly, disgusting, blurry"
)



#decorator
def db_session(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        db = SessionLocal()
        try:
            await func(db = db, *args, **kwargs)
        finally:
            db.close()
    return wrapper



#init dispatcher
rp = Router()
settings_master = SettingsMaster("settings", SessionLocal, 3, rp)


#Commands itself
@rp.message(CommandStart())
@db_session
async def command_start_handler(msg: Message, db:Session) -> None:
    logger.info(f"Recieved start command from {msg.from_user.id} - {msg.from_user.full_name}")
    await crud.start_command(msg, db)

@rp.message(F.text) #yep any message will cause generation
@db_session
async def echo_handler(msg: types.Message, db:Session) -> None:
    logger.info(f"Recieved generation command from {msg.from_user.id} - {msg.from_user.full_name}")
    await crud.any_msg(msg, db)


@rp.callback_query(cb_models.ImageOptions.filter())
@db_session
async def img_reaction_query(query: types.CallbackQuery, callback_data: cb_models.ImageOptions, db:Session):
    await crud.image_reaction(query, callback_data, db, bot)

settings_master.register_command(
    "ratio", 
    lambda s: f'🖥 Change aspect [{s.aspect_x} / {s.aspect_y}]', 
    crud.ratio_setting 
)

async def main():
    dp = Dispatcher()
    dp.include_routers(
        rp,
    )

    loop = asyncio.get_event_loop()
    loop.create_task(crud.queue.process_requests())

    await bot.get_updates(offset=-1)#skip updates
    await dp.start_polling(bot)

if __name__ == "__main__":
    async_run(main())