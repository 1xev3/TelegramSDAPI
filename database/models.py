from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, JSON, Date, Enum
from typing import Literal
from sqlalchemy.orm import relationship

from .db import Base

UserDefaultSettings = {
    'cfg_scale':7,
    'n_iter':1,
    'seed': -1,
    'sampler':"Euler",
    'steps': 22,

    'quality_tag': 'Основной',

    'enable_hr': False,
    'hr_scale': 2,
    'hr_denoise': 0.4,

    'aspect_x': 16.0,
    'aspect_y': 9.0,
}

class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer)
    settings = Column(JSON, default=UserDefaultSettings)
    