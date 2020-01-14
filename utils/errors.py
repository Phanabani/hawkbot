from typing import Union, Tuple, Type

import discord.errors


class UserFeedbackError(Exception):
    pass


class GuildDataError(UserFeedbackError):
    pass


class GuildDataNotExistError(GuildDataError):
    pass


class ErrorStrings:
    no_pins_channel = 'No pins channel is set for this guild.'
    default = 'An error has occurred.'

    _error_map = {
        discord.errors.Forbidden: 'Missing permissions to get message.',
        discord.errors.HTTPException: 'HTTP request failed; try again.',
        discord.errors.NotFound: 'Message could not be found.',
    }

    @classmethod
    def translate(cls, exception: Exception):
        if exception in cls._error_map:
            # noinspection PyTypeChecker
            return cls._error_map[exception]
        return cls.default


def typecheck(value, types: Union[Type, Tuple[Type, ...]], value_name: str):
    if isinstance(value, types):
        return True
    raise TypeError(f'{value_name} should be of type {types}, '
                    f'not {type(value)}')


if __name__ == '__main__':
    typecheck([1, 2, 3], tuple, 'my_list')
