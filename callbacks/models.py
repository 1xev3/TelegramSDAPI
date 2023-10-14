from aiogram.filters.callback_data import CallbackData
from typing import Literal

class MenuOptions(CallbackData, prefix="menu"):
    mode: str
    
class ImageOptions(CallbackData, prefix="img"):
    mode: Literal["upscale", "sameprompt", "variants", "deepboru", "style"]

class SetOptions(CallbackData, prefix="set"):
    mode: str
    value: str