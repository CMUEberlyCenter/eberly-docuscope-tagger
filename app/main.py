""" The online DocuScope tagger interface. """
import cProfile
import logging
import re
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from difflib import ndiff
from html import escape
from typing import Counter, Dict, List, Literal, Optional
from uuid import UUID

import emcache
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
#from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from jsondiff import diff
from lxml import etree  # nosec
from neo4j import AsyncGraphDatabase
from neo4j import AsyncSession as NeoAsyncSession
from pydantic import BaseModel, constr
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
#from starlette.middeware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from .count_patterns import CategoryPatternData, count_patterns, sort_patterns
from .default_settings import SETTINGS, SQLALCHEMY_DATABASE_URI
from .docx_to_text import docx_to_text
from .database import Submission
from .ds_tagger import get_wordclasses
from .ity.formatters.simple_html_formatter import SimpleHTMLFormatter
from .ity.tagger import ItyTaggerResult, neo_tagger, tag_json
from .ity.taggers.docuscope_tagger_neo import DocuscopeTaggerNeo
from .ity.tokenizers.regex_tokenizer import RegexTokenizer
from .ity.tokenizers.tokenizer import TokenType
from .lat_frame import generate_tagged_html

CACHE = None
ENGINE = create_async_engine(SQLALCHEMY_DATABASE_URI)
SESSION = sessionmaker(bind=ENGINE, expire_on_commit=False,
                       class_=AsyncSession, future=True)
DRIVER = AsyncGraphDatabase.driver(
    SETTINGS.neo4j_uri,
    auth=(SETTINGS.neo4j_user,
          SETTINGS.neo4j_password.get_secret_value())) # pylint: disable=no-member
WORDCLASSES = None
TAGGER = None

app = FastAPI(
    title="DocuScope Tagger",
    description="Run the DocuScope tagger on a document in the database or on given text.",
    version="4.0.0",
    license={
        'name': 'CC BY-NC-SA 4.0',
        'url': 'https://creativecommons.org/licenses/by-nc-sa/4.0/'
    })

# app.add_middleware(
#    CORSMiddleware,
#    allow_origins=['*'],
#    allow_credentials=True,
#    allow_methods=['GET', 'POST'],
#    allow_headers=['*'])
# app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(GZipMiddleware)


