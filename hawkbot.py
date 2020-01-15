import asyncio
from collections import deque, defaultdict
from dataclasses import dataclass
from datetime import datetime
import discord
import logging
from pathlib import Path
import random
import re
import string
import sys
from typing import *

import commands
from commands.parser import Parser, ParsedCommand, Grammar
from commands.parser.parameter_types import *
from utils.api_requests.gan_image import gan_image
from utils.config import config
import utils.database as db
import utils.discord_utils as dc_utils
from utils.discord_utils import send_error, play_audio_file
from utils.errors import UserFeedbackError, ErrorStrings, typecheck
import utils.misc as misc_utils

EMOJIS = {c: chr(i + 0x1f1e6) for i, c in enumerate(string.ascii_lowercase)}
REPEAT_EMOJI = '🔂'
# TODO can this be typed using typing.Protocol in the future?
BotCommandType = Callable[..., Awaitable[bool]]
logger = logging.getLogger(__name__)


class TempNickname:

    def __init__(self, member, new_name):
        self.member = member
        self.prev_name = member.display_name
        self.new_name = new_name

    async def __aenter__(self):
        await self.member.edit(nick=self.new_name)

    async def __aexit__(self, exc_type, exc, tb):
        await self.member.edit(nick=self.prev_name)


@dataclass(frozen=True)
class LastCommand:
    msg: discord.Message
    cmd: ParsedCommand
    function: BotCommandType
    args: Tuple
    kwargs: Dict[str, Any]


class PrefixStore:

    __slots__ = ['_prefixes', 'default']

    def __init__(self, default: Optional[str] = None):
        self._prefixes = {}
        self.default = default

    def __getitem__(self, guild_id: int):
        typecheck(guild_id, int, 'guild_id')
        if guild_id not in self._prefixes:
            prefix = db.config.get_prefix(guild_id)
            self._prefixes[guild_id] = (self.default if prefix is None
                                        else prefix)
        return self._prefixes[guild_id]

    def __setitem__(self, guild_id: int, prefix: Optional[str]):
        typecheck(guild_id, int, 'guild_id')
        db.config.set_prefix(guild_id, prefix)
        self._prefixes[guild_id] = self.default if prefix is None else prefix


def repeatable(f: BotCommandType):
    async def _repeatable(self, msg: discord.Message,
                          cmd: ParsedCommand, *args, **kwargs):
        result = await f(self, msg=msg, cmd=cmd, *args, **kwargs)
        if result:
            memory = self.channel_memory[msg.channel]
            if memory['last_command']:
                # Remove the repeat reaction (if it exists)
                # This is usually removed in the client listener,
                # but if a different repeatable command is run, we'll remove
                # the old reaction here.
                sent_msg: discord.Message = memory['last_command'][1]
                if isinstance(sent_msg, discord.Message):
                    try:
                        sent_msg = await sent_msg.channel.fetch_message(sent_msg.id)
                        await sent_msg.remove_reaction(REPEAT_EMOJI, self.user)
                    except discord.errors.Forbidden:
                        pass
                    except Exception as e:
                        logger.error(e)

            if isinstance(result, discord.Message):
                await result.add_reaction(REPEAT_EMOJI)

            cmd = LastCommand(msg=msg, cmd=cmd, function=repeatable(f),
                              args=args, kwargs=kwargs)
            memory['last_command'] = (cmd, result)
        return result
    return _repeatable


