from io import StringIO
import logging
import shlex
import string
from typing import List, Optional, cast

from commands.parser.enums import ParsingMode
from commands.parser.grammar import Grammar, CommandGrammar

logger = logging.getLogger(__name__)


class NoCommandFound(Exception):

    __slots__ = ['command']

    def __init__(self, command: str):
        self.command = command


class UnknownArgument(Exception):

    __slots__ = ['base_name', 'arg']

    def __init__(self, base_name, arg):
        self.base_name = base_name
        self.arg = arg

    def __str__(self):
        return f'command {self.base_name} cannot parse argument {self.arg}'


class ChangeParsingMode(Exception):

    __slots__ = ['mode']

    def __init__(self, mode: ParsingMode):
        self.mode = mode


class ParsedCommand:

    __slots__ = ['base', '_args', '_args_encountered', '_mode',
                 '_current_pos']

    def __init__(self):
        self.base: Optional[CommandGrammar] = None
        self._args = {}
        self._args_encountered = False
        self._mode = False
        self._current_pos = 0

    def __str__(self):
        if self.base:
            return f'<ParsedCommand base={self.base.name!r} args={self._args}>'
        else:
            return f'<ParsedCommand empty>'

    def __getattr__(self, arg):
        if arg in self._args:
            return self._args[arg]
        raise AttributeError(f'{arg} argument not found in command {self}')

    def __bool__(self):
        return self.base is not None

    def set_base(self, base: CommandGrammar):
        self.base = base
        self._args = base.get_all_params() if base else {}
        if base.mode is not self._mode:
            # The type of parsing is changing now; signal up to the parser
            self._mode = base.mode
            raise ChangeParsingMode(base.mode)

    def add(self, item: str, data: Optional[List] = None):
        # Interpretation function
        if not self.base:
            # Beginning of command
            base = Grammar.find_base(item)
            if base:
                self.set_base(base)
            else:
                raise NoCommandFound(item)
        else:
            if not self._args_encountered and not data:
                # May be a subcommand, like 'ms plot ...'
                subcommand = self.base.get_subcommand(item)
                if subcommand:
                    self.set_base(Grammar.find_base(subcommand))
                    return

            # Interpret this argument; it may be shorthand notation
            self.base = cast(CommandGrammar, self.base)

            if self._mode is ParsingMode.LEXICAL:
                if data:
                    name = self.base.get_param_name(name=item)
                    arg = data
                    logger.debug(f'named arg: name={name} arg={arg}')
                else:
                    name = self.base.get_param_name(arg=item)
                    arg = item
                    logger.debug(f'shorthand arg: name={name} arg={arg}')

            elif self._mode in {ParsingMode.POSITIONAL, ParsingMode.REST}:
                name = self.base.get_param_name(pos=self._current_pos)
                arg = item
                logger.debug(f'positional arg: name={name} arg={arg}')
                self._current_pos += 1

            else:
                raise ValueError(f'Parsing mode {self._mode} is not valid')

            if name:
                self._args_encountered = True
                self._args[name].parse(arg)
            else:
                raise UnknownArgument(self.base.name, arg)


class Parser:

    __slots__ = ['lexer']
    lexical_parsing_wordchars = (
        string.ascii_letters + string.digits
        + ''.join(set(string.punctuation) - set('"\'(),;[]`{}')))
    positional_parsing_wordchars = (
        ''.join(set(string.printable) - set(string.whitespace) - set('"\'')))

    def __init__(self):
        self.lexer = shlex.shlex(StringIO())
        self.lexer.commenters = ''
        self.lexer.quotes = '\'"`'

    def __call__(self, command: str):
        return self.parse_command(command)

    def set_parse_mode(self, mode: ParsingMode):
        if mode is ParsingMode.LEXICAL:
            self.lexer.wordchars = self.lexical_parsing_wordchars
        elif mode is ParsingMode.POSITIONAL:
            self.lexer.wordchars = self.positional_parsing_wordchars
        else:
            raise ValueError(f'Parsing mode {mode} is not valid')

    def parse_sequence(self):
        seq = []
        item = None
        while item != ']':
            item = self.parse_token()
            if item != ']':
                seq.append(item)
        return seq

    parser_map = {
        '': lambda x: None,
        '[': parse_sequence,
    }

    def parse_token(self):
        token: str = self.lexer.get_token()
        if token in self.parser_map:
            # noinspection PyUnresolvedReferences
            return self.parser_map[token](self)
        return token

    def parse_command(self, command: str) -> Optional[ParsedCommand]:
        self.lexer.state = ' '  # took forever to figure this out
        self.set_parse_mode(ParsingMode.LEXICAL)
        command_stream = StringIO(command)
        self.lexer.instream = command_stream

        command = ParsedCommand()
        prev_arg = arg = self.parse_token()
        try:
            while arg is not None:
                arg = self.parse_token()

                if isinstance(arg, list):
                    # This arg is a list, so its associated argument name
                    # should be in prev_arg
                    command.add(prev_arg, data=arg)
                    prev_arg = None

                elif prev_arg:
                    # prev_arg is either a subcommand or a positional arg
                    prev_arg = cast(str, prev_arg)
                    try:
                        command.add(prev_arg)
                    except ChangeParsingMode as e:
                        # prev_arg was a subcommand and we're changing parsing
                        # modes now
                        if e.mode is ParsingMode.REST:
                            # Read the rest of the stream and break token
                            # loop
                            rest = command_stream.read()
                            if rest:
                                command.add(f'{arg} {rest}')
                            else:
                                command.add(arg)
                            break
                        else:
                            self.set_parse_mode(e.mode)
                    prev_arg = arg

                else:
                    # We had just consumed a named arg, so prev_arg isn't set
                    prev_arg = arg

        except NoCommandFound as e:
            logger.debug(f'Command not found: {e.command}')
            return None
        except UnknownArgument as e:
            logger.debug(f'Unknown argument: {e.args}')
            return None

        return command if command else None


if __name__ == '__main__':
    p = Parser()
    print(p('config pins_channel set'))
