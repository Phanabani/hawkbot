import asyncio
import discord
from pathlib import Path
from typing import List, Optional, Union

from utils.errors import UserFeedbackError, ErrorStrings
from utils.misc import data_folder_path


async def close_voice(voice):
    await asyncio.sleep(0.5)
    await voice.disconnect(force=True)


def get_close_voice_fn(vc):
    def after(error):
        coro = close_voice(vc)
        fut = asyncio.run_coroutine_threadsafe(coro, vc.loop)
        try:
            fut.result()
        except Exception:
            # an error happened sending the message
            print(f'Exception in get_close_voice_fn: {error}')
    return after


async def play_audio_file(msg: Optional[discord.Message] = None,
                          path: Union[Path, str] = '',
                          voice_channel: Optional[discord.VoiceChannel] = None):
    if msg and msg.guild.voice_client:
        # Don't play anything if it's already in a channel
        return
    volume = 0.1
    path = data_folder_path / 'audio' / path
    if not path.exists():
        raise ValueError(f'File does not exist: {path}')
    if not voice_channel:
        voice_channel = get_voice(msg.author)

    if voice_channel:
        vc = await voice_channel.connect()
        after = get_close_voice_fn(vc)
        src = discord.FFmpegPCMAudio(str(path), options='-v error')
        src = discord.PCMVolumeTransformer(src, volume=volume)
        await asyncio.sleep(0.5)
        vc.play(src, after=after)


def get_message_url(guild_id: int, channel_id: int, message_id: int):
    return f'https://discordapp.com/channels/' \
           f'{guild_id}/{channel_id}/{message_id}'


def get_non_bot_users(guild: discord.Guild):
    return list(filter(lambda u: not u.bot, guild.members))


def get_text_channels(client: discord.Client, guild_id: int,
                      channel_id: Optional[int] = None
                      ) -> List[discord.TextChannel]:
    guild = client.get_guild(guild_id)
    if channel_id:
        return [guild.get_channel(channel_id)]
    return [g for g in guild.channels if isinstance(g, discord.TextChannel)]


def get_voice(member):
    if hasattr(member, 'voice') and member.voice:
        return member.voice.channel


def resolve_channel(guild: discord.Guild,
                    channel_names: List[str]) -> List[discord.TextChannel]:
    channels = []
    for name in channel_names:
        name = name.lower()
        for channel in guild.text_channels:
            if name in channel.name:
                channels.append(channel)
    return channels


def resolve_users(guild: discord.Guild,
                  user_names: List[str]) -> List[discord.User]:
    users = []
    for name in user_names:
        name = name.lower()
        for user in guild.members:
            if not user.bot and name in user.name.lower():
                users.append(user)
    return users


async def send_error(channel: discord.TextChannel,
                     error: Union[Exception, str]):
    if isinstance(error, UserFeedbackError):
        desc = str(error)
    elif isinstance(error, Exception):
        desc = ErrorStrings.translate(error)
    elif isinstance(error, str):
        desc = error
    else:
        raise TypeError(f'error should be one of [Exception, str], not '
                        f'{type(error)} (value={error})')
    embed = discord.Embed(description=desc,
                          title='Error',
                          color=0xFF0000)
    await channel.send(embed=embed)
