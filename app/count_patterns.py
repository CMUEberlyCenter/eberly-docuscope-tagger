""" Utility functions for dealing with patterns. """
import re
from operator import itemgetter
from typing import Counter, DefaultDict, List
from bs4 import BeautifulSoup

from pydantic import BaseModel

from .lat_frame import LAT_MAP


class PatternData(BaseModel): #pylint: disable=too-few-public-methods
    """Schema for pattern data."""
    pattern: str = ...
    count: int = 0

class CategoryPatternData(BaseModel): #pylint: disable=too-few-public-methods
    """Schema for pattern data for each category."""
    category: str = ...
    patterns: List[PatternData] = []

def count_patterns(node: BeautifulSoup, patterns_all: DefaultDict[str, Counter]):
    """ Accumulate patterns for each cluster into patterns_all. """
    for child in node.find_all(attrs={"data-key": True}):
        lat = child.get("data-key", None)
        key = ' '.join(child.stripped_strings).lower()
        key = re.sub(' +', ' ', key)
        cluster = LAT_MAP.get(lat, {'cluster': '?'})['cluster']
        if cluster != 'Other':
            patterns_all[cluster].update([key])

def sort_patterns(patterns_all: DefaultDict[str, Counter]) -> List[CategoryPatternData]:
    """ Sort the patterns by count and secondarily alphabetically. """
    return [
        {'category': cat,
         'patterns': sorted(
             sorted([{'pattern': word, 'count': count}
                     for (word, count) in cpats.items()],
                    key=itemgetter('pattern')),
             key=itemgetter('count'), reverse=True)}
        for (cat, cpats) in sorted(
            sorted(patterns_all.items(), key=itemgetter(0)),
            key=lambda pat: -sum(c for (_, c) in pat[1].items()),
            reverse=False)
    ]
