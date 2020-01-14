import logging
from typing import Optional, List, Union

from mysql.connector.cursor import MySQLCursor

from utils.database.main import cnx, supply_cursor, fix_missing_shared

logger = logging.getLogger(__name__)


@fix_missing_shared()
@supply_cursor()
def add_guild(guild_id: int, cur: MySQLCursor = None):
    cur.execute('''
        INSERT INTO config (guild_id) VALUES (%s)
        ON DUPLICATE KEY UPDATE guild_id=guild_id
    ''', (guild_id,))
    cnx.commit()


@fix_missing_shared()
@supply_cursor()
def get_prefix(guild_id: int, cur: MySQLCursor = None):
    cur.execute('''
        SELECT prefix FROM config
        WHERE guild_id = %s
    ''', (guild_id,))
    result = cur.fetchone()
    return result[0] if result else None


@fix_missing_shared()
@supply_cursor()
def set_prefix(guild_id: int, prefix: Optional[str], cur: MySQLCursor = None):
    cur.execute('''
        UPDATE config SET prefix = %s
        WHERE guild_id = %s
    ''', (prefix, guild_id))
    cnx.commit()


@fix_missing_shared()
@supply_cursor()
def get_pins_channel(guild_id: int, cur: MySQLCursor = None):
    cur.execute('''
        SELECT pins_channel FROM config
        WHERE guild_id = %s
    ''', (guild_id,))
    result = cur.fetchone()
    return result[0] if result else None


@fix_missing_shared()
@supply_cursor()
def set_pins_channel(guild_id: int, channel_id: Optional[int],
                     cur: MySQLCursor = None):
    cur.execute('''
        UPDATE config SET pins_channel = %s
        WHERE guild_id = %s
    ''', (channel_id, guild_id))
    cnx.commit()


def _split_channel_download_blacklist(blacklist: Optional[str]):
    if not blacklist:
        return []
    return list(map(int, blacklist.split(';')))


def _join_channel_download_blacklist(blacklist: List[int]):
    return ';'.join(map(str, blacklist))


@fix_missing_shared()
@supply_cursor()
def get_channel_download_blacklist(guild_id: int, cur: MySQLCursor = None
                                   ) -> Optional[List[int]]:
    cur.execute('''
        SELECT channel_download_blacklist FROM config
        WHERE guild_id = %s
    ''', (guild_id,))
    result = cur.fetchone()
    if result:
        return _split_channel_download_blacklist(result[0])
    return []


@fix_missing_shared()
@supply_cursor()
def set_channel_download_blacklist(guild_id: int, blacklist: str,
                                   cur: MySQLCursor = None):
    cur.execute('''
        UPDATE config SET channel_download_blacklist = %s
        WHERE guild_id = %s
    ''', (blacklist, guild_id))
    cnx.commit()


def add_channel_to_download_blacklist(guild_id: int,
                                      channel_ids: Union[int, List[int]]):
    if isinstance(channel_ids, int):
        channel_ids = [channel_ids]
    blacklist = _join_channel_download_blacklist(
        get_channel_download_blacklist(guild_id) + channel_ids
    )
    set_channel_download_blacklist(guild_id, blacklist)


def remove_channel_from_download_blacklist(guild_id: int,
                                           channel_ids: Union[int, List[int]]):
    if isinstance(channel_ids, int):
        channel_ids = [channel_ids]
    blacklist_channels = get_channel_download_blacklist(guild_id)
    for channel in channel_ids:
        blacklist_channels.remove(channel)

    blacklist = _join_channel_download_blacklist(blacklist_channels)
    set_channel_download_blacklist(guild_id, blacklist)


if __name__ == '__main__':
    print(repr(get_prefix(288545683462553610)))
