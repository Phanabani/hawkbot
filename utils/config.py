import json

from utils.constants import DATA_FOLDER


class Config:

    def __init__(self, file):
        with open(file) as f:
            self._config = json.load(f)
            self.env = self._config['env']

    def __getitem__(self, item):
        if item not in self._config:
            return self._config['envs'][self.env][item]
        return self._config[item]


config = Config(DATA_FOLDER / 'config.json')
