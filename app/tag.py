""" On demand DocuScope tagger interface. """
#from enum import Enum, auto
from datetime import datetime, timedelta
import logging
import re
from collections import Counter, defaultdict
from html import escape
from typing import List

#import aioredis
from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
#from uuid import UUID, uuid1
from lxml import etree  # nosec
from neo4j import Driver, GraphDatabase, Session
from pydantic import BaseModel, constr

from .count_patterns import CategoryPatternData, count_patterns, sort_patterns
from .default_settings import SETTINGS
from .ds_tagger import get_wordclasses
from .ity.formatters.simple_html_formatter import SimpleHTMLFormatter
from .ity.taggers.docuscope_tagger_neo import DocuscopeTaggerNeo
from .ity.tokenizers.regex_tokenizer import RegexTokenizer
from .ity.tokenizers.tokenizer import TokenType
from .lat_frame import generate_tagged_html


APP = FastAPI(
    title="DocuScope Online Tagger",
    description="Given text, tag it using DocuScope.",
    version="1.0.0",
    license={
        'name': 'CC BY-NC-SA 4.0',
        'url': 'https://creativecommons.org/licenses/by-nc-sa/4.0/'
    }
)

DRIVER: Driver = None
WORDCLASSES: dict[str, list[str]] = None


@APP.on_event("startup")
async def startup_event():
    """Initialize shared static data."""
    global DRIVER, WORDCLASSES  # pylint: disable=global-statement
    # DRIVER = AsyncGraphDatabase.driver(
    DRIVER = GraphDatabase.driver(
        SETTINGS.neo4j_uri,
        # pylint: disable=no-member
        auth=(SETTINGS.neo4j_user, SETTINGS.neo4j_password.get_secret_value())
    )
    WORDCLASSES = get_wordclasses()


@APP.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler."""
    if DRIVER is not None:
        # await DRIVER.close()
        DRIVER.close()


async def rule_session():
    """Establish a scoped session for accessing rules database."""
    session: Session = DRIVER.session()
    try:
        yield session
    finally:
        # await session.close()
        session.close()

# async def redis_session():
#    redis = await aioredis.from_url("redis://localhost", encoding="utf-8")
#    yield redis
#    await redis.close()


class DocuScopeDocument(BaseModel):
    """Model for tagged text."""
    word_count: int = 0
    html_content: str = ""
    patterns: List[CategoryPatternData]
    tagging_time: timedelta


class TagRequst(BaseModel):
    """Schema for tagging requests. """
    text: constr(strip_whitespace=True, min_length=1)


@APP.post("/tag")
async def tag_text(tag_request: TagRequst,
                   rule_db: Session = Depends(rule_session)) -> DocuScopeDocument:
    """Use DocuScope to tag the submitted text."""
    start_time = datetime.now()
    tokenizer = RegexTokenizer()
    text = escape(tag_request.text)
    tokens = tokenizer.tokenize(text)
    tagger = DocuscopeTaggerNeo(return_untagged_tags=True, return_no_rules_tags=True,
        return_included_tags=True, wordclasses=WORDCLASSES, session=rule_db)
    rules, tags = tagger.tag(tokens)
    formatter = SimpleHTMLFormatter()
    output = formatter.format(
        tags=(rules, tags), tokens=tokens, text_str=text)
    output = re.sub(r'(\n|\s)+', ' ', output)
    output = "<body><p>" + \
        re.sub(r'<span[^>]*>\s*PZPZPZ\s*</span>',
               '</p><p>', output) + "</p></body>"
    parser = etree.XMLParser(
        load_dtd=False, no_network=True, remove_pis=True, resolve_entities=False)
    try:
        etr = etree.fromstring(output, parser=parser)  # nosec
    except Exception as exp:
        logging.error(output)
        raise exp
    pats = defaultdict(Counter)
    count_patterns(etr, pats)
    type_count = Counter([token.type for token in tokens])
    return DocuScopeDocument(
        html_content=generate_tagged_html(etr),
        patterns=sort_patterns(pats),
        word_count=type_count[TokenType.WORD],
        tagging_time=datetime.now() - start_time
        # pandas.Timedelta(datetime.now()-start_time).isoformat()
    )

APP.mount('/static', StaticFiles(directory="app/static", html=True))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import asyncio

    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    config = Config()
    config.bind = ["0.0.0.0:8000"]
    config.loglevel = "info"
    asyncio.run(serve(APP, config))
