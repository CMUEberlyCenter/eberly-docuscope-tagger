""" The DocuScope Tagger using a neo4j based dictionary. """
# coding=utf-8
__author__ = 'mringenb'

from collections import OrderedDict
import hashlib
import json
from typing import Optional
import emcache

import neo4j
from neo4j import AsyncTransaction

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
            session: Optional[neo4j.AsyncSession] = None,
            cache: Optional[emcache.Client] = None,
            **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session
        self.wordclasses = wordclasses or {}
        self._label = (self._label if self._label else "") + ".default"
        self.emcache = cache

    async def get_long_rule(self) -> Optional[LatRule]:
        lookup = [sorted(list(t)) for t in self.get_next_ds_words_in_range(0, 4)]
        rules: Optional[list[LatRule]] = None
        if self.emcache:
            hsh = hashlib.sha256(str(lookup).encode('utf-8')).hexdigest().encode('utf-8') #f"${hash((tuple(l) for l in lookup))}".encode('utf-8')
            hit = await self.emcache.get(hsh)
            if hit is not None:
                rules = json.loads(hit.value)
        if rules is None:
            rules = await self.session.read_transaction(
            # rules = self.session.read_transaction(
                get_lat_rules, lookup)
        if rules and self.emcache:
            jrules = json.dumps(rules)
            await self.emcache.set(hsh, jrules.encode('utf-8'), noreply=True)
        tokens = self.get_next_ds_words_in_range(
            0, len(rules[0]['path'])) if len(rules) > 0 else []
        ds_rule = next((r for r in rules
                        if rule_applies_for_tokens(r['path'], tokens, offset=2)), None)
        return ds_rule

    async def get_short_rule(self, token_ds_words: list[str]):
        if len(token_ds_words) == 0:
            return None, None
        if self.emcache:
            hsh =  hashlib.sha256(str(sorted(token_ds_words)).encode('utf-8')).hexdigest().encode('utf-8')
            hit = await self.emcache.get(hsh)
            if hit is not None:
                [lat, token] = json.loads(hit.value)
                return lat, token
        lat, token = await self.session.read_transaction(get_short_rules, token_ds_words)
        if self.emcache:
            await self.emcache.set(hsh, json.dumps([lat, token]).encode("utf-8"), noreply=True)
        return lat, token
    # def get_short_rule(self, token_ds_words: list[str]):
    #    return self.session.read_transaction(get_short_rules, token_ds_words)


async def get_lat_rules(
        trx: AsyncTransaction,
        tokens: list[tuple[str]]) -> list[LatRule]:
    """ Retrieve the LAT rules starting with the given n-gram. """
    if len(tokens) >= 4:
        result = await trx.run(
            "MATCH (w1:Start)-[w2:NEXT]->(e2) WHERE w1.word IN $first AND w2.word IN $second "
            "CALL { "
            "  WITH e2 MATCH (e2)-[w3:NEXT]->(e3) WHERE w3.word IN $third "
            "  CALL {"
            "    WITH e3 MATCH r = (e3)-[w4:NEXT]->()-[:NEXT*0..23]->()-[:LAT]->(l:Lat) "
            "    WHERE w4.word IN $fourth "
            "    RETURN [p IN relationships(r) WHERE p.word IS NOT NULL | p.word] AS path, l.lat AS lat ORDER BY length(r) DESC "
            "    UNION ALL "
            "    WITH e3 MATCH (e3)-[:LAT]->(l:Lat) "
            "    RETURN [] AS path, l.lat AS lat LIMIT 1 "
            "  } "
            "  RETURN [w3.word] + path AS path, lat "
            "  UNION ALL "
            "  WITH e2 MATCH (e2)-[:LAT]->(l:Lat) "
            "  RETURN [] AS path, l.lat AS lat LIMIT 1 "
            "} "
            "RETURN [w1.word, w2.word] + path AS path, lat ORDER BY size(path) DESC",
            first=tokens[0], second=tokens[1], third=tokens[2], fourth=tokens[3])
    elif len(tokens) == 3:
        result = await trx.run(
            "MATCH (w1:Start)-[w2:NEXT]->(e2) WHERE w1.word IN $first AND w2.word IN $second "
            "Call { "
            "  WITH e2 MATCH (e2)-[w3:NEXT]->()-[:LAT]->(l:Lat) WHERE w3.word IN $third "
            "  RETURN [w3.word] AS word3, l.lat AS lat LIMIT 1 "
            "  UNION ALL "
            "  WITH e2 MATCH (e2)-[:LAT]->(l:Lat) "
            "  RETURN [] AS word3, l.lat AS lat LIMIT 1 "
            "} "
            "RETURN [w1.word, w2.word] + word3 as path, lat",
            first=tokens[0], second=tokens[1], third=tokens[2])
    else:  # bigram fallthrough
        result = await trx.run(
            "MATCH (w1:Start)-[w2:NEXT]->()-[:LAT]->(l:Lat) "
            "WHERE w1.word IN $first AND w2.word IN $second "
            "RETURN [w1.word, w2.word] AS path, "
            "l.lat as lat LIMIT 1",
            first=tokens[0], second=tokens[1])
    res = [{"lat": record["lat"],
            "path": record["path"]}
           async for record in result]
    return res

