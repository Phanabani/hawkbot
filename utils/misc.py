from collections import deque
from colormath.color_objects import LCHabColor, sRGBColor
from colormath.color_conversions import convert_color
from pathlib import Path
import pkgutil
from queue import Queue
import mmh3
import random
import re
import sys
from types import ModuleType, FunctionType
from typing import Optional, List, Sized, Iterator, Dict, Iterable, Union, Any

data_folder_path = Path(__file__, '../../data').resolve()


class SizedDict(dict):

    def __init__(self, *args, size=10, **kwargs):
        super(SizedDict, self).__init__(*args, **kwargs)
        self._key_queue = Queue(size)

    def __setitem__(self, key, value):
        if self._key_queue.full():
            remove_key = self._key_queue.get()
            del self[remove_key]
        self._key_queue.put(key)
        super(SizedDict, self).__setitem__(key, value)


def color_from_hash(key):
    key = str(key)
    l = (mmh3.hash(key + key[::-1]) + 2147483648) / 4294967296
    c = (mmh3.hash(key[::-1] + key) + 2147483648) / 4294967296
    h = (mmh3.hash(key) + 2147483648) / 4294967296
    l = (l*0.6 + 0.3) * 100
    c = (c*0.75 + 0.25) * 100
    h = h * 360

    lch = LCHabColor(l, c, h)
    rgb: sRGBColor = convert_color(lch, sRGBColor)
    return rgb.clamped_rgb_r, rgb.clamped_rgb_g, rgb.clamped_rgb_b


# noinspection PyShadowingBuiltins
def find_submodules(globals: Dict[str, Any], path: str):
    submodules = {m.name for m in pkgutil.walk_packages(path=[path])}
    alias_cache = set()
    for name, value in globals.copy().items():
        if isinstance(value, ModuleType) and value.__name__ in submodules:
            yield value
        elif isinstance(value, FunctionType) \
                and value.__module__ in submodules \
                and value.__module__ not in alias_cache:
            alias_cache.add(value.__module__)
            yield sys.modules[value.__module__]


def gdrive_direct_link(url: str) -> Optional[str]:
    match = re.match(
        r'https://drive\.google\.com/(?:file/d/|open\?id=)([^/]+).*', url)
    if match:
        return ('https://drive.google.com/uc?export=download&id='
                + match.group(1))
    return None


def merge_names(names: List[str]):
    if len(names) == 1:
        return names[0]
    out = ''
    for i in range(min(len(names), 5)):
        n = random.choice(names)
        names.remove(n)

        if len(n) > 3:
            rand_length = random.randrange(len(n) // 3,
                                           2 * len(n) // 3)
            if i == 0:
                offset = 0
            elif i == len(names) - 1:
                offset = len(n) - rand_length
            else:
                offset = random.randrange(1, len(n) - 1 - rand_length)
            out += n[offset:offset + rand_length]
        else:
            out += n
    return out


def normalize_text(text):
    return text.replace('“', '"').replace('”', '"')


def random_by_filesize(files: List[Path]) -> Path:
    if not all([f.is_file() for f in files]):
        raise ValueError('One or more paths is not a file')
    file_sizes = [f.stat().st_size for f in files]  # Sizes in bytes
    return random.choices(files, weights=file_sizes)[0]


def random_color():
    return random.randint(0, 0xFFFFFF)


def random_offset_iter(it: Union[Iterable, Sized]) -> Iterator:
    d = deque(it)
    d.rotate(random.randint(0, len(it)-1))
    return d
