import typing
import logging

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton as IKB, InlineKeyboardMarkup, Message, CallbackQuery

from functools import wraps

from sqlalchemy.orm import Session

from dataclasses import dataclass

from functional.shared import get_user

logger = logging.getLogger("telebot")



@dataclass
class SettingsCallback():
    prefix: str
    button_text: str
    coro: typing.Coroutine


class SettingsMaster():
    def __init__(self, command:str, db_session_maker, buttons_per_row = 3, router = Router()):
        self.session_maker = db_session_maker
        self.command = command
        self.router = router
        self.buttons_per_row = buttons_per_row

        self.callbacks: dict[SettingsCallback] = {}
        self.delimeter = ":"

        #main message handler
        @self.router.message(Command(command))
        async def _(msg: Message) -> None:
            db = self.session_maker()
            try: await msg.answer(text=self.generate_main_menu(), reply_markup=self.generate_keyboard(msg.from_user.id, db))
            except Exception as E: 
                logger.error(E.with_traceback())
                db.close()

        #back to menu handler
        @self.router.callback_query(F.data == self.arg_pack(self.command, "to_menu"))
        async def _(query: CallbackQuery) -> None:
            db = self.session_maker()
            try: await query.message.edit_text(text=self.generate_main_menu(), reply_markup=self.generate_keyboard(query.from_user.id, db))
            except Exception as E: 
                logger.error(E.with_traceback())
                db.close()
    
    def arg_pack(self, *args):
        return self.delimeter.join(args)
    
    def arg_unpack(self, arg:str):
        return arg.split(self.delimeter)
        

    def register_command(self, prefix: str, button_text: str, coro: typing.Coroutine):
        self.callbacks[prefix] = SettingsCallback(
            prefix=prefix,
            button_text=button_text,
            coro=coro
        ) 
        
        @self.router.callback_query(F.data.startswith(prefix))
        @self.__db_async_session
        async def _(query: CallbackQuery, db:Session):
            data = self.arg_unpack(query.data)
            if len(data[1:]) < 1: 
                logger.error(f"[{self.command}] Data len < 1 for callback {prefix}! Skipping")
                await query.answer()
                return

            await coro(self, query, data, db)

    def get_callbacks(self) -> dict[SettingsCallback]:
        return self.callbacks.values()
    
    def edit_button_text(self, prefix: str, button_text:str):
        self.callbacks[prefix].button_text = button_text
    
    def back_button(self, text:str = "❌ Back") -> IKB:
        return IKB(text=text, callback_data=self.arg_pack(self.command, "to_menu"))

    def __db_async_session(self,func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            db = self.session_maker()
            try:
                await func(db = db, *args, **kwargs)
            finally:
                db.close()
        return wrapper
    
    def generate_main_menu(self) -> str: 
        return "⚙️ Settings menu"

    def generate_keyboard(self, telegram_id, db:Session) -> InlineKeyboardMarkup:
        user = get_user(db, telegram_id)

        kb = []
        for k, callback in enumerate(self.get_callbacks()):
            if k % self.buttons_per_row == 0:
                kb.append([])

            text = "?"
            if callable(callback.button_text):
                text = callback.button_text(user.settings)
            elif type(callback.button_text) == str:
                text = callback.button_text
            

            kb[-1].append(
                IKB(text=text, callback_data=self.arg_pack(callback.prefix, "menu"))
            )
        print(kb)
        
        return InlineKeyboardMarkup(inline_keyboard=kb)