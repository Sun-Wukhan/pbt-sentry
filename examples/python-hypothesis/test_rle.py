"""Hypothesis property tests for the run-length encoder.

Run under pbt-sentry with the seed pinned per run:

    pbt-sentry --runs 50 --command \
      "python -m pytest test_rle.py -q -p no:cacheprovider --hypothesis-seed={seed}"

``--hypothesis-seed`` makes each run deterministic, and the database is
disabled below so no examples leak between runs: the seed alone decides
what a run generates, which is what makes pbt-sentry's reproduction
commands exact.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from hypothesis import given, settings, strategies as st

from rle import decode, encode

# A small alphabet makes long identical runs likely, which is exactly
# where the planted bug lives.
VALUES = st.lists(st.integers(min_value=0, max_value=1), min_size=0, max_size=40)

PROPERTY = settings(max_examples=25, database=None)


@PROPERTY
@given(VALUES)
def test_round_trip(values):
    assert decode(encode(values)) == values


@PROPERTY
@given(VALUES)
def test_encoded_counts_account_for_every_item(values):
    assert sum(count for count, _ in encode(values)) == len(values)
