import functools
import logging
from typing import Optional, List, Tuple, Iterator

import mysql.connector
from mysql.connector import errorcode
from mysql.connector.cursor import MySQLCursor
import spacy

from utils.errors import typecheck, UserFeedbackError
from utils.database.misc import flat_pruned_list
from utils.database.main import cnx, supply_cursor

logger = logging.getLogger(__name__)
nlp = spacy.load('en_core_web_sm')


def _create_where_statement(users: int = 0,
                            channels: int = 0,
                            tag: bool = False):
    users = int(users)
    channels = int(channels)
    tag = bool(tag)

    where = ' AND '.join([i for i in [
        users and f'user IN (SELECT key_id FROM users '
                  f'WHERE id IN ({",".join(["%s"] * users)}))',
        channels and f'channel IN (SELECT key_id FROM channels '
                     f'WHERE id IN ({",".join(["%s"] * channels)}))',
        tag and f'tag = %s'
    ] if i])
    return f'WHERE {where}' if where else ''


def alert_missing_pos_tags(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        try:
            f(*args, **kwargs)
        except mysql.connector.Error as e:
            if e.errno == errorcode.ER_NO_SUCH_TABLE:
                raise UserFeedbackError('No part of speech data generated '
                                        'for this server')
            raise e
        return f(*args, **kwargs)
    return wrapped


# noinspection SqlResolve
@alert_missing_pos_tags
@supply_cursor()
def _insert_word(guild_id: int, user: int, channel: int, tag: str,
                 word: str, cur: MySQLCursor = None):
    cur.execute(f'''
        INSERT INTO g{guild_id}_pos_tags
        (user, channel, tag, word)
        VALUES (
            (SELECT key_id FROM users WHERE id=%s),
            (SELECT key_id FROM channels WHERE id=%s),
            %s,%s
        ) ON DUPLICATE KEY UPDATE use_count = use_count + 1
    ''', (user, channel, tag, word))
    cnx.commit()


def _get_tags(msg: str) -> Iterator[Tuple[str, str]]:
    try:
        doc = nlp(msg)
    except TypeError:
        return
    for token in doc:
        yield token.tag_, token.text


# noinspection SqlResolve
@alert_missing_pos_tags
@supply_cursor()
def generate_tags(guild_id: int, cur: MySQLCursor = None):
    typecheck(guild_id, int, 'guild_id')
    logger.info(f'Generating part of speech tags for server {guild_id}')

    cur.execute(f'''
        SELECT users.id, channels.id, content FROM g{guild_id}_messages AS msgs
        INNER JOIN users ON (msgs.user = users.key_id)
        INNER JOIN channels ON (msgs.channel = channels.key_id)
        WHERE content <> ''
    ''')

    for user_id, channel_id, content in cur:
        for tag, word in _get_tags(content):
            _insert_word(guild_id, user_id, channel_id, tag, word)


# noinspection SqlResolve
@alert_missing_pos_tags
@supply_cursor()
def get_random_words_by_tag(guild_id: int, tag: str,
                            users: Optional[List[int]] = None,
                            channel: Optional[int] = None,
                            count: int = 1,
                            cur: MySQLCursor = None) -> List[str]:
    typecheck(guild_id, int, 'guild_id')
    where_stmt = _create_where_statement(len(users) if users else 0,
                                         1 if channel else 0, True)

    cur.execute(f'''
        SELECT word FROM g{guild_id}_pos_tags
        {where_stmt}
        ORDER BY RAND() LIMIT %s
    ''', flat_pruned_list(users, channel, tag, count))

    words = [w[0] for w in cur]
    return words


if __name__ == '__main__':
    # generate_tags(288545683462553610)
    pass
