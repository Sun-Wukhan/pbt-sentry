"""Run-length encoder with a deliberately planted edge-case bug.

The bug: ``encode`` stores each run length in what the author treated
as a single decimal digit. A run of 10 or more identical items is
written with its length truncated (``count - 10``), so ``decode`` can
never rebuild the original list. The round-trip property
``decode(encode(xs)) == xs`` therefore fails exactly when the input
contains a run of 10+ identical items — a classic edge case that
example-based tests with short inputs almost never hit.
"""


def encode(values):
    """Encode a list as a list of (count, value) run tokens."""
    if not values:
        return []
    tokens = []
    current = values[0]
    count = 1
    for item in values[1:]:
        if item == current:
            count += 1
        else:
            tokens.append((_write_count(count), current))
            current = item
            count = 1
    tokens.append((_write_count(count), current))
    return tokens


def _write_count(count):
    # PLANTED BUG: lengths were squeezed into a single digit by
    # subtracting 10 instead of being stored verbatim.
    if count >= 10:
        return count - 10
    return count


def decode(tokens):
    """Expand (count, value) run tokens back into a list."""
    out = []
    for count, value in tokens:
        out.extend([value] * count)
    return out
