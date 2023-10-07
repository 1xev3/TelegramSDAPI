from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

from typing import Tuple, Type

from pydantic import Field

class Config(BaseSettings):
    DB_DNS: str = Field(default = "sqlite:///database.db")
    TOKEN: str = Field(description="Telegram bot token")
    API_URL: str = Field(description="SDWebUI URL", default="localhost:7860")
    QUEUE_LIMIT: int = Field(description="Limit for user queue", default=4)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return dotenv_settings, env_settings, init_settings

def load_config(*arg, **vararg) -> Config:
    return Config(*arg, **vararg)