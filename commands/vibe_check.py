from datetime import datetime
from pathlib import Path
import random

from utils.constants import DATA_FOLDER

with Path(DATA_FOLDER, 'text', 'adjectives_large.txt').open() as f:
    adjectives = f.read().split('\n')
    adjectives += ['power move', '***continental***',
                   '<:i_slowly_open_the_door:628094920279982081>']*10

with Path(DATA_FOLDER, 'text', 'nouns.txt').open() as f:
    nouns = [n.split(' ')[0] for n in f.read().split('\n')]


def vibe_check():
    adj = random.choice(adjectives)
    return f'vibe: {adj}'


def hawktober():
    noun = random.choice(nouns)
    adj = random.choice(adjectives)
    now = datetime.now()
    return f'**{now:%B %d, %Y}:** *{adj} {noun}*'
