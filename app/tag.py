""" On demand DocuScope tagger interface. """
#from enum import Enum, auto
import logging
import re
from collections import Counter, defaultdict
from typing import List

#import aioredis
from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
#from uuid import UUID, uuid1
from lxml import etree  # nosec
from lxml.html import Classes
from neo4j import Driver, GraphDatabase, Session
from pydantic import BaseModel, constr

from .count_patterns import CategoryPatternData, count_patterns, sort_patterns
from .default_settings import SETTINGS
from .ds_tagger import get_wordclasses
from .ity.formatters.simple_html_formatter import SimpleHTMLFormatter
from .ity.taggers.docuscope_tagger_neo import DocuscopeTaggerNeo
from .ity.tokenizers.regex_tokenizer import RegexTokenizer
from .ity.tokenizers.tokenizer import TokenType
from .lat_frame import LAT_MAP

#from sse_starlette.sse import EventSourceResponse

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
#WORDCLASSES = None


@APP.on_event("startup")
async def startup_event():
    """Initialize shared static data."""
    global DRIVER  # pylint: disable=global-statement
    # DRIVER = AsyncGraphDatabase.driver(
    DRIVER = GraphDatabase.driver(
        SETTINGS.neo4j_uri,
        # pylint: disable=no-member
        auth=(SETTINGS.neo4j_user, SETTINGS.neo4j_password.get_secret_value())
    )
    #global WORDCLASSES
    APP.WORDCLASSES = get_wordclasses()


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

# class DocuScopeTagResponse(BaseModel):
#    """"""
#    id: str = ""
#    link: str

# class State(Enum):
#    RECIEVED = auto()
#    TOKENIZING = auto()
#    PROCESSING = auto()
#    FORMATTING = auto()
#    DONE = auto()
#    ERROR = auto()

# class Status(BaseModel):
#    event: State = State.RECIEVED
#    processed: int = 0
#    data: DocuScopeDocument = ...


# async def status_generator(uuid: UUID, request: Request, redis: aioredis.Redis):
#    while True:
#        if await request.is_disconnected():
#            logging.info("client disconnected!")
#            break
#        state = await redis.xread([uuid])
#        yield state

# @APP.get("/tag/{uuid}/status/", response_model=Status)
# async def get_status(uuid: UUID, request: Request,
#             redis: aioredis.Redis = Depends(redis_session)):
#    gen = status_generator(uuid, request, redis)
#    return EventSourceResponse(gen)
#
#    return await REDIS.json().get(uuid)

# @APP.get("/tag/{uuid}/results/")
# async def get_results(uuid: UUID) -> DocuScopeDocument:
#    return await REDIS.json().get(uuid)

class TagRequst(BaseModel):
    """Schema for tagging requests. """
    text: constr(strip_whitespace=True, min_length=1)


@APP.post("/tag")
async def tag_text(tag_request: TagRequst,
                   rule_db: Session = Depends(rule_session)) -> DocuScopeDocument:
    """Use DocuScope to tag the submitted text."""
    tokenizer = RegexTokenizer()
    tokens = tokenizer.tokenize(tag_request.text)
    tagger = DocuscopeTaggerNeo(return_untagged_tags=True, return_no_rules_tags=True,
        return_included_tags=True, wordclasses=APP.WORDCLASSES, session=rule_db)
    rules, tags = tagger.tag(tokens)
    print(rules)
    print(tags)
    formatter = SimpleHTMLFormatter()
    output = formatter.format(
        tags=(rules, tags), tokens=tokens, text_str=tag_request.text)
    html_content = re.sub(r'(\n|\s)+', ' ', output)
    print(html_content)
    html = "<body><p>" + \
        re.sub(r'<span[^>]*>\s*PZPZPZ\s*</span>',
               '</p><p>', html_content) + "</p></body>"
    parser = etree.XMLParser(
        load_dtd=False, no_network=True, remove_pis=True, resolve_entities=False)
    try:
        etr = etree.fromstring(html, parser=parser)  # nosec
    except Exception as exp:
        logging.error(html)
        raise exp
    pats = defaultdict(Counter)
    count_patterns(etr, pats)
    for tag in etr.iterfind(".//*[@data-key]"):
        lat = tag.get('data-key')
        categories = LAT_MAP.get(lat, None)
        if categories:
            if categories['cluster'] != 'Other':
                cats = [categories['category'],
                        categories['subcategory'],
                        categories['cluster']]
                cpath = " > ".join([categories['category_label'],
                                    categories['subcategory_label'],
                                    categories['cluster_label']])
                sup = etree.SubElement(tag, "sup")
                sup.text = "{" + cpath + "}"
                sclasses = Classes(sup.attrib)
                sclasses |= cats
                sclasses |= ['d_none', 'cluster_id']
                tclasses = Classes(tag.attrib)
                tclasses |= cats
                tag.set('data-key', cpath)
        #else:
        #    logging.info("No category mapping for %s.", lat)
    html_out = etree.tostring(etr)
    type_count = Counter([token.type for token in tokens])
    return DocuScopeDocument(
        html_content=html_out,
        patterns=sort_patterns(pats),
        word_count=type_count[TokenType.WORD]
    )
    #tagging = tag_document(tag_request.text, request, rule_db)
    # return EventSourceResponse(tagging)

