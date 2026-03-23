
from aiogram.filters import Filter
from aiogram.types import Message

class TextOnlyFilter(Filter):

    async def __call__(self, message: Message) -> bool:
        return message.text is not None and not message.photo and not message.voice and not message.video

class MediaFilter(Filter):

    async def __call__(self, message: Message) -> bool:
        return message.photo or message.voice or message.video or message.document
