from dataclasses import dataclass


@dataclass
class User:
    id: int = None
    name: str = None
    discriminator: int = None


@dataclass
class Channel:
    id: int = None
    name: str = None
