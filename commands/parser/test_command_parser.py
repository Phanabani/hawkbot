import pytest

from commands.parser import Parser


class TestParser:

    parser = Parser()

    def test_basic(self):
        parser = self.parser

        cmd = parser('')
        assert cmd is None

        cmd = parser('this isn\'t a command')
        assert cmd is None

    def test_gen(self):
        parser = self.parser

        cmd = parser('gen')
        assert cmd.base.name == 'generate'
        assert cmd.base.path == ['generate']
        assert cmd.users.names == []
        assert cmd.channels.names == []
        assert cmd.limit.min is None
        assert cmd.limit.max is None
        assert cmd.count.count == 1
        assert cmd.seed.quote_type is None
        assert cmd.seed.is_regex is False
        assert cmd.seed.value is None

        cmd = parser('gen users[hawk chance lob] channels[deities] limit[5 10] count[4] seed["initial text"]')
        assert cmd.users.names == ['hawk', 'chance', 'lob']
        assert cmd.channels.names == ['deities']
        assert cmd.limit.min == 5
        assert cmd.limit.max == 10
        assert cmd.count.count == 4
        assert cmd.seed.quote_type == '"'
        assert cmd.seed.value == 'initial text'

        cmd = parser('gen u[hawk chance lob] c[deities] 5->10 x50 "initial text"')
        assert cmd.users.names == ['hawk', 'chance', 'lob']
        assert cmd.channels.names == ['deities']
        assert cmd.limit.min == 5
        assert cmd.limit.max == 10
        assert cmd.count.count == 25
        assert cmd.seed.quote_type == '"'
        assert cmd.seed.value == 'initial text'

        cmd = parser('gen \'this is my seed\' limit[5 10] x9')
        assert cmd.seed.quote_type == "'"
        assert cmd.seed.value == 'this is my seed'
        assert cmd.limit.min == 5
        assert cmd.limit.max == 10
        assert cmd.count.count == 9

        cmd = parser('gen x5 3->3')
        assert cmd.count.count == 5
        assert cmd.limit.min == 3
        assert cmd.limit.max == 3

        cmd = parser('gen 3->3 x5')
        assert cmd.count.count == 5
        assert cmd.limit.min == 3
        assert cmd.limit.max == 3

        cmd = parser('gen count[-5]')
        assert cmd.count.count == 1

    def test_rquote(self):
        parser = self.parser

        cmd = parser('rq u[hawk chance lob] ->10 x99')
        assert cmd.base.name == 'rquote'
        assert cmd.base.path == ['rquote']
        assert cmd.users.names == ['hawk', 'chance', 'lob']
        assert cmd.limit.min is None
        assert cmd.limit.max == 10
        assert cmd.count.count == 5

        cmd = parser('rq u[lob] x5')
        assert cmd.users.names == ['lob']
        assert cmd.count.count == 5

        cmd = parser('rq c[deities]')
        assert cmd.channels.names == ['deities']

        cmd = parser('rq c[deities] u[hawk]')
        assert cmd.channels.names == ['deities']
        assert cmd.users.names == ['hawk']

        cmd = parser('rq u[hawk] channels[deities]')
        assert cmd.channels.names == ['deities']
        assert cmd.users.names == ['hawk']

        cmd = parser('rq u[hawk] x4')
        assert cmd.users.names == ['hawk']
        assert cmd.count.count == 4

        cmd = parser('rq u[hawk] 2->4')
        assert cmd.users.names == ['hawk']
        assert cmd.limit.min == 2
        assert cmd.limit.max == 4

        cmd = parser('rq u[hawk] "seed text"')
        assert cmd is None

        cmd = parser('rq guess 5->10 x3')
        assert cmd.base.name == 'rquote guess'
        assert cmd.base.path == ['rquote', 'guess']
        assert cmd.limit.min == 5
        assert cmd.limit.max == 10
        assert cmd.count.count == 3

        cmd = parser('rq guess u[hawk] 5->10 x3')
        assert cmd is None

    def test_rimage(self):
        parser = self.parser

        cmd = parser('ri x3')
        assert cmd.base.name == 'rimage'
        assert cmd.count.count == 3

    def test_mstats(self):
        parser = self.parser

        cmd = parser('ms')
        assert cmd.base.name == 'mstats'
        assert cmd.base.path == ['mstats']
        assert cmd.users.names == []
        assert cmd.channels.names == []
        assert cmd.flags.flags == set()
        assert cmd.pattern.quote_type is None
        assert cmd.pattern.is_regex is False
        assert cmd.pattern.value is None

        cmd = parser('ms -cf c[convo images] "/regex (?P<pattern>.+)/"')
        assert cmd.flags.flags == {'c', 'f'}
        assert cmd.channels.names == ['convo', 'images']
        assert cmd.pattern.is_regex is True
        assert cmd.pattern.value == 'regex (?P<pattern>.+)'

        cmd = parser('ms plot flags[f] channels[convo images] pattern["my phrase here"]')
        assert cmd.base.name == 'mstats plot'
        assert cmd.base.path == ['mstats', 'plot']
        assert cmd.flags.flags == {'f'}
        assert cmd.channels.names == ['convo', 'images']
        assert cmd.pattern.quote_type == '"'
        assert cmd.pattern.is_regex is False
        assert cmd.pattern.value == 'my phrase here'

        cmd = parser('ms plot "hello"')
        assert cmd.base.name == 'mstats plot'
        assert cmd.base.path == ['mstats', 'plot']
        assert cmd.pattern.quote_type == '"'
        assert cmd.pattern.is_regex is False
        assert cmd.pattern.value == 'hello'

    def test_positional(self):
        p = self.parser

        cmd = p('config prefix set "test"')
        assert cmd.base.root == 'config'
        assert cmd.base.name == 'config prefix set'
        assert cmd.prefix.value == 'test'

        cmd = p('gdrive https://drive.google.com/this_is_my_url')
        assert cmd.base.name == 'gdrive'
        assert cmd.url.value == 'https://drive.google.com/this_is_my_url'

        cmd = p('quote '
                'https://discordapp.com/channels/'
                '288545683462553610/377548983477731328/640338828288327691 '
                'https://discordapp.com/channels/'
                '288545683462553610/377548983477731328/640338923175804929')
        assert cmd.base.name == 'quote'
        assert cmd.url1.guild_id == 288545683462553610
        assert cmd.url1.channel_id == 377548983477731328
        assert cmd.url1.message_id == 640338828288327691
        assert cmd.url2.guild_id == 288545683462553610
        assert cmd.url2.channel_id == 377548983477731328
        assert cmd.url2.message_id == 640338923175804929

    def test_rest(self):
        parser = self.parser

        cmd = parser('help command')
        assert cmd.base.name == 'help'
        assert cmd.command.value == 'command'

        cmd = parser('help command with subcommands')
        assert cmd.base.name == 'help'
        assert cmd.command.value == 'command with subcommands'

    def test_config(self):
        p = self.parser

        cmd = p('config')
        assert cmd.base.name == 'config'

        cmd = p('config pins_channel set')
        assert cmd.base.root == 'config'
        assert cmd.base.path == ['config', 'pins_channel']
        assert cmd.action.value == 'set'


if __name__ == '__main__':
    pytest.main()
