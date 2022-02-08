""" The DocuScope Tagger using a neo4j based dictionary. """
# coding=utf-8
__author__ = 'mringenb'

from collections import OrderedDict
from typing import Optional

import neo4j
from neo4j import Transaction

from .docuscope_tagger_base import (DocuscopeTaggerBase, LatRule,
                                    rule_applies_for_tokens)


class DocuscopeTaggerNeo(DocuscopeTaggerBase):
    """
    This DocuScope tagger connects to a neo4j database which stores all of the
    LAT rules and patterns.
    """

    def __init__(
            self, *args,
            wordclasses: Optional[dict[str, list[str]]] = None,
            session: Optional[neo4j.Session] = None,
            **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.wordclasses = wordclasses or {}
        self._label = (self._label if self._label else "") + ".default"

    #async def get_long_rule(self) -> Optional[LatRule]:
    def get_long_rule(self) -> Optional[LatRule]:
        lookup = [list(t) for t in self.get_next_ds_words_in_range(0, 4)]
        #rules = await self.session.read_transaction(
        rules = self.session.read_transaction(
            get_lat_rules, lookup)
        tokens = self.get_next_ds_words_in_range(0, len(rules[0]['path'])) if len(rules) > 0 else []
        ds_rule = next((r for r in rules \
            if rule_applies_for_tokens(r['path'], tokens, offset=2)), None)
        return ds_rule

    #async def get_short_rule(self, token_ds_words: list[str]):
    #    return await self.session.read_transaction(get_short_rules, token_ds_words)
    def get_short_rule(self, token_ds_words: list[str]):
        return self.session.read_transaction(get_short_rules, token_ds_words)

SEPARATOR = f"{hash('+++MichaelRingenbergSeparator+++')}"
#async def get_lat_rules(
def get_lat_rules(
        trx: Transaction,
        tokens: list[tuple[str]]) -> list[LatRule]:
    """ Retrieve the LAT rules starting with the given bi-/tri-gram. """
    hsh = SEPARATOR.join(['+++'.join(token) for token in tokens])
    res = CACHE.get(hsh)
    if res is None:
        if len(tokens) >= 4:
            #result = await trx.run(
            result = trx.run(
                "MATCH p = (w1:Start)-[w2:NEXT]->()-[w3:NEXT]->()-[w4:NEXT]->()-[:NEXT*0..25]->()"
                "-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second AND w3.word IN $third "
                "AND w4.word IN $fourth "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat ORDER BY length(p) DESC "
                "UNION MATCH p = (w1:Start)-[w2:NEXT]->()-[w3:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second AND w3.word IN $third "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat "
                "UNION MATCH p = (w1:Start)-[w2:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat",
                first=tokens[0], second=tokens[1], third=tokens[2], fourth=tokens[3])
        elif len(tokens) == 3:
            #result = await trx.run(
            result = trx.run(
                "MATCH p = (w1:Start)-[w2:NEXT]->()-[w3:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second AND w3.word IN $third "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat "
                "UNION MATCH p = (w1:Start)-[w2:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat",
                first=tokens[0], second=tokens[1], third=tokens[2])
        else: # bigram fallthrough
            #result = await trx.run(
            result = trx.run(
                "MATCH p = (w1:Start)-[w2:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat",
                first=tokens[0], second=tokens[1])
        # duck type NEXT as type is not in record properties.
        res = [{"lat": record["lat"],
                "path": [record["start"],
                         *[path["word"] for path in record["path"]
                           if "word" in path]]}
               for record in result]
               #async for record in result]
        CACHE.put(hsh, res)
    return res

SHORT_CACHE = {}
#async def get_short_rules(trx: Transaction,
def get_short_rules(trx: Transaction,
                    first_tokens: list[str]) -> tuple[str, str]:
    """ Retrieve the unigram LAT rule for the given token. """
    hsh = tuple(first_tokens)
    if hsh not in SHORT_CACHE:
        #trans = await trx.run(
        trans = trx.run(
            "MATCH (s:Start)-[:LAT]->(l:Lat) WHERE s.word IN $first "
            "RETURN s.word AS token, l.lat AS lat "
            "ORDER BY token DESC, lat DESC LIMIT 1",
            first=first_tokens)
        #result = await trans.single()
        result = trans.single()
        SHORT_CACHE[hsh] = result
    res = SHORT_CACHE.get(hsh, None)
    if res:
        return res["lat"], res["token"]
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

CACHE = LRUCache(2**22)
