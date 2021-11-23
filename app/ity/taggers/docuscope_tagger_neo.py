""" The DocuScope Tagger using a neo4j based dictionary. """
# coding=utf-8
__author__ = 'mringenb'

from collections import OrderedDict
from typing import Optional
from neo4j import Transaction
import neo4j
from .docuscope_tagger_base import DocuscopeTaggerBase, LatRule

class DocuscopeTaggerNeo(DocuscopeTaggerBase):
    """
    This DocuScope tagger connects to a neo4j database which stores all of the
    LAT rules and patterns.
    """

    def __init__(
            self, *args,
            wordclasses: Optional[dict[str, list[str]]]=None,
            session: Optional[neo4j.Session]=None,
            **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.wordclasses = wordclasses or {}
        self._label = (self._label if self._label else "") + ".default"

    def get_long_rule(self) -> Optional[LatRule]:
        first_tokens = self._get_ds_words_for_token_index(self.token_index)
        second_token_index = self._get_nth_next_included_token_index()
        second_tokens = self._get_ds_words_for_token_index(second_token_index) \
            if second_token_index else [] # should not happen, but just in case
        third_token_index = self._get_nth_next_included_token_index(
            starting_token_index=second_token_index)
        third_tokens = self._get_ds_words_for_token_index(third_token_index) \
            if third_token_index else []
        fourth_token_index = self._get_nth_next_included_token_index(
            starting_token_index=third_token_index)
        fourth_tokens = self._get_ds_words_for_token_index(fourth_token_index) \
            if fourth_token_index else []
        rules = self.session.read_transaction(
            get_lat_rules, first_tokens, second_tokens, third_tokens, fourth_tokens)
        #rules.sort(reverse=True, key=lambda p: len(p["path"]))
        ds_rule = next((r for r in rules \
            if self._long_rule_applies_at_token_index(r['path'])), None)
        return ds_rule

    def get_short_rule(self, token_ds_words):
        return self.session.read_transaction(get_short_rules, token_ds_words)

SEPARATOR = f"{hash('+++MichaelRingenbergSeparator+++')}"
def get_lat_rules(
        trx: Transaction,
        first_tokens: tuple[str],
        second_tokens: tuple[str],
        third_tokens: tuple[str], fourth_tokens: tuple[str]) -> list[LatRule]:
    """ Retrieve the LAT rules starting with the given bi-/tri-gram. """
    hsh = ",".join([*first_tokens, SEPARATOR, *second_tokens,
                    SEPARATOR, *third_tokens, SEPARATOR, *fourth_tokens])
    res = CACHE.get(hsh)
    if res is None:
        if len(fourth_tokens) > 0:
            result = trx.run(
                "MATCH p = (w1:Start)-[w2:NEXT]->()-[w3:NEXT]->()-[w4:NEXT]->()-[*1..25]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second AND w3.word IN $third "
                "AND w4.word IN $fourth "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat " # ORDER BY length(p) DESC "
                "UNION MATCH p = (s:Start)-[n:NEXT]->()-[m:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE s.word IN $first AND n.word IN $second AND m.word IN $third "
                "RETURN s.word AS start, relationships(p) as path, "
                "l.lat as lat " # ORDER BY length(p) DESC "
                "UNION MATCH p = (s:Start)-[n:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE s.word IN $first AND n.word IN $second "
                "RETURN s.word AS start, relationships(p) as path, "
                "l.lat as lat ",# "ORDER BY length(p) DESC",
                first=first_tokens, second=second_tokens, third=third_tokens, fourth=fourth_tokens)
        elif len(third_tokens) > 0:
            result = trx.run(
                "MATCH p = (s:Start)-[n:NEXT]->()-[m:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE s.word IN $first AND n.word IN $second AND m.word IN $third "
                "RETURN s.word AS start, relationships(p) as path, "
                "l.lat as lat " # ORDER BY length(p) DESC "
                "UNION MATCH p = (s:Start)-[n:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE s.word IN $first AND n.word IN $second "
                "RETURN s.word AS start, relationships(p) as path, "
                "l.lat as lat ",# "ORDER BY length(p) DESC",
                first=first_tokens, second=second_tokens, third=third_tokens)
        else:
            result = trx.run(
                "MATCH p = (s:Start)-[n:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE s.word IN $first AND n.word IN $second "
                "RETURN s.word AS start, relationships(p) as path, "
                "l.lat as lat ", # ORDER BY length(p) DESC "
                first=first_tokens, second=second_tokens)
        # duck type NEXT as type is not in record properties.
        res = [{"lat": record["lat"],
                "path": [record["start"],
                         *[path["word"] for path in record["path"]
                           if "word" in path]]}
               for record in result]
        res.sort(reverse=True, key=lambda p: len(p["path"])) # python faster on sort
        CACHE.put(hsh, res)
    return res

def get_short_rules(trx: Transaction,
                    first_tokens: list[str]) -> tuple[str, str]:
    """ Retrieve the unigram LAT rule for the given token. """
    hsh = ",".join(first_tokens)
    res = CACHE.get(hsh)
    if res is None:
        result = trx.run(
            "MATCH (s:Start)-[:LAT]->(l:Lat) WHERE s.word IN $first "
            "RETURN s.word AS token, l.lat AS lat "
            "ORDER BY token DESC, lat DESC LIMIT 1",
            first=first_tokens)
        res = [{"lat": record["lat"],
                "path": [record["token"]]} for record in result]
        CACHE.put(hsh, res)
    if len(res) > 0:
        record = res[0]
        return record["lat"], record["path"][0]
    return None, None

class LRUCache:
    """ A simple least recently used cache for memoization. """
    def __init__(self, capacity: int):
        self.cache = OrderedDict()
        self.capacity = capacity
    def get(self, key: str) -> Optional[list[LatRule]]:
        """ Retrieve the value for the key or None. """
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]
    def put(self, key: str, value: list[LatRule]) -> None:
        """ Add the given data for the given key to the cache. """
        self.cache[key] = value
        self.cache.move_to_end(key)
        if len(self.cache) > self.capacity:
            self.cache.popitem(last = False)

CACHE = LRUCache(2**12)
