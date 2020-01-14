from __future__ import annotations

from collections import namedtuple
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Type, NamedTuple

from commands.parser.enums import ParsingMode
from commands.parser.parameter_types import *

ParamHelp = namedtuple('ParamHelp', 'name desc alias shorthand optional')
ParamHelpType = NamedTuple('ParamHelpType', name=str, desc=str, alias=str,
                           shorthand=str, optional=bool)


@dataclass
class CommandHelp:
    description: str
    subcommands: List[str, ...] = field(default_factory=list)
    params: List[NamedTuple[str, str], ...] = field(default_factory=list)


class CommandGrammar:

    __slots__ = ['name', 'path', 'root', 'parent', 'mode', 'description',
                 'subcommands', 'parameters', 'positional_order']

    def __init__(self, name: str, mode: Optional[str] = 'lexical'):
        """
        A grammar entry for a command

        :param name: the name of the command
        :param mode: the parsing mode to use for this command
        """
        self.name = name
        self.path = name.split()
        self.parent = self.path[-2] if len(self.path) != 1 else None
        self.root = self.path[0]
        self.mode = ParsingMode(mode)
        self.description = 'No description available'
        self.subcommands = set()
        self.parameters = {}
        self.positional_order: List[str] = []

    def __str__(self):
        return f'<CommandGrammar name={self.name}>'

    def get_help(self) -> CommandHelp:
        command_help = CommandHelp(self.description)
        command_help.subcommands = list(sorted(self.subcommands))
        params = self.get_all_params()
        for name, param in params.items():
            # noinspection PyTypeChecker
            param_help = ParamHelp(name, param.help, param.alias,
                                   param.shorthand, param.optional)
            command_help.params.append(param_help)
        command_help.params = list(sorted(command_help.params,
                                          key=lambda x: x[0]))
        return command_help

    def add_desc(self, desc: str) -> CommandGrammar:
        self.description = desc
        return self

    def add_subcommands(self, *names: str) -> CommandGrammar:
        self.subcommands = self.subcommands | set(names)
        return self

    def get_subcommand(self, name: str) -> Optional[str]:
        if name in self.subcommands:
            return f'{self.name} {name}'
        return None

    # noinspection PyShadowingBuiltins
    def add_param(self, name: str, param: Type[ParameterBase],
                  alias: Optional[str] = None,
                  optional: Optional[bool] = None,
                  help: Optional[str] = None,
                  **kwargs_for_param) -> CommandGrammar:

        if optional is None:
            if self.mode is ParsingMode.LEXICAL:
                optional = True
            else:
                optional = False

        kwargs = {}
        for key, val in kwargs_for_param.items():
            if key.startswith('_'):
                kwargs[key[1:]] = val
        kwargs['alias'] = alias
        kwargs['optional'] = optional
        kwargs['help'] = help

        self.parameters[name] = {
            'parameter': param,
            'has_shorthand': bool(param.shorthand),
            'kwargs': kwargs
        }

        if alias:
            self.parameters[alias] = name

        if self.mode in {ParsingMode.POSITIONAL, ParsingMode.REST}:
            self.positional_order.append(name)

        return self

    def get_all_params(self) -> Dict[str, ParameterBase]:
        params = self.parameters
        return {k: params[k]['parameter'](**params[k]['kwargs'])
                for k in params if isinstance(params[k], dict)}

    def get_param_name(self, name: Optional[str] = None,
                       arg: Optional[str] = None,
                       pos: int = None) -> Optional[str]:
        params = self.parameters
        if name:
            if name in params:
                if isinstance(params[name], str):
                    # This name is an alias
                    name = params[name]
                return name
        elif arg:
            for name, data in self.parameters.items():
                if isinstance(data, dict) and data['has_shorthand']:
                    # Only test parameters that have shorthand representations
                    if data['parameter'].test(arg):
                        # Matched shorthand pattern
                        return name
        elif pos is not None and self.mode in {ParsingMode.POSITIONAL,
                                               ParsingMode.REST}:
            if pos < len(self.positional_order):
                return self.positional_order[pos]
        return None


