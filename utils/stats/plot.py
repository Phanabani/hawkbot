from io import BytesIO

import matplotlib
import numpy as np

matplotlib.use('agg')

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
# import matplotlib.style as mplstyle
# mplstyle.use('dark_background')

from utils.misc import color_from_hash

# plt.rc('font', size=20, family='Calibri')

# https://stackoverflow.com/questions/14313510/how-to-calculate-moving-average-using-numpy


class CountPlotData:

    # data_dtype = np.dtype('M8[D], u4')
    data_dtype = np.dtype([('date', 'M8[D]'), ('count', 'u4')])

    def __init__(self):
        self.data = {}

    def init_id(self, id_: int, name: str):
        if id_ not in self.data:
            self.data[id_] = {'name': name, 'counts': []}

    def add(self, id_, name, date, count):
        self.init_id(id_, name)
        self.data[id_]['counts'].append((date, count))

    def get_counts(self):
        for data in self.data.values():
            yield (data['name'],
                   np.fromiter(data['counts'], dtype=self.data_dtype))


class GridShader:
    # https://stackoverflow.com/a/54654448

    def __init__(self, ax, first=True, **kwargs):
        self.spans = []
        self.sf = first
        self.ax = ax
        self.kw = kwargs
        self.ax.autoscale(False, axis="x")
        self.cid = self.ax.callbacks.connect('xlim_changed', self.shade)
        self.shade()

    def clear(self):
        for span in self.spans:
            # noinspection PyBroadException
            try:
                span.remove()
            except Exception:
                pass

    def shade(self):
        self.clear()
        xticks = self.ax.get_xticks()
        if len(xticks) == 0:
            return
        xlim = self.ax.get_xlim()
        xticks = xticks[(xticks > xlim[0]) & (xticks < xlim[-1])]
        locs = np.concatenate(([[xlim[0]], xticks, [xlim[-1]]]))

        start = locs[1-int(self.sf)::2]
        end = locs[2-int(self.sf)::2]

        for s, e in zip(start, end):
            self.spans.append(self.ax.axvspan(s, e, zorder=0, **self.kw))


def figure_to_image_stream(fig: plt.Figure):
    img = BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)
    return img


def plot_counts(data: CountPlotData, pattern: str):
    # Create fig
    fig, ax = plt.subplots(figsize=(16, 9), dpi=125)

    fig.autofmt_xdate()
    locator = mdates.MonthLocator()
    formatter = mdates.DateFormatter('%Y-%m')
    ax.xaxis.set_major_locator(locator)
    ax.xaxis.set_major_formatter(formatter)
    ax.grid()

    for name, counts in data.get_counts():
        # Run for every user
        counts['count'] = np.cumsum(counts['count'])
        ax.plot(counts['date'], counts['count'],
                label=name, linewidth=3,
                marker='o' if len(counts['date']) else '',
                color=color_from_hash(name))

    ax.set_title(f'Stats for {pattern}', fontsize=20)
    ax.set_xlabel('Month', fontsize=20)
    plt.setp(ax.get_xticklabels(), fontsize=12)
    ax.set_ylabel('Messages', fontsize=20)
    plt.setp(ax.get_yticklabels(), fontsize=16)
    fig.set_tight_layout(True)

    ax.legend(loc='best', fontsize='x-large')
    GridShader(ax, facecolor="lightgrey", alpha=0.5)

    image = figure_to_image_stream(fig)
    plt.close(fig)
    return image
