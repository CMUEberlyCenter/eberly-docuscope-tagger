""" The DocuScope Tagger using a neo4j based dictionary. """
# coding=utf-8
__author__ = 'mringenb'

import hashlib
import json
from typing import Optional

import aiomcache
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
            driver: Optional[neo4j.AsyncDriver] = None,
            cache: Optional[aiomcache.Client] = None,
            **kwargs):
        super().__init__(*args, **kwargs)
        self.driver = driver
        self.wordclasses = wordclasses or {}
        self._label = (self._label if self._label else "") + ".default"
        self.cache = cache

    async def get_long_rule(self) -> Optional[LatRule]:
        lookup = [sorted(list(t))
                  for t in self.get_next_ds_words_in_range(0, 4)]
        rules: Optional[list[LatRule]] = None
        if self.cache:
            hsh = hashlib.sha256(str(lookup).encode(
                'utf-8')).hexdigest().encode('utf-8')
            hit = await self.cache.get(hsh)
            if hit is not None:
                rules = json.loads(hit)
        if rules is None:
            async with self.driver.session() as session:
                rules = await session.execute_read(
                    get_lat_rules, lookup)
        if rules and self.cache:
            jrules = json.dumps(rules)
            await self.cache.set(hsh, jrules.encode('utf-8'))
        tokens = self.get_next_ds_words_in_range(
            0, len(rules[0]['path'])) if len(rules) > 0 else []
        ds_rule = next((r for r in rules
                        if rule_applies_for_tokens(r['path'], tokens, offset=2)), None)
        return ds_rule

    async def get_short_rule(self, token_ds_words: list[str]):
        if len(token_ds_words) == 0:
            return None, None
        if self.cache:
            hsh = hashlib.sha256(str(sorted(token_ds_words)).encode('utf-8'))\
                .hexdigest().encode('utf-8')
            hit = await self.cache.get(hsh)
            if hit is not None:
                [lat, token] = json.loads(hit)
                return lat, token
        async with self.driver.session() as session:
            lat, token = await session.execute_read(get_short_rules, token_ds_words)
        if self.cache:
            await self.cache.set(hsh, json.dumps([lat, token]).encode("utf-8"))
        return lat, token


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
            "    RETURN [p IN relationships(r) WHERE p.word IS NOT NULL | p.word] AS path, "
            "      l.lat AS lat ORDER BY length(r) DESC "
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
    return [{"lat": record["lat"],
            "path": record["path"]}
            async for record in result]


async def get_short_rules(trx: AsyncTransaction,
                          first_tokens: list[str]) -> tuple[str, str]:
    """ Retrieve the unigram LAT rule for the given token. """
    trans = await trx.run(
        "MATCH (s:Start)-[:LAT]->(l:Lat) WHERE s.word IN $first "
        "RETURN s.word AS token, l.lat AS lat "
        "ORDER BY token DESC, lat DESC LIMIT 1",
        first=first_tokens)
    result = await trans.single()
    if result:
        return result["lat"], result["token"]
    return None, None