SEPARATOR = f"{hash('+++MichaelRingenbergSeparator+++')}"

async def get_lat_rules_depr(
    # def get_lat_rules(
        trx: AsyncTransaction,
        tokens: list[tuple[str]]) -> list[LatRule]:
    """ Retrieve the LAT rules starting with the given n-gram. """
    #hsh = SEPARATOR.join(['+++'.join(token) for token in tokens])
    res = None  # CACHE.get(hsh)
    if res is None:
        if len(tokens) >= 4:
            result = await trx.run(
                # result = trx.run(
                "MATCH p = (w1:Start)-[w2:NEXT]->()-[w3:NEXT]->()-[w4:NEXT]->()-[:NEXT*0..25]->()"
                "-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second AND w3.word IN $third "
                "AND w4.word IN $fourth "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat ORDER BY length(p) DESC "
                "UNION ALL MATCH p = (w1:Start)-[w2:NEXT]->()-[w3:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second AND w3.word IN $third "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat LIMIT 1 "
                "UNION ALL MATCH p = (w1:Start)-[w2:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat LIMIT 1",
                first=tokens[0], second=tokens[1], third=tokens[2], fourth=tokens[3])
        elif len(tokens) == 3:
            result = await trx.run(
                # result = trx.run(
                "MATCH p = (w1:Start)-[w2:NEXT]->()-[w3:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second AND w3.word IN $third "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat LIMIT 1 "
                "UNION ALL MATCH p = (w1:Start)-[w2:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat LIMIT 1",
                first=tokens[0], second=tokens[1], third=tokens[2])
        else:  # bigram fallthrough
            result = await trx.run(
                # result = trx.run(
                "MATCH p = (w1:Start)-[w2:NEXT]->()-[:LAT]->(l:Lat) "
                "WHERE w1.word IN $first AND w2.word IN $second "
                "RETURN w1.word AS start, relationships(p) as path, "
                "l.lat as lat LIMIT 1",
                first=tokens[0], second=tokens[1])
        # duck type NEXT as type is not in record properties.
        res = [{"lat": record["lat"],
                "path": [record["start"],
                         *[path["word"] for path in record["path"]
                           if "word" in path]]}
               # for record in result]
               async for record in result]
        #CACHE.put(hsh, res)
    return res

#SHORT_CACHE = {}


async def get_short_rules(trx: AsyncTransaction,
                          # def get_short_rules(trx: Transaction,
                          first_tokens: list[str]) -> tuple[str, str]:
    """ Retrieve the unigram LAT rule for the given token. """
    #hsh = tuple(first_tokens)
    # if hsh not in SHORT_CACHE:
    trans = await trx.run(
        # trans = trx.run(
        "MATCH (s:Start)-[:LAT]->(l:Lat) WHERE s.word IN $first "
        "RETURN s.word AS token, l.lat AS lat "
        "ORDER BY token DESC, lat DESC LIMIT 1",
        first=first_tokens)
    result = await trans.single()
    #result = trans.single()
    #SHORT_CACHE[hsh] = result
    #result = SHORT_CACHE.get(hsh, None)
    if result:
        return result["lat"], result["token"]
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
            self.cache.popitem(last=False)


CACHE = LRUCache(2**22)
