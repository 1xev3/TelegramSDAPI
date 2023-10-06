from aiogram.filters.callback_data import CallbackData

class MenuOptions(CallbackData, prefix="menu"):
    mode: str
    