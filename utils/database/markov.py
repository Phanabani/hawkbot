from collections import defaultdict
import functools
from functools import partial
import logging
from typing import Iterable, Optional, List

import mysql.connector
from mysql.connector import errorcode
from mysql.connector.cursor import MySQLCursor

from utils.errors import typecheck, UserFeedbackError
from utils.database.misc import flat_pruned_list
from utils.database.main import cnx, supply_cursor

logger = logging.getLogger(__name__)


def _create_where_statement(users: int = 0,
                            channels: int = 0,
                            base: bool = False):
    users = int(users)
    channels = int(channels)
    base = bool(base)

    where = ' AND '.join([i for i in [
        users and f'user IN (SELECT key_id FROM users '
                  f'WHERE id IN ({",".join(["%s"] * users)}))',
        channels and f'channel IN (SELECT key_id FROM channels '
                     f'WHERE id IN ({",".join(["%s"] * channels)}))',
        base and f'base = %s'
    ] if i])
    return f'WHERE {where}' if where else ''


def alert_missing_chain(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        try:
            f(*args, **kwargs)
        except mysql.connector.Error as e:
            if e.errno == errorcode.ER_NO_SUCH_TABLE:
                raise UserFeedbackError('No chain collected for this server')
            raise e
        return f(*args, **kwargs)
    return wrapped


# noinspection SqlResolve
@alert_missing_chain
@supply_cursor()
def _insert_to_chain(guild_id: int, user: int, channel: int, base: str,
                     potentials: Iterable[str], cur: MySQLCursor = None):
    potentials = ' '.join(potentials)
    cur.execute(f'''
        INSERT INTO g{guild_id}_markov
        (user, channel, base, potentials)
        VALUES (
            (SELECT key_id FROM users WHERE id=%s),
            (SELECT key_id FROM channels WHERE id=%s),
            %s,%s
        )
    ''', (user, channel, base, potentials))
    cnx.commit()


def _make_pairs(msg: str):
    msg = msg.split(' ')
    for i in range(0, len(msg)):
        if i == 0:
            yield ('', msg[0])
        else:
            yield (msg[i-1], msg[i])
    yield (msg[len(msg)-1], '')


# noinspection SqlResolve
@alert_missing_chain
@supply_cursor()
def create_chain(guild_id: int, cur: MySQLCursor = None):
    typecheck(guild_id, int, 'guild_id')
    logger.info(f'Creating chain for server {guild_id}')
    # Structure: chain[user_id][channel][base] = potentials
    user_chains = defaultdict(partial(defaultdict, partial(defaultdict, set)))

    cur.execute(f'''
        SELECT users.id, channels.id, content FROM g{guild_id}_messages AS msgs
        INNER JOIN users ON (msgs.user = users.key_id)
        INNER JOIN channels ON (msgs.channel = channels.key_id)
        WHERE content <> ''
    ''')

    for user_id, channel_id, content in cur:
        for base, potential in _make_pairs(content):
            user_chains[user_id][channel_id][base].add(potential)

    for user, channels in user_chains.items():
        for channel, chain in channels.items():
            for base, potentials in chain.items():
                _insert_to_chain(guild_id, user, channel, base, potentials)


# noinspection SqlResolve
@alert_missing_chain
@supply_cursor()
def get_potentials(guild_id: int, base: str,
                   users: Optional[List[int]] = None,
                   channel: Optional[int] = None,
                   cur: MySQLCursor = None):
    typecheck(guild_id, int, 'guild_id')
    where_stmt = _create_where_statement(len(users) if users else 0,
                                         1 if channel else 0, True)

    cur.execute(f'''
        SELECT potentials FROM g{guild_id}_markov
        {where_stmt}
    ''', flat_pruned_list(users, channel, base))

    potentials = []
    for p in cur:
        potentials.extend(p[0].split(' '))
    return potentials
