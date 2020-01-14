from pathlib import Path
import random

from utils.constants import DATA_FOLDER

with Path(DATA_FOLDER, 'text', 'adjectives_large.txt').open() as f:
    adjectives = f.read().split('\n')
    adjectives += ['power move', '***continental***',
                   '<:i_slowly_open_the_door:628094920279982081>']*10


def vibe_check():
    adj = random.choice(adjectives)
    return f'vibe: {adj}'
