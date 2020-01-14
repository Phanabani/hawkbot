import functools
from typing import Optional

import mysql.connector
from mysql.connector import errorcode
from mysql.connector.cursor import MySQLCursor

from utils.database.main import supply_cursor, cnx
from utils.errors import typecheck, UserFeedbackError


def alert_missing_pins(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        try:
            f(*args, **kwargs)
        except mysql.connector.Error as e:
            if e.errno == errorcode.ER_NO_SUCH_TABLE:
                raise UserFeedbackError('Run `admin init guild` to enable '
                                        'pins')
            raise e
        return f(*args, **kwargs)
    return wrapped


# noinspection SqlResolve
@alert_missing_pins
@supply_cursor()
def pin_message(guild_id: int, original_msg_id: int, pin_msg_id: int,
                cur: MySQLCursor = None):
    """
    Add a mapping between an original message and Hawkbot's pin message sent
    in a guild's designated pins channel

    :param guild_id: guild id
    :param original_msg_id: the id of the original message that was pinned
    :param pin_msg_id: the id of the pin message Hawkbot sent linking to the
        original
    """
    typecheck(guild_id, int, 'guild_id')
    cur.execute(f'''
        INSERT INTO g{guild_id}_pins (original, pin) VALUES (%s,%s) 
    ''', (original_msg_id, pin_msg_id))
    cnx.commit()


# noinspection SqlResolve
@alert_missing_pins
@supply_cursor()
def unpin_message(guild_id: int, original_msg_id: int,
                  cur: MySQLCursor = None) -> Optional[int]:
    """
    Remove a mapping between an original message and Hawkbot's pin message sent
    in a guild's designated pins channel

    :param guild_id: guild id
    :param original_msg_id: the id of the original message that was pinned
    :return: the id of the pin message Hawkbot sent linking to the original, or
        None if the original message was not found
    """
    typecheck(guild_id, int, 'guild_id')
    pin_msg_id = get_pin_msg_id(guild_id, original_msg_id)
    if pin_msg_id:
        cur.execute(f'''
            DELETE FROM g{guild_id}_pins WHERE original = %s
        ''', (original_msg_id,))
        cnx.commit()
        return pin_msg_id
    return None


# noinspection SqlResolve
@alert_missing_pins
@supply_cursor()
def get_pin_msg_id(guild_id: int, original_msg_id: int,
                   cur: MySQLCursor = None) -> Optional[int]:
    """
    Get the id of the associated pin message Hawkbot sent in a guild's
    designated pins channel

    :param guild_id: guild id
    :param original_msg_id: the id of the original message that was pinned
    :return: the id of the pin message Hawkbot sent linking to the original, or
        None if the original message was not found
    """
    typecheck(guild_id, int, 'guild_id')
    cur.execute(f'''
        SELECT pin FROM g{guild_id}_pins WHERE original = %s
    ''', (original_msg_id,))
    pin_msg_id = cur.fetchone()
    return pin_msg_id[0] if pin_msg_id else None
