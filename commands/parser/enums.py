from enum import Enum


class ParsingMode(Enum):
    """
    LEXICAL: Parse lexically (keywords)
    POSITIONAL: Parse positionally
    REST: Parse without tokenization
    """
    LEXICAL = 'lexical'
    POSITIONAL = 'positional'
    REST = 'rest'