@app.on_event("startup")
async def startup_event():
    """Initialize some important static data on startup.
    Loads the _wordclasses json file for use by tagger.
    Initializes database driver."""
    global WORDCLASSES, CACHE  # pylint: disable=global-statement
    WORDCLASSES = get_wordclasses()
    CACHE = await emcache.create_client([emcache.MemcachedHostAddress(
        SETTINGS.memcache_url, SETTINGS.memcache_port)])


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler.  Closes database connection cleanly."""
    if DRIVER is not None:
        await DRIVER.close()
    if ENGINE is not None:
        await ENGINE.dispose()
    if CACHE is not None:
        await CACHE.close()


async def session() -> AsyncSession:
    """Establish a scoped session for accessing the database."""
    my_session: AsyncSession = SESSION()
    try:
        yield my_session
        await my_session.commit()
    except:
        await my_session.rollback()
        raise
    finally:
        await my_session.close()


async def neo_session() -> NeoAsyncSession:
    """Establish a scoped session for accessing the neo4j database."""
    my_session: NeoAsyncSession = DRIVER.session()
    try:
        yield my_session
    finally:
        await my_session.close()


class DocuScopeDocument(BaseModel):
    """Model for tagged text."""
    word_count: int = 0
    html_content: str = ""
    patterns: List[CategoryPatternData]
    tagging_time: timedelta


class TagRequst(BaseModel):
    """Schema for tagging requests. """
    text: constr(strip_whitespace=True, min_length=1)


@app.post("/tag")
async def tag_text(tag_request: TagRequst,
                   rule_db: NeoAsyncSession = Depends(neo_session)) -> DocuScopeDocument:
    """Use DocuScope to tag the submitted text."""
    start_time = datetime.now()
    text = escape(tag_request.text)
    tokens = RegexTokenizer().tokenize(text)
    tagger = DocuscopeTaggerNeo(return_untagged_tags=False, return_no_rules_tags=True,
                                return_included_tags=True, wordclasses=WORDCLASSES,
                                session=rule_db, cache=CACHE)
    rules, tags = await tagger.tag(tokens)
    output = SimpleHTMLFormatter().format(
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


class Message(BaseModel):
    """Model for tag responses."""
    #pylint: disable=too-few-public-methods
    doc_id: Optional[UUID]
    message: str
    event: Literal['submitted', 'processing', 'done', 'error', 'pending']


async def tag_document(  #pylint: disable=too-many-locals
        doc_id: UUID,
        request: Request,
        sql: AsyncSession,
        neo: NeoAsyncSession,
        cache: emcache.Client):
    """Incrementally tag the given database document."""
    start_time = datetime.now()
    query = await sql.execute(select(Submission.content, Submission.name)
                              .where(Submission.id == doc_id))
    (doc_content, name) = query.first() or (None, None)
    if doc_content:
        await sql.execute(update(Submission).where(Submission.id == doc_id)
                          .values(state='submitted'))
        await sql.commit()
        yield Message(doc_id=doc_id, event="submitted", message="0")
        try:
            if name.endswith(".docx"):
                doc_content = docx_to_text(doc_content)
            tokenizer = RegexTokenizer()
            tokens = tokenizer.tokenize(doc_content)
            tagger = DocuscopeTaggerNeo(return_untagged_tags=False, return_no_rules_tags=True,
                                        return_included_tags=True, wordclasses=WORDCLASSES,
                                        session=neo, cache=cache)
            tagger_gen = tagger.tag_next(tokens)
            timeout = start_time + timedelta(seconds=1)
            while True:
                if await request.is_disconnected():
                    logging.info("Client Disconnected!")
                    return
                try:
                    indx = await tagger_gen.asend(None)
                except StopAsyncIteration:
                    break
                if datetime.now() > timeout:
                    timeout = datetime.now() + timedelta(seconds=1)
                    yield Message(doc_id=doc_id, event='processing',
                                  message=f"{indx * 100 // len(tokens)}")
            yield Message(doc_id=doc_id, event='processing', message='100')
            output = SimpleHTMLFormatter().format(tags=(tagger.rules, tagger.tags),
                                                  tokens=tokens, text_str=doc_content)
        except Exception as exc:
            logging.error("Error while tagging %s", doc_id)
            traceback.print_exc()
            await sql.execute(update(Submission).where(Submission.id == doc_id).values(
                state='error',
                processed={
                    'error': f'{exc}',
                    'trace': traceback.format_exc(),
                    'date_tagged': datetime.now(timezone.utc).astimezone().isoformat(),
                    'tagging_time': str(datetime.now() - start_time)
                }
            ))
            raise exc
        type_count = Counter([token.type for token in tokens])
        not_excluded = set(TokenType) - set(tokenizer.excluded_token_types)
        await sql.execute(update(Submission).where(Submission.id == doc_id).values(
            state='tagged',
            processed=tag_json(ItyTaggerResult(
                text_contents=doc_content,
                format_output=output,
                tag_dict=tagger.rules,
                num_tokens=len(tokens),
                num_word_tokens=type_count[TokenType.WORD],
                num_punctuation_tokens=type_count[TokenType.PUNCTUATION],
                num_included_tokens=sum([type_count[itype]
                                        for itype in not_excluded]),
                num_excluded_tokens=sum(
                    [type_count[etype] for etype in tokenizer.excluded_token_types]),
                tag_chain=[tag.rules[0][0].split(
                    '.')[-1] for tag in tagger.tags]
            )).dict()
        ))
        yield Message(doc_id=doc_id, event="done", message=str(datetime.now() - start_time))
    else:
        await sql.execute(update(Submission).where(Submission.id == doc_id).values(
            state='error',
            processed={
                'error': 'No file data to process.',
                'date_tagged': datetime.now(timezone.utc).astimezone().isoformat(),
                'tagging_time': 0
            }
        ))
        yield Message(doc_id=doc_id, event="error", message=f"No content in document: {name}!")


@app.get("/tag/{uuid}", response_model=Message)
async def tag(uuid: UUID,
              request: Request,
              sql: AsyncSession = Depends(session),
              neo: NeoAsyncSession = Depends(neo_session)) -> Message:
    """ Check the document status and tag if pending. """
    # check if uuid
    try:
        UUID(f"{uuid}")
    except ValueError as vexc:
        raise HTTPException(detail=f"{vexc}: {uuid}",
                            status_code=status.HTTP_400_BAD_REQUEST) from vexc
    # get current status.
    result = await sql.execute(select(Submission.state).where(Submission.id == uuid))
    (state,) = result.first()
    if state == 'pending':
        # check for too many submitted? Need to find limit emperically.
        tagging = tag_document(uuid, request, sql, neo, CACHE)
        return EventSourceResponse(tagging)
    if state == 'submitted':
        return Message(doc_id=uuid, message=f"{uuid} already submitted.", event='done')
    if state == 'tagged':
        return Message(doc_id=uuid, message=f"{uuid} already tagged.", event='done')
    if state == 'error':
        raise HTTPException(detail=f"Tagging failed for {uuid}",
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if state is None:
        raise HTTPException(detail="Document unavailable.",
                            status_code=status.HTTP_404_NOT_FOUND)
    raise HTTPException(detail=f"Unknown state: {state} for {uuid}",
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


async def tag_documents(request: Request, neo: NeoAsyncSession, cache: emcache.Client):
    """Tag all pending documents in the database."""
    sql: AsyncSession
    while True:  # wait until outstanding processing is done.
        if await request.is_disconnected():
            logging.info("Client Disconnected!")
            return
        async with SESSION() as sql:
            result = await sql.execute(select(func.count(Submission.id))
                                       .execution_options(populate_existing=True)
                                       .where(Submission.state == 'submitted'))
            (submitted,) = result.first() or (0,)
            if submitted > 0:
                yield Message(
                    message=f"Waiting for {submitted} prior documents to finish.",
                    event="pending")
            else:
                break
            await sql.commit()  # not necessary, but good idea.
        await asyncio.sleep(1)
    while True:
        if await request.is_disconnected():
            logging.info("Client Disconnected!")
            return
        async with SESSION() as sql:
            pending = await sql.execute(select(Submission.id).where(Submission.state == 'pending'))
            (docid,) = pending.first() or (None,)
            if docid:
                print(docid)
                tag_next = tag_document(docid, request, sql, neo, cache)
                while True:
                    if await request.is_disconnected():
                        logging.info("Client Disconnected!")
                        return
                    try:
                        yield await tag_next.asend(None)
                    except StopAsyncIteration:
                        break
            else:
                break
            await sql.commit()
    yield Message(message="No more pending documents.", event='done')


@app.get('/tag')
async def tag_all(request: Request,
                  neo: NeoAsyncSession = Depends(neo_session)):
    """Tag all of the pending documents in the database while emitting sse's on progress."""
    return EventSourceResponse(tag_documents(request, neo, CACHE))


