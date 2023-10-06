from PIL import Image
from io import BytesIO
from math import floor

from aiogram import types


def ImageToBytes(img: Image):
    img_byte_arr = BytesIO()
    img_byte_arr.name = 'image.png'
    img.save(img_byte_arr, format="PNG")
    img_byte_arr.seek(0)
    return img_byte_arr.getvalue()

def KBCustom(inputs,callback_strings,size):
    if len(inputs) != len(callback_strings):
        raise ValueError("rounded_keyboard_custom - inputs and callback_strings: must be a same size")
    kb = []
    count = len(inputs)
    for i in range(0,floor(count/size)+1):
        kb.append([])
        cur_num = size*i
        for k in range(cur_num,cur_num+min(size,count-cur_num)):
            key = str(inputs[k])
            kb[i].append(types.InlineKeyboardButton(text=key, callback_data=callback_strings[k]))
    return kb