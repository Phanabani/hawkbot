from collections.abc import Sequence
import datetime as dt
import functools
import logging
import sqlite3
from typing import Union, Optional, List

import discord
import mysql.connector
from mysql.connector import errorcode
from mysql.connector.cursor import MySQLCursor

from utils.database.config import get_channel_download_blacklist
from utils.database.main import cnx, init_guild, add_channel, add_user,\
    supply_cursor
from utils.database.misc import flat_pruned_list, LimitTuple
from utils.errors import typecheck, UserFeedbackError

logger = logging.getLogger(__name__)
IMAGE_TYPES = {'bmp', 'gif', 'gifv', 'jpg', 'jpeg', 'png', 'webp'}


class SkippedBlacklistedChannel(Exception):
    pass


def _create_where_statement(id_: bool = False,
                            user: int = 0,
                            channel: int = 0,
                            timestamp: bool = False,
                            regex: bool = False,
                            content: bool = False,
                            images: bool = False,
                            case_sensitive: bool = False):
    id_ = bool(id_)
    user = int(user)
    channel = int(channel)
    timestamp = bool(timestamp)
    regex = bool(regex)
    content = bool(content)
    images = bool(images)
    case_sensitive = bool(case_sensitive)

    where = ' AND '.join([i for i in [
        id_ and f'id BETWEEN %s AND %s',
        user and f'user IN (SELECT key_id FROM users '
                 f'WHERE id IN ({",".join(["%s"]*user)}))',
        channel and f'channel IN (SELECT key_id FROM channels '
                    f'WHERE id IN ({",".join(["%s"]*channel)}))',
        timestamp and 'timestamp BETWEEN %s AND %s',
        regex and ('content REGEXP %s' if case_sensitive
                   else 'LOWER(content) REGEXP LOWER(%s)'),
        content and 'content <> ""',
        images and 'images IS NOT NULL'
    ] if i])
    return f'WHERE {where}' if where else ''


