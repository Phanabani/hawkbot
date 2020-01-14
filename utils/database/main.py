import functools
import logging

from discord import Guild, TextChannel, User
import mysql.connector
from mysql.connector.cursor import MySQLCursor
from mysql.connector import errorcode

from utils.config import config
from utils.errors import typecheck
import utils.database.config as db_config

logger = logging.getLogger(__name__)

if 'mysql' in config:
    if config['mysql']['use_aws_secrets_manager']:
        from utils.aws import aws
        credentials = aws.get_rds_secret(config['mysql']['secret_name'],
                                         config['mysql']['region_name'])
    else:
        credentials = config['mysql']

    cnx = mysql.connector.connect(
        ssl_disabled=False,
        user=credentials['username'],
        password=credentials['password'],
        host=credentials['host'],
        database=credentials['database'],
        auth_plugin='mysql_native_password'
    )
else:
    # TODO handle errors from attempting to use this null connection
    logger.warning('MySQL database info is not configured.')
    cnx = None


def supply_cursor(*cur_args, close=True, **cur_kwargs):
    """
    Use to supply a function with a `cur` MySQL cursor argument that will be
    automatically closed

    :param cur_args: args to pass to cnx.cursor
    :param cur_kwargs: kwargs to pass to cnx.cursor
    """
    def wrapper(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            cnx.ping(reconnect=True)
            cur = cnx.cursor(*cur_args, buffered=True, **cur_kwargs)
            try:
                return f(*args, **kwargs, cur=cur)
            except Exception as e:
                cur.close()
                raise e
            finally:
                if close:
                    cur.close()
        return wrapped
    return wrapper


def fix_missing_shared(return_none_if_missing: bool = False):
    def wrapper(f):
        @functools.wraps(f)
        def wrapped(*args, **kwargs):
            try:
                f(*args, **kwargs)

            except mysql.connector.Error as e:
                if e.errno == errorcode.ER_NO_SUCH_TABLE:
                    init_shared()
                    if return_none_if_missing:
                        return None
                    return wrapped(*args, **kwargs)
                raise e
            return f(*args, **kwargs)
        return wrapped
    return wrapper


@supply_cursor()
def init_shared(cur: MySQLCursor = None):
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            key_id SMALLINT UNSIGNED AUTO_INCREMENT,
            id BIGINT UNSIGNED NOT NULL UNIQUE,
            name VARCHAR(32) NOT NULL,
            discriminator SMALLINT UNSIGNED NOT NULL,
            PRIMARY KEY (key_id)
        );

        CREATE TABLE IF NOT EXISTS channels (
            key_id SMALLINT UNSIGNED AUTO_INCREMENT,
            id BIGINT UNSIGNED NOT NULL UNIQUE,
            name VARCHAR(100) NOT NULL,
            PRIMARY KEY (key_id)
        );

        CREATE TABLE IF NOT EXISTS config (
            guild_id BIGINT UNSIGNED NOT NULL,
            prefix VARCHAR(255),
            pins_channel BIGINT UNSIGNED,
            channel_download_blacklist TEXT,
            PRIMARY KEY (guild_id)
        );
    ''', multi=True)


@supply_cursor()
def init_guild(guild: Guild, cur: MySQLCursor = None):
    guild_id = guild.id
    typecheck(guild_id, int, 'guild_id')

    cur.execute(f'''
        CREATE TABLE IF NOT EXISTS g{guild_id}_messages (
            id BIGINT UNSIGNED NOT NULL,
            user SMALLINT UNSIGNED NOT NULL,
            channel SMALLINT UNSIGNED NOT NULL,
            timestamp DATETIME NOT NULL,
            content TEXT NOT NULL,
            images TEXT,
            PRIMARY KEY (id),
            INDEX (user),
            INDEX (channel)
        );

        CREATE TABLE IF NOT EXISTS g{guild_id}_markov (
            user SMALLINT UNSIGNED NOT NULL,
            channel SMALLINT UNSIGNED NOT NULL,
            base TEXT,
            potentials MEDIUMTEXT,
            INDEX (user),
            INDEX (channel),
            INDEX (base(32))
        );
        
        CREATE TABLE IF NOT EXISTS g{guild_id}_pos_tags (
            user SMALLINT UNSIGNED NOT NULL,
            channel SMALLINT UNSIGNED NOT NULL,
            tag VARCHAR(8) NOT NULL,
            word TEXT NOT NULL,
            use_count MEDIUMINT UNSIGNED DEFAULT 0,
            INDEX (user),
            INDEX (channel),
            INDEX (tag(3)),
            UNIQUE KEY unique_entry (user, channel, tag, word(32))
        );

        CREATE TABLE IF NOT EXISTS g{guild_id}_pins (
            original BIGINT UNSIGNED NOT NULL,
            pin BIGINT UNSIGNED NOT NULL
        );
    ''', multi=True)

    db_config.add_guild(guild_id)

    for channel in guild.text_channels:
        add_channel(channel)


@fix_missing_shared()
@supply_cursor()
def add_channel(channel: TextChannel, cur: MySQLCursor = None):
    cur.execute('''
        INSERT INTO channels (id, name) VALUES (%s,%s)
        ON DUPLICATE KEY UPDATE id=id
    ''', (channel.id, channel.name))
    cnx.commit()


@fix_missing_shared()
@supply_cursor()
def add_user(user: User, cur: MySQLCursor = None):
    cur.execute('''
        INSERT INTO users (id, name, discriminator)
        VALUES (%s,%s,%s)
        ON DUPLICATE KEY UPDATE id=id
    ''', (user.id, user.name, user.discriminator))
    cnx.commit()


@fix_missing_shared(return_none_if_missing=True)
@supply_cursor()
def user_name_from_id(id_: int, cur: MySQLCursor):
    cur.execute(
        'SELECT name FROM users WHERE id=%s', (id_,)
    )
    result = cur.fetchone()
    return result[0] if result else None
