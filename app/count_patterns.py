""" Utility functions for dealing with patterns. """
import re
from operator import itemgetter
from typing import List

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

def count_patterns(node, patterns_all):
    """ Accumulate patterns for each cluster into patterns_all. """
    for child in node.findall(".//*[@data-key]"):
        lat = child.get('data-key')
        key = ' '.join(child.itertext()).strip().lower()
        key = re.sub(' +', ' ', key)
        cluster = LAT_MAP.get(lat, {'cluster': '?'})['cluster']
        if cluster != 'Other':
            patterns_all[cluster].update([key])

def sort_patterns(patterns_all) -> List[CategoryPatternData]:
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