def alert_missing_messages(return_none_if_missing=False):
    def wrapper(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            try:
                result = f(*args, **kwargs)
            except mysql.connector.Error as e:
                if e.errno == errorcode.ER_NO_SUCH_TABLE:
                    if return_none_if_missing:
                        return None
                    raise UserFeedbackError('No message data has been '
                                            'collected for this server')
                raise e
            return result
        return wrapped
    return wrapper


def _get_images_urls(msg: discord.Message):
    urls = []
    if msg.attachments:
        for a in msg.attachments:
            if a.filename.split('.')[-1] in IMAGE_TYPES:
                urls.append(a.url)
    elif msg.embeds:
        for e in msg.embeds:
            if e.type == 'image':
                urls.append(e.url)
    return urls if urls else None


# noinspection SqlResolve
@alert_missing_messages(return_none_if_missing=True)
@supply_cursor()
def _get_most_recent_update(guild_id: int, channel_id: int,
                            cur: MySQLCursor) -> Optional[dt.datetime]:
    typecheck(guild_id, int, 'guild_id')

    cur.execute(f'''
        SELECT MAX(timestamp) FROM g{guild_id}_messages as msgs
        INNER JOIN channels ON (channels.key_id = msgs.channel)
        WHERE channels.id = %s
        GROUP BY channel;
    ''', (channel_id,))
    timestamp = cur.fetchone()

    return timestamp[0] if timestamp else None


# noinspection SqlResolve
@alert_missing_messages()
@supply_cursor()
def _insert_message(msg: discord.Message, cur: MySQLCursor = None):
    guild_id = msg.guild.id
    typecheck(guild_id, int, 'guild_id')
    images = _get_images_urls(msg)
    if images:
        images = ';'.join(images)

    add_user(msg.author)
    add_channel(msg.channel)
    cur.execute(f'''
        INSERT INTO g{guild_id}_messages (
            id, user, channel, timestamp, content, images
        ) VALUES (
            %s,
            (SELECT key_id FROM users WHERE id=%s),
            (SELECT key_id FROM channels WHERE id=%s),
            %s,%s,%s
        )
    ''', (msg.id, msg.author.id, msg.channel.id, msg.created_at,
          msg.content, images))
    cnx.commit()


async def download_messages(source: Union[discord.Guild, discord.TextChannel]):
    if isinstance(source, discord.Guild):
        for channel in source.text_channels:
            await download_messages(channel)

    elif isinstance(source, discord.TextChannel):
        logger.info(f'Collecting messages from {source.id} (#{source.name}) '
                    f'in guild {source.guild.id} ({source.guild.name})')
        init_guild(source.guild)

        blacklist = get_channel_download_blacklist(source.guild.id)
        if blacklist and source.id in blacklist:
            raise SkippedBlacklistedChannel

        after = _get_most_recent_update(source.guild.id, source.id)
        # TODO it's skipping the first message sent in updated channels
        skip_first = after is not None
        try:
            async for msg in source.history(limit=None, after=after,
                                            oldest_first=True):
                if skip_first:
                    skip_first = False
                    continue
                if msg.author.bot or msg.type != discord.MessageType.default:
                    continue
                _insert_message(msg)

        except discord.errors.Forbidden as e:
            logger.info(f'Access denied to {source.id} ({source.name})')
            raise e
        except sqlite3.Error as e:
            logger.error(f'Failed to download {source}: {e}')
            raise e

    else:
        raise ValueError(f'source must be of type Guild or TextChannel, '
                         f'not {type(source)}')


# noinspection SqlResolve
@alert_missing_messages()
@supply_cursor(close=False, named_tuple=True)
def random_message(guild_id: int,
                   users: Optional[List[int]] = None,
                   channel: Optional[int] = None,
                   word_limit: Optional[LimitTuple] = None,
                   count: int = 1,
                   content: bool = False,
                   images: bool = False,
                   cur: MySQLCursor = None):
    typecheck(guild_id, int, 'guild_id')
    if isinstance(word_limit, Sequence) and not any(word_limit):
        word_limit = None

    # Case insensitivity was screwing with the word limit
    # regex pattern (\S -> \s)
    where_stmt = _create_where_statement(
        user=len(users) if users else 0,
        channel=1 if channel else 0,
        regex=bool(word_limit),
        content=content,
        images=images,
        case_sensitive=True
    )
    word_limit_regex = None
    if word_limit:
        min_ = word_limit[0]-1 if word_limit[0] else ''
        max_ = word_limit[1]-1 if word_limit[1] else ''
        word_limit_regex = (
            rf'^(?:\S+ +){{{min_},{max_}}}\S+$')

    # https://stackoverflow.com/a/41581041
    script = f'''
        SELECT msgs.id as msg_id, channels.id as channel_id,
               users.name as user_name, timestamp, content, images
        FROM g{guild_id}_messages AS msgs
        INNER JOIN channels ON (msgs.channel = channels.key_id)
        INNER JOIN users ON (msgs.user = users.key_id)
        WHERE msgs.id IN (
            SELECT id FROM (
                SELECT id FROM g{guild_id}_messages
                {where_stmt}
                ORDER BY RAND() LIMIT %s
            ) t
        )
    '''
    cur.execute(script, flat_pruned_list(users, channel, word_limit_regex,
                                         count))
    return cur


# noinspection SqlResolve
@alert_missing_messages()
@supply_cursor()
def message_stats(guild_id: int,
                  pattern: str,
                  users: Optional[List[int]] = None,
                  channels: Optional[List[int]] = None,
                  case_sensitive: bool = False,
                  plot: bool = False,
                  cur: MySQLCursor = None):
    typecheck(guild_id, int, 'guild_id')
    where_stmt = _create_where_statement(
        user=len(users) if users else 0,
        channel=len(channels) if channels else 0,
        regex=True,
        case_sensitive=case_sensitive
    )

    if not plot:
        cur.execute(f'''
            SELECT users.name, COUNT(*)
            FROM g{guild_id}_messages AS msgs
            INNER JOIN channels ON (msgs.channel = channels.key_id)
            INNER JOIN users ON (msgs.user = users.key_id)
            {where_stmt}
            GROUP BY user
            ORDER BY users.name
        ''', flat_pruned_list(users, channels, pattern))
        return cur
    else:
        cur.execute(f'''
            SELECT
                users.id, users.name, DATE_FORMAT(timestamp, '%Y-%m-%d'),
                COUNT(*)
            FROM g{guild_id}_messages AS msgs
            INNER JOIN channels ON (msgs.channel = channels.key_id)
            INNER JOIN users ON (msgs.user = users.key_id)
            {where_stmt}
            GROUP BY user, DATE_FORMAT(timestamp, '%Y-%m-%d')
            ORDER BY timestamp
        ''', flat_pruned_list(users, channels, pattern))
        return cur


if __name__ == '__main__':
    # print(repr(random_message(288545683462553610).fetchone()))
    print(repr(random_message(288545683462553610, images=True).fetchone()))
    # print(_get_most_recent_update(288545683462553610, 536970318762475550))
