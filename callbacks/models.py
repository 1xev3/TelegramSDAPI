from aiogram.filters.callback_data import CallbackData

class MenuOptions(CallbackData, prefix="menu"):
    mode: str
    
class ImageOptions(CallbackData, prefix="img"):
    mode: str

class SetOptions(CallbackData, prefix="set"):
    mode: str
    value: str