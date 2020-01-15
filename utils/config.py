import json

from utils.constants import DATA_FOLDER


class Config:

    def __init__(self, file):
        with open(file) as f:
            self._config = json.load(f)
        self.env_name = self._config['env']
        self._env = self._config['envs'][self.env_name]

    def __getitem__(self, item):
        if item in self._env:
            return self._env[item]
        return self._config[item]

    def __contains__(self, item):
        return item in self._env or item in self._config


config = Config(DATA_FOLDER / 'config.json')