class Status(BaseModel):
    """Return type for /status requests. The state of a document."""
    state: str
    count: Optional[int]


@app.get('/status/{uuid}')
async def document_status(uuid: UUID, sql: AsyncSession = Depends(session)) -> Status:
    """Get the state of the given document."""
    result = await sql.execute(select(Submission.state).where(Submission.id == uuid))
    return result.first()


@app.get('/status')
async def status_all(sql: AsyncSession = Depends(session)) -> list[Status]:
    """Get the count of the various states of the documents in the database."""
    result = await sql.execute(select(Submission.state, func.count(Submission.state))
                               .group_by(Submission.state))
    return result.all()


class CheckResults(BaseModel):
    """Model for testing results."""
    #pylint: disable=too-few-public-methods
    output_check: bool
    token_check: bool
    tag_dict_check: int


@app.get("/test/{uuid}", response_model=CheckResults)
async def test_tagging(uuid: UUID,
                       sql: AsyncSession = Depends(session),
                       neo: NeoAsyncSession = Depends(neo_session)):
    """ Check the document status and start the tagging if appropriate. """
    # check if uuid
    try:
        UUID(f"{uuid}")
    except ValueError as vexc:
        raise HTTPException(detail=f"{vexc}: {uuid}",
                            status_code=status.HTTP_400_BAD_REQUEST) from vexc
    # get current status.
    query = await sql.execute(select(Submission.state).where(Submission.id == uuid))
    (state,) = query.first()
    if state in ['pending', 'submitted']:
        return {"message": f"{uuid} is not yet tagged."}
    if state == 'tagged':
        # check for too many submitted
        return await check_tagging(uuid, sql, neo, CACHE)

    if state == 'error':
        raise HTTPException(detail=f"Tagging failed for {uuid}",
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if state is None:
        raise HTTPException(detail="Document unavailable.",
                            status_code=status.HTTP_404_NOT_FOUND)
    raise HTTPException(detail=f"Unknown state: {state} for {uuid}",
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


@app.get("/profile/{uuid}")
async def profile_tagging(
        uuid: UUID,
        sql: AsyncSession = Depends(session),
        neo: NeoAsyncSession = Depends(neo_session)):
    """Profile tagging and dump to file."""
    query = await sql.execute(select(Submission.content).where(Submission.id == uuid))
    (doc_content,) = query.first()
    tagger = neo_tagger(WORDCLASSES, neo)
    content = docx_to_text(doc_content)
    with cProfile.Profile() as prof:
        tagger.tag(content)
    prof.dump_stats('mprof.stat')


@app.post('/batchtest', response_model=Dict[UUID, CheckResults])
async def test_corpus(
        corpus: list[UUID],
        sql: AsyncSession = Depends(session),
        neo: NeoAsyncSession = Depends(neo_session)):
    """Perform tagging check on multiple documents."""
    return {uuid: await check_tagging(uuid, sql, neo, CACHE) for uuid in corpus}


async def check_tagging(  #pylint: disable=too-many-locals
        doc_id: UUID,
        sql: AsyncSession,
        neo: NeoAsyncSession,
        cache: emcache.Client) -> CheckResults:
    """Perform tagging with neo4j tagger and check against the database. """
    query = await sql.execute(select(Submission.content, Submission.name, Submission.processed)
                              .where(Submission.id == doc_id))
    (doc_content, name, processed) = query.first() or (None, None, None)
    if doc_content:
        try:
            if name.endswith(".docx"):
                doc_content = docx_to_text(doc_content)
            tokenizer = RegexTokenizer()
            tokens = tokenizer.tokenize(doc_content)
            tagger = DocuscopeTaggerNeo(return_untagged_tags=False, return_no_rules_tags=True,
                                        return_included_tags=True, wordclasses=WORDCLASSES,
                                        session=neo, cache=cache)
            tagger_gen = tagger.tag_next(tokens)
            while True:
                try:
                    await tagger_gen.asend(None)
                except StopAsyncIteration:
                    break
            output = SimpleHTMLFormatter().format(tags=(tagger.rules, tagger.tags),
                                                  tokens=tokens, text_str=doc_content)
        except Exception as exc:
            logging.error("Error while tagging %s", doc_id)
            traceback.print_exc()
            raise exc
        type_count = Counter([token.type for token in tokens])
        not_excluded = set(TokenType) - set(tokenizer.excluded_token_types)
        test_processed = tag_json(ItyTaggerResult(
            text_contents=doc_content,
            format_output=output,
            tag_dict=tagger.rules,
            num_tokens=len(tokens),
            num_word_tokens=type_count[TokenType.WORD],
            num_punctuation_tokens=type_count[TokenType.PUNCTUATION],
            num_included_tokens=sum([type_count[itype]
                                    for itype in not_excluded]),
            num_excluded_tokens=sum([type_count[etype]
                                     for etype in tokenizer.excluded_token_types]),
            tag_chain=[tag.rules[0][0].split('.')[-1] for tag in tagger.tags]
        )).dict()
        tag_diff = diff(processed, test_processed)
        if tag_diff:
            logging.warning("diff: %s", tag_diff)
        if processed['ds_output'] != test_processed['ds_output']:
            logging.warning(''.join(ndiff(
                "</span>\n".join(
                    processed['ds_output'].split('</span>')).splitlines(keepends=True),
                "</span>\n".join(
                    test_processed['ds_output'].split("</span>")).splitlines(keepends=True))))
        return {
            "output_check": processed['ds_output'] == test_processed['ds_output'],
            "token_check": processed['ds_num_tokens'] == test_processed['ds_num_tokens'],
            "tag_dict_check": len(processed['ds_tag_dict']) - len(test_processed['ds_tag_dict']),
            # "tag_count": str(diff(doc_processed['ds_count_dict'], processed['ds_count_dict']))
        }
    logging.error("No document content for %s.", doc_id)
    raise HTTPException(detail=f"No document content for {doc_id}.",
                        status_code=status.HTTP_404_NOT_FOUND)

app.mount('/static', StaticFiles(directory="app/static", html=True))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import asyncio

    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    config = Config()
    config.bind = ["0.0.0.0:8000"]
    config.loglevel = "info"
    asyncio.run(serve(app, config))