class Grammar:
    grammar = {
        'ping':
            CommandGrammar('ping')
            .add_desc('Ping Hawkbot to see if he\'s awake'),

        'help':
            CommandGrammar('help', mode='rest')
            .add_desc('View all Hawkbot commands, or see details about a '
                      'specific command')
            .add_param('command', StringParam,
                       help='A command to get help for'),

        # Config command

        'config':
            CommandGrammar('config')
            .add_desc('Configure Hawkbot\'s settings on this server')
            .add_subcommands('pins_channel', 'prefix',
                             'download_channels_blacklist'),

        'config pins_channel':
            CommandGrammar('config pins_channel', mode='positional')
            .add_desc('Lets Hawkbot post custom pinned messages in a specific '
                      'channel (in case another channel has run out of pins '
                      'slots). Run without arguments to show which channel is '
                      'set.')
            .add_param('action', ChoiceParam,
                       _choices={'set', 'remove'},
                       help='`set` this channel as the pins channel or '
                            '`remove` the pins channel.'),

        'config prefix':
            CommandGrammar('config prefix')
            .add_desc('Show the prefix used for Hawkbot commands')
            .add_subcommands('set', 'reset'),

        'config prefix set':
            CommandGrammar('config prefix set', mode='positional')
            .add_desc('Set the prefix used for Hawkbot commands')
            .add_param('prefix', QuotedStringParam),

        'config prefix reset':
            CommandGrammar('config prefix reset')
            .add_desc('Reset the prefix used for Hawkbot commands to default'),

        'config download_channels_blacklist':
            CommandGrammar('config download_channels_blacklist',
                           mode='positional')
            .add_desc('Blacklist certain channels from being downloaded to '
                      'Hawkbot\'s message database. Run without arguments to '
                      'see which channels are currently blacklisted.')
            .add_param('action', ChoiceParam,
                       _choices={'add', 'remove'},
                       help='`add` or `remove` this channel to/from the '
                            'blacklist'),

        # Admin

        'admin':
            CommandGrammar('admin')
            .add_desc('Admin commands which can only be run by the bot owner')
            .add_subcommands('init', 'download', 'chain'),

        'admin init':
            CommandGrammar('admin init').add_subcommands('admin init guild'),
        'admin init guild':
            CommandGrammar('admin init guild')
            .add_desc('Initialize guild database tables'),

        'admin download':
            CommandGrammar('admin download')
            .add_desc('Download messages to Hawkbot\'s database (to enable '
                      'usage of other commands like `admin chain` and '
                      '`rquote`)')
            .add_param('channels', ChannelsParam, alias='c'),

        'admin chain':
            CommandGrammar('admin chain')
            .add_desc('Create markov chain to enable usage of `gen`'),

        # Other

        'again':
            CommandGrammar('again')
            .add_desc('Run the previous command again'),

        'cleanse':
            CommandGrammar('cleanse')
            .add_desc('Send a long, blank message to hide a particularly '
                      'cursed message'),

        'quote':
            CommandGrammar('quote', mode='positional')
            .add_desc('Quote a previously sent message (or optionally a range '
                      'of messages from `url1` to `url2`)')
            .add_param('url1', DiscordMessageURLParam)
            .add_param('url2', DiscordMessageURLParam, optional=True),

        'portal':
            CommandGrammar('portal')
            .add_desc('Create a portal to another channel (i.e. if the chat '
                      'has gone off-topic)')
            .add_param('channel', ChannelsParam, alias='c'),

        'gdrive':
            CommandGrammar('gdrive', mode='positional')
            .add_desc('Get a direct link to a Google Drive file (so you can '
                      'play the file with a music bot, for example)')
            .add_param('url', StringParam, help='Google Drive file share link'),

        'vc': 'vibe check',
        'vibe': CommandGrammar('vibe').add_subcommands('check'),
        'vibe check':
            CommandGrammar('vibe check')
            .add_desc('how are u vibin?'),
        
        'gen': 'generate',
        'generate':
            CommandGrammar('generate')
            .add_desc('Generate a message based on what users have said before')
            .add_param('algorithm', ChoiceParam, alias='a',
                       help='`original`/`markov`/`1` is the original '
                            'Markov-chain-based algorithm, '
                            '`madlibs`/`2` is a new Mad-Libs-inspired '
                            'algorithm (uses part-of-speech tagging)',
                       _choices={'1', 'original', 'markov', '2', 'madlibs'},
                       _default='original')
            .add_param('users', UsersParam, alias='u')
            .add_param('channels', ChannelsParam, alias='c')
            .add_param('limit', LimitParam,
                       help='Limit the number of generated words')
            .add_param('count', CountParam, _min=1, _max=25)
            .add_param('blueprint', QuotedStringParam,
                       help='A quoted string to base all generations off of'),

        'rq': 'rquote',
        'rquote':
            CommandGrammar('rquote')
            .add_desc('Bring up a random quote from past messages on the '
                      'server')
            .add_subcommands('guess')
            .add_param('users', UsersParam, alias='u')
            .add_param('channels', ChannelsParam, alias='c')
            .add_param('limit', LimitParam,
                       help='Limit the number of words in the quote')
            .add_param('count', CountParam, _min=1, _max=5),

        'rquote guess':
            CommandGrammar('rquote guess')
            .add_desc('Same as rquote, but hides the authors\' names until '
                      'the question mark reaction is clicked. Play with your '
                      'friends and guess who wrote each message!')
            .add_param('channels', ChannelsParam, alias='c')
            .add_param('limit', LimitParam,
                       help='Limit the number of words in the quote')
            .add_param('count', CountParam, _min=1, _max=5),

        'ri': 'rimage',
        'rimage':
            CommandGrammar('rimage')
            .add_desc('Bring up a random image that\'s been shared on this '
                      'server before')
            .add_param('users', UsersParam, alias='u')
            .add_param('channels', ChannelsParam, alias='c')
            .add_param('count', CountParam, _min=1, _max=5),

        'ms': 'mstats',
        'mstats':
            CommandGrammar('mstats')
            .add_desc('Message statistics - see how many messages on this '
                      'server contain a given phrase')
            .add_subcommands('plot')
            .add_param('users', UsersParam, alias='u')
            .add_param('channels', ChannelsParam, alias='c')
            .add_param('flags', FlagsParam, _allowed_flags='ca',
                       help='Use letter `a` to find the pattern anywhere ('
                            'like inside another word) and letter `c` to '
                            'make search case-sensitive')
            .add_param('pattern', QuotedStringParam,
                       help='A quoted phrase or regex pattern to search for'),

        'mstats plot':
            CommandGrammar('mstats plot')
            .add_desc('Plot out instances of a phrase over time')
            .add_param('users', UsersParam, alias='u')
            .add_param('channels', ChannelsParam, alias='c')
            .add_param('flags', FlagsParam, _allowed_flags='ca',
                       help='Use letter `a` to find the pattern anywhere ('
                            'like inside another word) and letter `c` to '
                            'make search case-sensitive')
            .add_param('pattern', QuotedStringParam,
                       help='A quoted phrase or regex pattern to search for')
    }

    @classmethod
    def resolve_alias(cls, name):
        g = cls.grammar
        if name in g:
            if isinstance(g[name], str):
                # name is an alias
                return g[name]
            return name
        return None

    @classmethod
    def find_base(cls, base: str,
                  resolve_aliases: bool = False) -> Optional[CommandGrammar]:
        if not base:
            return None
        if resolve_aliases:
            path = base.split(' ')
            base = cls.resolve_alias(path[0])
            for fragment in path[1:]:
                base = cls.resolve_alias(f'{base} {fragment}')
        base = cls.resolve_alias(base)
        return cls.grammar[base] if base else None

    @classmethod
    def get_command_names(cls):
        return [k for k, v in cls.grammar.items()
                if not isinstance(v, str) and ' ' not in k]


if __name__ == '__main__':
    print(Grammar.find_base('rquote'))
    print(Grammar.find_base('rq'))
    print(Grammar.find_base('rq guess', resolve_aliases=True))