# async def tag_document(text: str, request: Request, rule_db: Session) -> Status:
#    yield Status(event=State.RECIEVED)
#    yield Status(event=State.TOKENIZING)
#    tokenizer = RegexTokenizer()
#    tokens = tokenizer.tokenize(text)
#
#    tagger = DocuscopeTaggerNeo(return_included_tags=True,
#             wordclasses=WORDCLASSES, session=rule_db)
#    tagger_gen = tagger.tag_next(tokens)
#    tot_tokens = len(tokens)
#    tenpc = tot_tokens // 10
#    last_indx = 0
#    while True:
#        if await request.is_disconnected():
#            logging.info("client disconnected!")
#            return
#        try:
#            indx = next(tagger_gen)
#        except StopIteration:
#            break
#        if indx - last_indx >= tenpc:
#            last_indx = indx
#            yield Status(event=State.PROCESSING, processed=tot_tokens // indx)
#    yield Status(event=State.FORMATTING, processed=100)
#    formatter = SimpleHTMLFormatter()
#    output = formatter.format(tags = (tagger.rules, tagger.tags),
#                    tokens=tokens, text_str=text)
#    html_content = re.sub(r'(\n|\s)+', ' ', output)
#    html = "<body><p>" + re.sub(r'<span[^>]*>\s*PZPZPZ\s*</span>', '</p><p>', html_content)
#            + "</p></body>"
#    parser = etree.XMLParser(load_dtd=False, no_network=True,
#             remove_pis=True, resolve_entities=False)
#    try:
#        etr = etree.fromstring(html, parser=parser) # nosec
#    except Exception as exp:
#        logging.error(html)
#        raise exp
#    pats = defaultdict(Counter)
#    count_patterns(etr, pats)
#    for tag in etr.iterfind(".//*[@data-key]"):
#        lat = tag.get('data-key')
#        categories = LAT_MAP[lat]
#        if categories:
#            if categories['cluster'] != 'Other':
#                cats = [categories['category'],
#                        categories['subcategory'],
#                        categories['cluster']]
#                cpath = " > ".join([categories['category_label'],
#                                    categories['subcategory_label'],
#                                    categories['cluster_label']])
#                sup = etree.SubElement(tag, "sup")
#                sup.text = "{" + cpath + "}"
#                sclasses = Classes(sup.attrib)
#                sclasses |= cats
#                sclasses |= ['d_none', 'cluster_id']
#                tclasses = Classes(tag.attrib)
#                tclasses |= cats
#                tag.set('data-key', cpath)
#        else:
#            logging.info("No category mapping for %s.", lat)
#    html_out = etree.tostring(etr)
#    type_count = Counter([token.type for token in tokens])
#    yield State(event=State.DONE, processed=100,
#                data=DocuScopeDocument(
#                    html_content=html_out,
#                    patterns=sort_patterns(pats),
#                    word_count=type_count[TokenType.WORD]
#                ))

APP.mount('/static', StaticFiles(directory="static", html=True))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import asyncio

    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    config = Config()
    config.bind = ["0.0.0.0:8000"]
    config.loglevel = "info"
    asyncio.run(serve(APP, config))
