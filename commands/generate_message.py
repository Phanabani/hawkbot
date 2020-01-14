from collections import defaultdict
import random
from typing import Optional, List, Set, Dict

import spacy

from utils.database.markov import get_potentials
from utils.database.messages import random_message
from utils.database.misc import LimitTuple
from utils.database.pos_tagging import get_random_words_by_tag
from utils.errors import UserFeedbackError

nlp = spacy.load('en_core_web_sm')
CHAR_LIMIT = 2048
TAGS_MAP: Dict[str, Set[str]] = {
    'ADJ': {
        'AFX',  # affix
        'JJ',  # adjective
        'JJR',  # adjective, comparative
        'JJS',  # adjective, superlative
        'IN',  # conjunction, subordinating or preposition
        'RP',  # adverb, particle
        'RB',  # adverb
        'RBR',  # adverb, comparative
        'RBS',  # adverb, superlative
        'WRB'  # wh-adverb
    },
    'CCONJ': {
        'CC'  # conjunction, coordinating
    },
    'DET': {
        'DT',  # determiner
        'PDT',  # predeterminer
        'PRP$',  # pronoun, possessive
        'WDT',  # wh-determiner
        'WP$'  # wh-pronoun, possessive
    },
    'INTJ': {
        'UH',  # interjection
    },
    'NOUN': {
        'NN',  # noun, singular or mass
        'NNS'  # noun, plural
    },
    'NUM': {
        'CD'  # cardinal number
    },
    'PART': {
        'POS',  # possessive ending
        'TO',  # infinitival “to”
    },
    'PRON': {
        'EX',  # existential there
        'PRP',  # pronoun, personal
        'WP'  # wh-pronoun, personal
    },
    'PROPN': {
        'NNP',  # noun, proper singular
        'NNPS'  # noun, proper plural
    },
    'PUNCT': {
        ',',  # punctuation mark, comma
        '-LRB-',  # left round bracket
        '-RRB-',  # right round bracket
        '.',  # punctuation mark, sentence closer
        ':',  # punctuation mark, colon or ellipsis
        '\'\'',  # closing quotation mark
        '``',  # opening quotation mark
        'HYPH',  # punctuation mark, hyphen
        'NFP'  # superfluous punctuation
    },
    'SPACE': {
        '_SP',  # no description
        'SP'  # space
    },
    'SYM': {
        '$',  # symbol, currency
        'SYM'  # symbol
    },
    'VERB': {
        'MD',  # verb, modal auxiliary
        'VB',  # verb, base form
        'VBD',  # verb, past tense
        'VBG',  # verb, gerund or present participle
        'VBN',  # verb, past participle
        'VBP',  # verb, non-3rd person singular present
        'VBZ'  # verb, 3rd person singular present
    },
    'X': {
        'ADD',  # email
        'FW',  # foreign word
        'GW',  # additional word in multi-word expression
        'LS',  # list item marker
        'NIL',  # missing tag
        'XX'  # unknown
    }
}
pos_to_replace = ['ADJ', 'INTJ', 'NOUN', 'NUM', 'PRON', 'PROPN', 'VERB', 'X']
REPLACEABLE_TAGS: Set[str] = (
    {tag for pos in pos_to_replace for tag in TAGS_MAP[pos]}
)


def generate_message(guild_id: int, users: Optional[List[int]] = None,
                     channel: Optional[int] = None,
                     word_limit: Optional[LimitTuple] = None,
                     blueprint: Optional[str] = None) -> str:
    if blueprint:
        out = blueprint.split()
        # if the user gave multiple words, start with the last one
        base = out[-1]
    else:
        out = []
        base = ''

    if not word_limit:
        word_limit: LimitTuple = (None, None)
    elif word_limit[0] and word_limit[1] and word_limit[0] > word_limit[1]:
        raise UserFeedbackError(f'The minimum word count ({word_limit[0]}) is '
                                f'greater than the maximum ({word_limit[1]}).')
    elif blueprint:
        word_limit = (word_limit[0]+len(out) if word_limit[0] else None,
                      word_limit[1]+len(out) if word_limit[1] else None)

    char_count = 0
    while True:
        # Collect words for the sentence
        potentials = get_potentials(guild_id, base, users=users,
                                    channel=channel)
        if not potentials:
            raise UserFeedbackError(f'Seed "{base}" could not be found '
                                    f'for these users in this channel.')
        if word_limit[1] and len(out) >= word_limit[1] and '' in potentials:
            # We're surpassing the word limit and EOF is in potentials; wrap up
            break

        base = random.choice(potentials)
        if base == '':
            # Reached EOF
            if word_limit[0] and len(out) < word_limit[0]\
                    and len(potentials) > 1:
                # We haven't met the minimum word count but there are other
                # words in potentials. Remove EOF and pick a new random base
                potentials.remove('')
                base = random.choice(potentials)
            else:
                # Wrap up
                break

        char_count += len(base)
        if char_count >= CHAR_LIMIT:
            break
        out.append(base)

    return ' '.join(out)


def generate_message2(guild_id: int, users: Optional[List[int]] = None,
                      channel: Optional[int] = None,
                      word_limit: Optional[LimitTuple] = None,
                      blueprint: Optional[str] = None) -> Optional[str]:
    if not blueprint:
        random_msg = random_message(guild_id, users, channel,
                                    word_limit=word_limit, count=1,
                                    content=True).fetchone()
        if random_message:
            blueprint = random_msg.content
        else:
            return None

    doc = nlp(blueprint)
    counts = defaultdict(lambda: 0)
    for token in doc:
        tag = token.tag_
        if tag in REPLACEABLE_TAGS:
            counts[token.tag_] += 1
    new_words = {}
    for tag, count in counts.items():
        new_words[tag] = get_random_words_by_tag(guild_id, tag, users, channel,
                                                 count)

    new_sentence = []
    for token in doc:
        tag = token.tag_
        if tag in REPLACEABLE_TAGS:
            new_sentence.append(new_words[tag].pop())
        else:
            new_sentence.append(token.text)
        new_sentence.append(token.whitespace_)

    return ''.join(new_sentence)


if __name__ == '__main__':
    blueprint = 'My bot, Hawkbot, is very cool'
    print(generate_message2(288545683462553610, blueprint=None))
