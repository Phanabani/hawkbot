from __future__ import annotations
import abc
import re
from typing import List, Union, Optional, Set, TypeVar

import discord

from utils.errors import UserFeedbackError

__all__ = ['ParameterBase', 'StringParam', 'ChoiceParam',
           'DiscordMessageURLParam', 'UsersParam', 'ChannelsParam',
           'LimitParam', 'CountParam', 'QuotedStringParam', 'FlagsParam']

ParameterSubclassType = TypeVar('ParameterSubclassType', bound='ParameterBase')
DiscordResolvableSubclassType = TypeVar('DiscordResolvableSubclassType',
                                        bound='ParameterBase')
DiscordResolvableDataType = TypeVar('DiscordResolvableDataType')


class ParameterBase(abc.ABC):

    shorthand = None
    pattern = re.compile('')
    printable_attrs: Optional[List[str]] = None
    help = 'No description'

    # noinspection PyShadowingBuiltins
    def __init__(self, alias: Optional[str] = None, optional: bool = False,
                 help: Optional[str] = None):
        self.alias = alias
        self.optional = optional
        if help is not None:
            self.help = help

    def __str__(self):
        if self.printable_attrs:
            attr_names = self.printable_attrs
        else:
            attr_names = [n for n in self.__slots__ if not n.startswith('_')]
        attrs = ' '.join([f'{a}={getattr(self, a)!r}' for a in attr_names])

        return f'<{self.__class__.__name__} {attrs}>'

    __repr__ = __str__

    def raise_parsing_error(self, arg: str):
        raise ValueError(f'argument could not be parsed '
                         f'by {self.__class__.__name__}: {arg}')

    def match(self, arg):
        match = self.pattern.match(arg)
        if not match:
            self.raise_parsing_error(arg)
        return match

    @classmethod
    def test(cls, arg: str) -> bool:
        """
        Test whether a string is a shorthand representation of this parameter

        :param arg: string argument to test
        :return: whether this string is a shorthand representation of this
            parameter
        """
        return bool(cls.pattern.match(arg))

    @abc.abstractmethod
    def parse(self, arg: Union[str, List[str]]) -> ParameterSubclassType:
        """
        Parse a string argument and return self with parsed components

        :param arg: string argument to parse as this parameter type
        :return: self with instance variables containing parsed data
        """
        pass


class StringParam(ParameterBase):

    __slots__ = ['value']
    help = 'A text string'

    def __init__(self, **kwargs):
        super(StringParam, self).__init__(**kwargs)
        self.value: Optional[str] = None

    @classmethod
    def test(cls, arg: str) -> bool:
        return True

    def parse(self, arg: str) -> StringParam:
        self.value = arg
        return self


class ChoiceParam(ParameterBase):

    __slots__ = ['value', 'choices', '_default']

    def __init__(self, choices: Set[str], default: Optional[str] = None,
                 **kwargs):
        super(ChoiceParam, self).__init__(**kwargs)
        self.value: Optional[str] = default
        self.choices: Set[str] = choices
        self._default = default

    # @property
    # def help(self):
    #     return f'Any one of the following choices: {", ".join(self.choices)}'

    @classmethod
    def test(cls, arg: str) -> bool:
        # Should test become an instance method to support testing of set
        # membership?
        return True

    def parse(self, arg: Union[str, List[str]]) -> ParameterSubclassType:
        if isinstance(arg, list):
            arg = arg[0]
        if arg in self.choices:
            self.value = arg
        return self


class DiscordMessageURLParam(ParameterBase):

    __slots__ = ['url', 'guild_id', 'channel_id', 'message_id']
    help = 'A Discord message URL (right click message -> copy message link)'
    pattern = re.compile(r'^https://discordapp\.com/channels'
                         r'/(?P<guild>\d+)'
                         r'/(?P<channel>\d+)'
                         r'/(?P<message>\d+)$')

    def __init__(self, **kwargs):
        super(DiscordMessageURLParam, self).__init__(**kwargs)
        self.url: Optional[str] = None
        self.guild_id: Optional[int] = None
        self.channel_id: Optional[int] = None
        self.message_id: Optional[int] = None

    def __bool__(self):
        return bool(self.url)

    def parse(self, arg: str) -> DiscordMessageURLParam:
        match = self.pattern.match(arg)
        if not match:
            self.raise_parsing_error(arg)

        self.url = arg
        guild = match.group('guild')
        channel = match.group('channel')
        message = match.group('message')
        self.guild_id = int(guild) if guild else None
        self.channel_id = int(channel) if channel else None
        self.message_id = int(message) if message else None

        return self


class DiscordResolvableParam(ParameterBase):

    __slots__ = ['_resolved', '_raw_names', '_names', '_ids']
    printable_attrs = ['names']

    def __init__(self, **kwargs):
        super(DiscordResolvableParam, self).__init__(**kwargs)
        self._resolved: List[DiscordResolvableDataType] = []
        self._raw_names: List[str] = []
        self._names: List[str] = []
        self._ids: List[int] = []

    def __bool__(self):
        return bool(self._raw_names)

    @classmethod
    def test(cls, arg: str) -> bool:
        return False

    def parse(self, arg: List[str]) -> DiscordResolvableSubclassType:
        self._raw_names = arg
        return self

    @abc.abstractmethod
    def _find(self, guild: discord.Guild,
              name: str) -> DiscordResolvableDataType:
        pass

    def resolve(self, guild: discord.Guild) -> DiscordResolvableSubclassType:
        resolved = []
        for name in self._raw_names:
            find = self._find(guild, name.lower())
            if find:
                resolved.append(find)
        self._resolved = resolved
        return self

    @property
    def ids(self):
        if not self._ids:
            self._ids = [r.id for r in self._resolved]
        return self._ids

    @property
    def names(self):
        if self._names:
            return self._names
        elif self._resolved:
            self._names = [r.name for r in self._resolved]
            return self._names
        else:
            return self._raw_names