# noinspection PyMethodMayBeStatic
class Hawkbot(discord.Client):

    default_prefix = 'hb '

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.channel_memory: Dict[str, any] = \
            defaultdict(self._channel_memory_factory)
        self.prefixes = PrefixStore(default=self.default_prefix)
        self.parser = Parser()

    @staticmethod
    def _channel_memory_factory():
        return {
            'get_his_ass': deque(maxlen=2 + 1),
            'rquote': misc_utils.SizedDict(size=10),
            'last_command': None
        }

    async def on_ready(self):
        logger.info('Hawkbot client started')

    async def on_message(self, msg):
        if msg.author == self.user:
            return
        if not isinstance(msg.channel, discord.TextChannel):
            return

        try:
            if await self.commands(msg):
                return
            await asyncio.sleep(1.0)
            await self.ranked_trio_memes(msg)
        except UserFeedbackError as e:
            await send_error(msg.channel, e)
        except (discord.Forbidden, discord.HTTPException,
                discord.NotFound) as e:
            await send_error(msg.channel, e)

    async def on_reaction_add(self, reaction, user):
        if user == self.user:
            return
        if await self.repeat_command_reaction(reaction, user):
            return
        if await self.random_quote_reveal(reaction, user):
            return

    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.user.id:
            return

        if await self.pin_msg(payload):
            return

    async def on_raw_reaction_remove(self, payload):
        if payload.user_id == self.user.id:
            return

        if await self.unpin_msg(payload):
            return

    async def commands(self, msg):
        prefix = self.prefixes[msg.guild.id]
        if not msg.content.startswith(prefix):
            return False

        args = msg.content[len(prefix):]
        cmd = self.parser(args)
        if not cmd:
            return False
        root = cmd.base.root
        name = cmd.base.name

        if root == 'admin' and msg.author.id == config['owner_id']:
            if name == 'admin init guild':
                await self.init_guild(msg=msg)
            elif name == 'admin download':
                await self.download_messages(msg=msg, cmd=cmd)
            elif name == 'admin chain':
                await self.create_chain(msg=msg)
        elif root == 'ping':
            await self.ping(msg=msg)
        elif root == 'help':
            await self.help(msg=msg, cmd=cmd)
        elif root == 'config':
            await self.config(msg=msg, cmd=cmd)
        elif root == 'again':
            await self.again(msg=msg)
        elif root == 'cleanse':
            await self.cleanse(msg=msg)
        elif root == 'quote':
            await self.quote_link(msg=msg, cmd=cmd)
        elif root == 'gdrive':
            await self.gdrive_direct_link(msg=msg, cmd=cmd)
        elif root == 'portal':
            await self.channel_portal(msg=msg, cmd=cmd)
        elif name == 'vibe check':
            await self.vibe_check(msg=msg)
        elif root == 'generate':
            await self.generate_message(msg=msg, cmd=cmd)
        elif root == 'rquote':
            await self.random_quote(msg=msg, cmd=cmd)
        elif root == 'rimage':
            await self.random_image(msg=msg, cmd=cmd)
        elif root == 'mstats':
            await self.message_stats(msg=msg, cmd=cmd)
        return True

    async def ranked_trio_memes(self, msg):
        if msg.guild.id not in {288545683462553610, 150236153910394881,
                                324981224110030848, 589381124325900291,
                                612501390681702432}:
            return

        await self.get_his_ass(msg)
        await self.already_tracer(msg)
        await self.cee_lo(msg)
        await self.cheels(msg)
        await self.doundrissit(msg)
        await self.corolla(msg)
        await self.and_i_oop(msg)
        await self.sans(msg)
        await self.vsauce(msg)
        await self.but_i_love_chef(msg)
        await self.sayori(msg)

    @staticmethod
    def create_help_embed(command_name: str,
                          command_str: str,
                          desc: str,
                          aliases: Optional[Tuple[str]] = None,
                          **params: str):
        help_text = (
                f'`{command_str}`\n'
                f'*<required> [optional] option1*|*option2*\n\n'
                f'**Description:**  {desc}\n'
                f'**Aliases:**  {", ".join(aliases) if aliases else "None"}\n\n'
                f'**__Parameters__**\n'
                + '\n'.join(f'`{p}`:  {desc}' for p, desc in params.items())
        )
        return discord.Embed(title=f'*{command_name}* command usage',
                             description=help_text,
                             color=0x8472DF)

    @staticmethod
    def create_embed_from_msgs(
            msgs: Union[Sequence[discord.Message], discord.Message]):
        if isinstance(msgs, discord.Message):
            msgs = [msgs]
        elif not isinstance(msgs, Sequence):
            raise ValueError(f'msgs should be of type Sequence, '
                             f'not {type(msgs)}')

        desc = '\n'.join([m.content for m in msgs])
        timestamp = msgs[0].created_at
        color = msgs[0].author.color
        author_name = msgs[0].author.name
        channel_name = msgs[0].channel.name
        avatar_url = msgs[0].author.avatar_url
        embed = discord.Embed(description=desc,
                              timestamp=timestamp,
                              color=color)
        embed.set_author(name=f'{author_name} in #{channel_name}',
                         icon_url=avatar_url)

        if msgs[0].embeds:
            # Note that there could be multiple embeds and we're only taking 1
            if msgs[0].embeds[0].type == 'image':
                embed.set_image(url=msgs[0].embeds[0].url)
            else:
                embed.description += f'\n{msgs[0].embeds[0].description}'

        elif msgs[0].attachments:
            if (msgs[0].attachments[0].filename.split('.')[-1]
                    in {'bmp', 'gif', 'jpg', 'jpeg', 'png', 'webp'}):
                embed.set_image(url=msgs[0].attachments[0].url)
            else:
                embed.description += f'\n{msgs[0].attachments[0]}'

        embed.description += f'\n\n[[Context]]({msgs[0].jump_url})'
        return embed

    async def repeat_command_reaction(self, reaction: discord.Reaction,
                                      user: discord.User):
        if reaction.emoji != REPEAT_EMOJI:
            return False

        chan = reaction.message.channel
        last_command = self.channel_memory[chan]['last_command']
        if not last_command:
            return False

        last_command, sent_msg = last_command
        if reaction.message.id != sent_msg.id:
            return False

        await reaction.remove(self.user)
        await reaction.remove(user)
        await self.again(reaction.message)
        return True

    async def ping(self, msg):
        chan = msg.channel
        await chan.send(':)')

    async def help(self, msg: discord.Message, cmd: ParsedCommand):
        chan = msg.channel
        color = 0x8472DF

        specified_command = cmd.command.value
        if specified_command:
            base = Grammar.find_base(specified_command, resolve_aliases=True)
            if base:
                # noinspection PyShadowingBuiltins
                help = base.get_help()
                embed = discord.Embed(title=f'**{base.name}**',
                                      description=help.description,
                                      color=color)
                subcommands = (', '.join([f'`{s}`' for s in help.subcommands])
                               if help.subcommands else 'None')
                embed.add_field(name='Subcommands',
                                value=subcommands,
                                inline=False)
                for name, desc, alias, shorthand, optional in help.params:
                    title = name
                    if alias:
                        title += f'/{alias}'
                    if shorthand:
                        title += f'  [{shorthand}]'
                    if optional:
                        title += f'  *(optional)*'
                    embed.add_field(name=title, value=desc, inline=False)
            else:
                embed = discord.Embed(title='This command doesn\'t exist',
                                      description='≳⋄≲',
                                      color=color)
        else:
            command_names = f'\n- '.join(Grammar.get_command_names())
            desc = (
                f'**__Available commands__**\n'
                f'- {command_names}\n\n'
                f'Type `help <command>` to see help for that command.'
            )
            embed = discord.Embed(title="Hawkbot help",
                                  description=desc,
                                  color=color)
        await chan.send(embed=embed)

    async def send_config_msg(self, channel: discord.TextChannel,
                              title: str, description: Optional[str] = None):
        color = 0x00C200
        embed = discord.Embed(title=title, description=description,
                              color=color)
        await channel.send(embed=embed)

    async def config(self, msg: discord.Message, cmd: ParsedCommand):
        chan: discord.TextChannel = msg.channel
        guild: discord.Guild = msg.guild

        subcommand = cmd.base.path[1]
        if subcommand == 'pins_channel':
            action = cast(ChoiceParam, cmd.action).value

            if action is None:
                # Get
                pins_channel = db.config.get_pins_channel(guild.id)
                pins_channel_name = 'None'
                if pins_channel:
                    pins_channel_name = \
                        f'#{guild.get_channel(pins_channel).name}'
                await self.send_config_msg(chan, 'Current pins channel',
                                           pins_channel_name)

            elif action == 'set':
                db.config.set_pins_channel(guild.id, chan.id)
                await self.send_config_msg(chan, 'Pins channel set')

            elif action == 'remove':
                db.config.set_pins_channel(guild.id, None)
                await self.send_config_msg(chan, 'Pins channel removed')

        elif subcommand == 'prefix':
            action = cmd.base.path[2] if len(cmd.base.path) == 3 else None

            if action is None:
                # Get
                current_prefix = self.prefixes[guild.id]
                await self.send_config_msg(chan, 'Current prefix',
                                           f'"{current_prefix}"')

            elif action == 'set':
                new_prefix = cast(QuotedStringParam, cmd.prefix).value
                self.prefixes[guild.id] = new_prefix
                await self.send_config_msg(chan,
                                           f'Changed command prefix to '
                                           f'{new_prefix}')

            elif action == 'reset':
                self.prefixes[guild.id] = None
                await self.send_config_msg(chan,
                                           f'Reset command prefix to '
                                           f'"{self.default_prefix}"')

        elif subcommand == 'download_channels_blacklist':
            action = cast(ChoiceParam, cmd.action).value

            if action is None:
                # Get
                channel_ids = db.config.get_channel_download_blacklist(guild.id)
                channel_names = []
                # noinspection PyShadowingBuiltins
                for id in channel_ids:
                    channel_names.append(guild.get_channel(id).name)
                channel_names = (', '.join(channel_names)
                                 if channel_names else 'None')
                await self.send_config_msg(chan,
                                           'Download blacklisted channels',
                                           channel_names)

            elif action == 'add':
                db.config.add_channel_to_download_blacklist(guild.id, chan.id)
                await self.send_config_msg(chan,
                                           'Added this channel to the '
                                           'download blacklist')

            elif action == 'remove':
                db.config.remove_channel_from_download_blacklist(guild.id,
                                                                 chan.id)
                await self.send_config_msg(chan,
                                           'Removed this channel to the '
                                           'download blacklist')

    async def again(self, msg):
        chan = msg.channel
        last_cmd: LastCommand = self.channel_memory[chan]['last_command'][0]
        if not last_cmd:
            return False
        result = await last_cmd.function(self, msg=last_cmd.msg,
                                         cmd=last_cmd.cmd,
                                         *last_cmd.args, **last_cmd.kwargs)
        return result

    async def cleanse(self, msg):
        chan = msg.channel
        await chan.send('```.' + '\n'*50 + '.```')

    async def gdrive_direct_link(self, msg: discord.Message,
                                 cmd: ParsedCommand):
        chan = msg.channel
        gdrive_link = misc_utils.gdrive_direct_link(cmd.url)
        if gdrive_link:
            await chan.send(gdrive_link)
            return True
        return False

    async def quote_link(self, msg: discord.Message, cmd: ParsedCommand):
        chan = msg.channel

        url1 = cast(DiscordMessageURLParam, cmd.url1)
        url2 = cast(DiscordMessageURLParam, cmd.url2)

        if url2 and url1.channel_id != url2.channel_id:
            raise UserFeedbackError('Messages must be from the same channel.')

        channel = self.get_channel(url1.channel_id)
        if not channel:
            raise UserFeedbackError(chan, 'I can\'t access this channel.')

        from_msg = await channel.fetch_message(url1.message_id)

        if url2:
            to_msg = await channel.fetch_message(url2.message_id)

            if from_msg.created_at > to_msg.created_at:
                await send_error(
                    chan, 'Start message must come before end message.')
                return True

            quoted_msgs = [from_msg] + await channel.history(
                after=from_msg,
                before=to_msg,
                limit=20
            ).flatten() + [to_msg]
        else:
            quoted_msgs = from_msg

        embed = self.create_embed_from_msgs(quoted_msgs)
        embed.set_footer(text=f'Quoted by {msg.author.name}',
                         icon_url=msg.author.avatar_url)

        try:
            await msg.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass
        await chan.send(embed=embed)

    async def channel_portal(self, msg: discord.Message, cmd: ParsedCommand):
        channel_in = msg.channel

        channel_out = cmd.channel.resolve(msg.guild).channels[0]

        await msg.delete()

        embed_out = discord.Embed(title=f'Portal from {channel_in.name}',
                                  color=0xFFA600)
        portal_out = await channel_out.send(embed=embed_out)

        embed_in = discord.Embed(title=f'Portal to {channel_out.name}',
                                 description=f'**[( )]({portal_out.jump_url})**',
                                 color=0x006DFF)
        portal_in = await channel_in.send(embed=embed_in)

        embed_out.description = f'**[( )]({portal_in.jump_url})**'
        await portal_out.edit(embed=embed_out)

        return True

    async def vibe_check(self, msg: discord.Message):
        chan = msg.channel
        await chan.send(commands.vibe_check())

    async def init_guild(self, msg: discord.Message):
        db.main.init_guild(msg.guild)

    async def download_messages(self, msg: discord.Message, cmd: ParsedCommand):
        chan = msg.channel

        if not cmd.channels.names:
            channels = msg.guild.text_channels
        else:
            channels = cmd.channels.resolve(msg.guild).channels
            if not channels:
                await send_error(chan, 'Could not find this channel.')
                return True

        embed = discord.Embed(title='Downloading channels')
        for c in channels:
            embed.add_field(name=c.name, value='⬛', inline=False)

        msg: discord.Message = await chan.send(embed=embed)
        await asyncio.sleep(0.25)

        for i, c in enumerate(channels):
            embed.set_field_at(i, name=embed.fields[i].name,
                               value='🕗', inline=False)
            await msg.edit(embed=embed)

            start_time = datetime.now()
            # noinspection PyBroadException
            try:
                await db.messages.download_messages(c)
            except db.messages.SkippedBlacklistedChannel:
                display_text = '↩ Channel skipped (blacklisted)'
            except discord.errors.Forbidden:
                display_text = '⚠ Channel access denied'
            except Exception:
                logger.error('Uncaught exception in download:\n', exc_info=True)
                display_text = '⚠ Runtime error'
            else:
                display_text = '✅'

            time_elapsed = round((datetime.now() - start_time).total_seconds(),
                                 2)
            display_text += f' ({time_elapsed} s)'
            embed.set_field_at(i, name=embed.fields[i].name,
                               value=display_text, inline=False)
        await msg.edit(embed=embed)

    async def create_chain(self, msg: discord.Message):
        chan = msg.channel

        embed = discord.Embed(title='Markov chain')
        embed.add_field(name='Generating chain', value='🕗', inline=False)

        msg: discord.Message = await chan.send(embed=embed)

        start_time = datetime.now()
        # noinspection PyBroadException
        try:
            # Run without blocking
            await self.loop.run_in_executor(None, db.markov.create_chain,
                                            msg.guild.id)
        except Exception as e:
            logger.error(e)
            display_text = '⚠ Runtime error'
        else:
            display_text = '✅'

        time_elapsed = round((datetime.now() - start_time).total_seconds(), 2)
        display_text += f' ({time_elapsed} s)'
        embed.set_field_at(0, name=embed.fields[0].name,
                           value=display_text, inline=False)
        await msg.edit(embed=embed)

    @repeatable
    async def generate_message(self, msg: discord.Message,
                               cmd: ParsedCommand):
        chan = msg.channel

        algorithm = cmd.algorithm.value
        if algorithm in {'1', 'original', 'markov'}:
            generation_function = commands.generate_message
        # elif algorithm in {'2', 'madlibs'}:
        #     generation_function = commands.generate_message2
        else:
            raise UserFeedbackError(f'This algorithm ({algorithm}) does not '
                                    f'exist')

        users = cast(UsersParam, cmd.users)
        if users.names == ['me']:
            user_ids = msg.author.id
            color = msg.author.color
            output_name = msg.author.name
        elif users:
            users.resolve(msg.guild)
            if len(users.users) == 1:
                color = users.users[0].color
            else:
                # Randomize the embed color if multiple users used
                color = misc_utils.random_color()
            user_ids = users.ids
            output_name = misc_utils.merge_names(users.names)
        else:
            user_ids = None
            output_name = misc_utils.merge_names(
                [u.name for u in dc_utils.get_non_bot_users(msg.guild)])
            color = misc_utils.random_color()

        channels = cast(ChannelsParam, cmd.channels)
        channel_id = None
        if channels:
            channels.resolve(msg.guild)
            channel_id = channels.ids[0]

        limit_min = cast(LimitParam, cmd.limit).min
        limit_max = cast(LimitParam, cmd.limit).max
        count = cast(CountParam, cmd.count).count

        blueprint = cast(QuotedStringParam, cmd.blueprint)
        multiline = blueprint.quote_type == '`'
        if multiline:
            blueprints = blueprint.value.split('\n')
        else:
            blueprints = [blueprint.value]

        final_msgs = []
        for i in range(count):
            this_iter = []
            for blueprint in blueprints:
                generation = generation_function(
                    msg.guild.id,
                    users=user_ids,
                    channel=channel_id,
                    blueprint=blueprint, word_limit=(limit_min, limit_max)
                )
                this_iter.append(generation)
            final_msgs.append('\n\n'.join(this_iter))
        final_msg = '\n\n'.join(final_msgs)
        embed = discord.Embed(description=final_msg,
                              title=f'{output_name} once said...',
                              color=color)
        gen_msg = await chan.send(embed=embed)

        # AI generated image for content
        # image = gan_image(final_msg)
        # if image:
        #     await chan.send(file=discord.File(image, 'rquote.jpg'))

        return gen_msg

    @repeatable
    async def random_quote(self, msg: discord.Message,
                           cmd: ParsedCommand):
        chan = msg.channel

        user_ids = None
        hide_author = cmd.base.name == 'rquote guess'
        if not hide_author and cmd.users:
            users = cast(UsersParam, cmd.users)
            users.resolve(msg.guild)
            user_ids = users.ids

        channels = cast(ChannelsParam, cmd.channels)
        channel_id = None
        if channels:
            channels.resolve(msg.guild)
            channel_id = channels.ids[0]

        limit_min = cast(LimitParam, cmd.limit).min
        limit_max = cast(LimitParam, cmd.limit).max
        count = cast(CountParam, cmd.count).count

        sent_msg = None
        for msg in commands.random_message(msg.guild.id, users=user_ids,
                                           channel=channel_id,
                                           word_limit=(limit_min, limit_max),
                                           count=count, content=True):
            embed = discord.Embed(description=msg.content,
                                  title=msg.author.name,
                                  timestamp=msg.created_at,
                                  color=misc_utils.random_color())
            if hide_author:
                embed.title = '???'
                sent_msg = await chan.send(embed=embed)
                await sent_msg.add_reaction('❔')

                rquote_memory = self.channel_memory[chan]['rquote']
                rquote_memory[sent_msg.id] = msg
            else:
                embed.description += f'\n[[Context]]({msg.jump_url})'
                sent_msg = await chan.send(embed=embed)

            # AI generated image for content
            # image = gan_image(msg.content)
            # if image:
            #     await chan.send(file=discord.File(image, 'rquote.jpg'))

            await asyncio.sleep(0.25)
        return sent_msg or True

    async def random_quote_reveal(self, reaction, user):
        msg = reaction.message
        chan = msg.channel
        mem = self.channel_memory[chan]['rquote']
        if msg.id not in mem:
            return False
        if reaction.emoji != '❔':
            return False
        r_msg = mem[msg.id]
        embed = msg.embeds[0]
        embed.title = r_msg.author.name
        embed.description += f'\n[[Context]]({r_msg.jump_url})'
        await reaction.remove(user)
        await reaction.remove(self.user)
        await msg.edit(embed=embed)

    @repeatable
    async def random_image(self, msg: discord.Message,
                           cmd: ParsedCommand):
        chan = msg.channel

        users = cast(UsersParam, cmd.users)
        user_ids = None
        if users:
            users.resolve(msg.guild)
            user_ids = users.ids

        channels = cast(ChannelsParam, cmd.channels)
        channel_id = None
        if channels:
            channels.resolve(msg.guild)
            channel_id = channels.ids[0]

        count = cast(CountParam, cmd.count).count

        sent_msg = None
        for msg in commands.random_message(msg.guild.id, users=user_ids,
                                           channel=channel_id, count=count,
                                           images=True):
            embed = discord.Embed(title=msg.author.name,
                                  description=f'\n[[Context]]({msg.jump_url})',
                                  timestamp=msg.created_at,
                                  color=misc_utils.random_color())
            image_url = random.choice(msg.images)
            embed.set_image(url=image_url)
            sent_msg = await chan.send(embed=embed)
        return sent_msg or True

    async def message_stats(self, msg: discord.Message, cmd: ParsedCommand):
        chan = msg.channel

        plot = cmd.base.name == 'mstats plot'

        users = cast(UsersParam, cmd.users)
        user_ids = None
        if users:
            users.resolve(msg.guild)
            user_ids = users.ids

        channels = cast(ChannelsParam, cmd.channels)
        channel_ids = None
        if channels:
            channels.resolve(msg.guild)
            channel_ids = channels.ids

        flags = cast(FlagsParam, cmd.flags).flags
        case_sensitive = 'c' in flags
        anywhere = 'a' in flags

        pattern = cast(QuotedStringParam, cmd.pattern)
        search_pattern = pattern.value
        if not pattern.is_regex:
            search_pattern = re.escape(search_pattern)
        if not anywhere:
            search_pattern = rf'\b{search_pattern}\b'

        # Execute
        stats = commands.message_stats(
            msg.guild.id, search_pattern, users=user_ids,
            channels=channel_ids, case_sensitive=case_sensitive, plot=plot)

        if not plot:
            title = 'Stats for {}'.format(f'regex pattern /{pattern.value}/'
                                          if pattern.is_regex
                                          else f'phrase "{pattern.value}"')
            embed = discord.Embed(title=title, description=str(stats),
                                  color=0x6C7EFF)
            await chan.send(embed=embed)
            return True
        else:
            await chan.send(file=discord.File(stats, 'mstats_result.png'))

    async def pin_msg(self, payload: discord.RawReactionActionEvent):
        if payload.emoji.name != '📌':
            return False

        chan: discord.TextChannel = self.get_channel(payload.channel_id)
        guild: discord.Guild = chan.guild
        pinner = await self.fetch_user(payload.user_id)
        orig_msg: discord.Message = await chan.fetch_message(payload.message_id)

        if db.pins.get_pin_msg_id(orig_msg.guild.id, orig_msg.id):
            return True

        pins_channel = db.config.get_pins_channel(orig_msg.guild.id)
        if pins_channel is None:
            await send_error(orig_msg.channel, ErrorStrings.no_pins_channel)
            return True
        pins_channel = guild.get_channel(pins_channel)

        embed = self.create_embed_from_msgs(orig_msg)
        embed.set_footer(text=f'Pinned by {pinner.name}',
                         icon_url=pinner.avatar_url)
        try:
            pinned_msg = await pins_channel.send(embed=embed)
        except discord.Forbidden:
            await send_error(orig_msg.channel,
                             f'Bot is not allowed to post in your pins '
                             f'channel (#{pins_channel.name}).')
        except discord.HTTPException as e:
            await send_error(orig_msg.channel, e)
        else:
            db.pins.pin_message(guild.id, orig_msg.id, pinned_msg.id)

        return True

    async def unpin_msg(self, payload: discord.RawReactionActionEvent):
        if payload.emoji.name != '📌':
            return False

        chan: discord.TextChannel = self.get_channel(payload.channel_id)
        guild: discord.Guild = chan.guild
        orig_msg: discord.Message = await chan.fetch_message(payload.message_id)

        pinned_msg_id = db.pins.unpin_message(guild.id, orig_msg.id)
        if not pinned_msg_id:
            return False

        pins_channel = db.config.get_pins_channel(guild.id)
        if not pins_channel:
            await send_error(orig_msg.channel, ErrorStrings.no_pins_channel)
        pins_channel: discord.TextChannel = guild.get_channel(pins_channel)

        pinned_msg = await pins_channel.fetch_message(pinned_msg_id)
        try:
            await pinned_msg.delete()
        except discord.Forbidden:
            await send_error(orig_msg.channel,
                             f'Bot is not allowed to delete this pin in your '
                             f'pins channel (#{pins_channel.name})')
        except discord.HTTPException as e:
            await send_error(orig_msg.channel, e)

    # Ranked Trio memes

    async def get_his_ass(self, msg):
        chan = msg.channel
        mem = self.channel_memory[chan]['get_his_ass']
        mem.append(msg)

        if not msg.content:
            # Empty message
            return False
        if len(mem) != mem.maxlen:
            # Don't have memory filled yet, which means comparisons will be
            # unreliable; skip
            return False

        users = [m.author for m in tuple(mem)[1:]]
        contents = [m.content for m in tuple(mem)[1:]]
        if len(set(users)) != len(users):
            # Repeated user; skip
            return False
        elif len(set(contents)) != 1:
            # Different messages; skip
            return False

        predicted_gettee = mem[0].author.id
        pronoun = 'her' if predicted_gettee in {150722990663925760} else 'his'

        await chan.send(msg.content)
        await asyncio.sleep(1.0)
        await play_audio_file(msg, 'gha.wav')
        await chan.send(f'get {pronoun} ass')

    async def already_tracer(self, msg):
        chan = msg.channel
        search = re.search(r"(?:i(?:m|'m| am|d|'d| would)? ?"
                           "(?:wanna|want to|going to|gonna|like to) "
                           # "be|(?:what|how) about) (.+)",
                           "be) (.+)",
                           msg.content, flags=re.I)
        if search:
            if search.group(1) == 'bastion':
                await chan.send('nerf bastion')
            else:
                await chan.send(f"I'm already {search.group(1)}")

    async def cee_lo(self, msg):
        me = msg.guild.me
        if re.search(r'(?:cee ?lo|get (?:your|ur) ass back here)',
                     msg.content, flags=re.I):
            ceelo = ('get', 'your', ('a', 's', '5\U000020e3'), 'back',
                     ('h', 'e', 'r', '3\U000020e3'))
            await play_audio_file(msg, 'get_your_ass_back_here.wav')
            await msg.add_reaction('▪')
            for word in ceelo:
                to_remove = []
                for c in word:
                    c = EMOJIS[c] if len(c) == 1 else c
                    to_remove.append(c)
                    await msg.add_reaction(c)
                await asyncio.sleep(0.6)
                for e in to_remove[::-1]:
                    await msg.remove_reaction(e, me)
            await msg.remove_reaction('▪', me)

    async def cheels(self, msg):
        chan = msg.channel
        if 'cheels' in msg.content.lower():
            await play_audio_file(msg, 'cheels.wav')
            await chan.send('https://cdn.discordapp.com/attachments/'
                            '377548983477731328/548273283175284771/'
                            '2019-02-21_17-41-50.gif')
        elif 'wa ah' in msg.content.lower():
            await play_audio_file(msg, 'wa_ah.wav')

    async def doundrissit(self, msg):
        content = msg.content.lower()
        folder = Path('doundrissit')
        if re.search(r'sc?hlow down', content):
            await play_audio_file(msg, folder / 'schlow_down.wav')
        elif re.search(r'rawky', content):
            await play_audio_file(msg, folder / 'rawky.wav')
        elif re.search(r'(?:slide down|doundrissit)', content):
            await play_audio_file(msg, folder / 'doundrissit.wav')
        elif re.search(r'chooses combat gear', content):
            await play_audio_file(msg, folder / 'chooses_combat_gear.wav')
        elif re.search(r'w[ao]lnum bolt?', content):
            await play_audio_file(msg, folder / 'walnum_bolt.wav')
        elif re.search(r'mother of god', content):
            await play_audio_file(msg, folder / 'mother_of_god.wav')
        elif re.search(r'mulled good', content):
            await play_audio_file(msg, folder / 'mulled_good_baby.wav')
        elif re.search(r'nill[yi] heeyah?', content):
            await play_audio_file(msg, folder / 'nilly_heeya.wav')
        elif re.search(r'(?:youorai|are you (?:alright|all right))', content):
            await play_audio_file(msg, folder / 'youorai.wav')

    async def corolla(self, msg):
        content = msg.content.lower()
        folder = Path('corolla')
        if re.search(r'a to b', content):
            await play_audio_file(msg, folder / 'a_to_b.wav')
        elif re.search(r'be that guy', content):
            await play_audio_file(msg, folder / 'be_that_guy.wav')
        elif re.search(r'coffee to strangers', content):
            await play_audio_file(msg, folder / 'coffee_to_strangers.wav')
        elif re.search(r'i wrote that book', content):
            await play_audio_file(msg, folder / 'i_wrote_that_book.wav')
        elif re.search(r'my dad', content):
            await play_audio_file(msg, folder / 'my_dad.wav')
        elif re.search(r'used to have a corolla', content):
            await play_audio_file(msg, folder / 'used_to_have_a_corolla.wav')
        elif re.search(r'yes,? i know that', content):
            await play_audio_file(msg, folder / 'yes_i_know_that.wav')
        elif re.search(r'you got here first', content):
            await play_audio_file(msg, folder / 'you_got_here_first.wav')

    async def and_i_oop(self, msg):
        content = msg.content.lower()
        if 'and i oop' in content:
            await play_audio_file(msg, 'and_i_oop.wav')

    async def sans(self, msg):
        content = msg.content.lower()
        if content == 'sans':
            await play_audio_file(msg, 'sans.wav')

    async def vsauce(self, msg):
        content = msg.content.lower()
        if content == 'v':
            await play_audio_file(msg, 'vsauce.wav')

    async def but_i_love_chef(self, msg):
        content = msg.content.lower()
        if content == 'but i love chef':
            await play_audio_file(msg, 'but_i_love_chef.wav')

    async def sayori(self, msg):
        content = msg.content.lower()
        if content in {'sayori', 'sayonara', 'door'}:
            await play_audio_file(msg, 'd.wav')


if __name__ == '__main__':
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s'))
    logger.addHandler(handler)

    # discord.opus.load_opus('libopus-0.x64.dll')

    hawkbot = Hawkbot()
    try:
        hawkbot = hawkbot.run(config['discord']['bot_token'])
    except KeyboardInterrupt:
        hawkbot.stop()
