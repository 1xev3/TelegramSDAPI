import asyncio
from asyncio import run as async_run
from functools import wraps

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ErrorEvent, CallbackQuery
from aiogram.utils.markdown import hbold

import logging
from sys import stdout

from sqlalchemy.orm import Session
from database import DB_INITIALIZER
import config

from callbacks import models as cb_models
import functional.crud as crud

## INIT ##
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO,stream=stdout)

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
crud.queue.configure(cfg.QUEUE_LIMIT, {}, 10)

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


#Commands itself
@rp.message(CommandStart())
@db_session
async def command_start_handler(msg: Message, db:Session) -> None:
    await crud.start_command(msg, db)

@rp.message(Command("settings"))
@db_session
async def _(msg: Message, db:Session) -> None:
    await crud.config_command(msg, db)

@rp.message()
@db_session
async def echo_handler(msg: types.Message, db:Session) -> None:
    await crud.any_msg(msg, db)

@rp.callback_query(cb_models.MenuOptions.filter(F.mode == "scale"))
@db_session
async def _(query: CallbackQuery, callback_data: cb_models.MenuOptions, db:Session):
    await crud.config_command_callaback(query, callback_data, db)



async def main():
    dp = Dispatcher()
    dp.include_routers(
        rp,
    )

    loop = asyncio.get_event_loop()
    loop.create_task(crud.queue.process_requests())

    bot = Bot(cfg.TOKEN, parse_mode=ParseMode.HTML)
    await bot.get_updates(offset=-1)#skip updates
    await dp.start_polling(bot)

if __name__ == "__main__":
    async_run(main())