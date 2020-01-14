from typing import Iterable, Tuple, Optional

LimitTuple = Tuple[Optional[int], Optional[int]]


def flat_pruned_list(*args):
    out = []
    for i in args:
        if i is not None:
            if isinstance(i, Iterable) and not isinstance(i, str):
                for j in i:
                    out.append(j)
            else:
                out.append(i)
    return out
