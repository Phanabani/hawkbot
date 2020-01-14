from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from .utils.data_classes import User, Channel
from utils.database.messages import random_message as random_message_db
from utils.database.misc import LimitTuple
from utils.discord_utils import get_message_url


@dataclass
class DatabaseMessage:
    guild_id: int
    id: int
    channel: Channel
    author: User
    created_at: datetime
    content: str
    images: List[str]

    @property
    def jump_url(self):
        if not isinstance(self.guild_id, int):
            raise ValueError(f'Guild ID must be int, not {type(self.guild_id)}')
        if not isinstance(self.channel.id, int):
            raise ValueError(f'Channel ID must be int, not {type(self.channel.id)}')
        if not isinstance(self.id, int):
            raise ValueError(f'Message ID must be int, not {type(self.id)}')
        return get_message_url(self.guild_id, self.channel.id, self.id)


def random_message(guild_id: int,
                   users: Optional[List[int]] = None,
                   channel: Optional[int] = None,
                   word_limit: Optional[LimitTuple] = None,
                   count: int = 1,
                   content: bool = False,
                   images: bool = False):
    cur = random_message_db(guild_id, users, channel, word_limit, count,
                            content, images)
    for msg_id, channel_id, username, timestamp, content, images in cur:
        yield DatabaseMessage(guild_id, msg_id, Channel(id=channel_id),
                              User(name=username),
                              timestamp, content,
                              images.split(';') if images else None)