class UsersParam(DiscordResolvableParam):

    help = 'One or more users to filter by'

    def _find(self, guild: discord.Guild,
              name: str) -> DiscordResolvableDataType:
        for user in guild.members:
            if not user.bot and name in user.name.lower():
                return user
        raise UserFeedbackError(f'User "{name}" could not be found')

    @property
    def users(self):
        return self._resolved


class ChannelsParam(DiscordResolvableParam):

    help = 'One or more channels to filter by'

    def _find(self, guild: discord.Guild,
              name: str) -> DiscordResolvableDataType:
        for channel in guild.text_channels:
            if name in channel.name:
                return channel
        raise UserFeedbackError(f'Channel "{name}" could not be found')

    @property
    def channels(self):
        return self._resolved


class LimitParam(ParameterBase):

    __slots__ = ['min', 'max']
    help = 'Limit by a minimum and/or maximum value'
    shorthand = '5->10 or 5-> or ->10'
    pattern = re.compile(r'(?P<min>\d+)?->(?P<max>\d+)?')

    def __init__(self, **kwargs):
        super(LimitParam, self).__init__(**kwargs)
        self.min: Optional[int] = None
        self.max: Optional[int] = None

    # noinspection PyShadowingBuiltins
    def parse(self, arg: Union[str, List[str]]) -> LimitParam:
        if isinstance(arg, list):
            self.min = int(arg[0])
            self.max = int(arg[1])
        elif isinstance(arg, str):
            match = self.pattern.match(arg)
            if not match:
                self.raise_parsing_error(arg)

            min = match.group('min')
            max = match.group('max')
            self.min = int(min) if min else None
            self.max = int(max) if max else None

        return self


class CountParam(ParameterBase):

    __slots__ = ['count', '_min', '_max', '_default']
    help = 'Repeat a specific number of times'
    shorthand = 'x3'
    pattern = re.compile(r'x(?P<count>\d+)?')

    # noinspection PyShadowingBuiltins
    def __init__(self, min: Optional[int] = None, max: Optional[int] = None,
                 default: Optional[int] = None, **kwargs):
        super(CountParam, self).__init__(**kwargs)
        self._min = min
        self._max = max
        self._default = default
        self.count: Optional[int] = default if default else min if min else None

    def parse(self, arg: Union[str, List[str]]) -> CountParam:
        if isinstance(arg, list):
            self.count = int(arg[0])

        elif isinstance(arg, str):
            match = self.match(arg)
            count = match.group('count')
            self.count = int(count) if count else self.count

        if self.count and self._min:
            self.count = max(self.count, self._min)
        if self.count and self._max:
            self.count = min(self.count, self._max)

        return self


class QuotedStringParam(ParameterBase):

    __slots__ = ['value', 'quote_type', 'is_regex']
    help = 'A quoted text string that may contain spaces'
    shorthand = '\"some text\"'
    pattern = re.compile(r'(?P<quote_type>[\'"`])(?P<is_regex>/?)'
                         r'(?P<string>.*?)'
                         r'(?P=is_regex)(?P=quote_type)')

    def __init__(self, **kwargs):
        super(QuotedStringParam, self).__init__(**kwargs)
        self.value: Optional[str] = None
        self.quote_type: Optional[str] = None
        self.is_regex: bool = False

    def parse(self, arg: Union[str, List[str]]) -> QuotedStringParam:
        if isinstance(arg, list):
            arg = arg[0]

        match = self.match(arg)
        self.value = match.group('string')
        self.quote_type = match.group('quote_type')
        if match.group('is_regex'):
            self.is_regex = True

        return self


class FlagsParam(ParameterBase):

    __slots__ = ['flags', 'allowed_flags']
    help = 'Letter flags to alter command execution'
    shorthand = '-abc'
    pattern = re.compile(r'-(?P<flags>[a-z]+)')

    def __init__(self, allowed_flags: str = '', **kwargs):
        super(FlagsParam, self).__init__(**kwargs)
        self.flags: Set[str] = set()
        self.allowed_flags: Set[str] = set(allowed_flags)

    def parse(self, arg: Union[str, List[str]]) -> FlagsParam:
        if isinstance(arg, list):
            if len(arg) == 1:
                arg = f'-{arg[0]}'
            else:
                arg = f'-{"".join(arg)}'

        match = self.match(arg)
        flags = set(match.group('flags'))
        if flags <= self.allowed_flags:
            self.flags = set(flags)
        else:
            unrecognized_flags = flags - self.allowed_flags
            raise UserFeedbackError(f'Flags {unrecognized_flags} are not'
                                    f'recognized')

        return self
