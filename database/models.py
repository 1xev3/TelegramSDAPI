from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Date, Enum, Float
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.dialects.postgresql import JSONB
from typing import Literal
from sqlalchemy.orm import relationship

from .db import Base

# UserDefaultSettings = {
#     'cfg_scale':7,
#     'n_iter':1,
#     'seed': -1,
#     'sampler':"Euler",
#     'steps': 22,

#     'quality_tag': 'Основной',

#     'enable_hr': False,
#     'hr_scale': 2,
#     'hr_denoise': 0.4,

#     'aspect_x': 1,
#     'aspect_y': 1,
# }

class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey('user.id'), unique=True)
    cfg_scale = Column(Integer, default=7)
    n_iter = Column(Integer, default=1)
    seed = Column(Integer, default=-1)
    sampler = Column(String, default="Euler a")
    steps = Column(Integer, default=28)
    quality_tag = Column(String, default='Основной')
    enable_hr = Column(Boolean, default=False)
    hr_scale = Column(Integer, default=2)
    hr_denoise = Column(Float, default=0.4)
    aspect_x = Column(Float, default=1)
    aspect_y = Column(Float, default=1)

class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer)
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    
UserSettings.user = relationship("User", back_populates="settings")