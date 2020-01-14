from dataclasses import dataclass
from io import BytesIO
from typing import Optional, List, Union

from .utils.data_classes import User
from utils.database.messages import message_stats as message_stats_db
from utils.stats.plot import CountPlotData, plot_counts


@dataclass
class MessageStatsEntry:
    user: User
    count: int


class MessageStats:

    def __init__(self):
        self.entries = []

    def __str__(self):
        self.entries = list(sorted(self.entries, key=lambda x: x.user.name))
        self.entries = list(sorted(self.entries, key=lambda x: x.count,
                                   reverse=True))
        return '\n'.join(f'{e.user.name}: **{e.count}**' for e in self.entries)

    def add(self, name: str, count: int):
        user = User(name=name)
        entry = MessageStatsEntry(user, count)
        self.entries.append(entry)


def message_stats(guild_id: int,
                  pattern: str,
                  users: Optional[List[int]] = None,
                  channels: Optional[List[int]] = None,
                  case_sensitive: bool = False,
                  plot: bool = False) -> Union[MessageStats, BytesIO]:
    cur = message_stats_db(guild_id, pattern, users, channels,
                           case_sensitive=case_sensitive,
                           plot=plot)
    if not plot:
        stats = MessageStats()
        for name, count in cur:
            stats.add(name, count)
        return stats
    else:
        data = CountPlotData()
        for id_, name, date, count in cur:
            data.add(id_, name, date, count)
        return plot_counts(data, pattern)
