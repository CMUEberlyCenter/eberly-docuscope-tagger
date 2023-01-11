""" The online DocuScope tagger interface. """
import asyncio
import logging
import re
import traceback
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Counter, Iterator, List, Literal, Optional, Union
from uuid import UUID

import emcache
from bs4 import BeautifulSoup
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.staticfiles import StaticFiles
#from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from neo4j import AsyncGraphDatabase
from neo4j import AsyncSession as NeoAsyncSession
from pydantic import BaseModel, constr
from sqlalchemy import column, func, insert, select, union_all, update
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.cors import CORSMiddleware

from .count_patterns import CategoryPatternData, count_patterns, sort_patterns
from .database import Submission, Tagging
from .default_settings import SETTINGS, SQLALCHEMY_DATABASE_URI
from .docx_to_text import docx_to_text
from .ds_tagger import get_wordclasses
from .ity.formatters.simple_html_formatter import SimpleHTMLFormatter
from .ity.tagger import ItyTaggerResult, tag_json
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
          SETTINGS.neo4j_password.get_secret_value()))  # pylint: disable=no-member
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['GET', 'POST'],
    allow_headers=['*'])
# app.add_middleware(HTTPSRedirectMiddleware)


@app.on_event("startup")
async def startup_event():
    """Initialize some important static data on startup.
    Loads the _wordclasses json file for use by tagger.
    Initializes database driver."""
    global WORDCLASSES, CACHE  # pylint: disable=global-statement
    WORDCLASSES = get_wordclasses()
    try:
        CACHE = await emcache.create_client([emcache.MemcachedHostAddress(
            SETTINGS.memcache_url, SETTINGS.memcache_port)])
    except asyncio.TimeoutError as exc:
        logging.warning(exc)
        CACHE = None


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
    my_session: NeoAsyncSession = DRIVER.session(
    )  # ({"database": SETTINGS.neo4j_database})
    try:
        yield my_session
    finally:
        await my_session.close()


class ServerSentEvent(BaseModel):
    """Model for Server Sent Events produced by the tagger."""
    event: Literal['submitted', 'processing', 'done', 'error', 'pending']
    data: str  # Using Json type causes single quote conversion.


class Message(BaseModel):
    """Model for tag responses."""
    doc_id: Optional[UUID]
    status: str


class DocuScopeDocument(BaseModel):
    """Model for tagged text."""
    doc_id: Optional[UUID]
    word_count: int = 0
    html_content: str = ""
    patterns: List[CategoryPatternData]
    tagging_time: timedelta


class TagRequst(BaseModel):
    """Schema for tagging requests. """
    text: constr(strip_whitespace=True, min_length=1)


class ErrorResponse(BaseModel):
    """Schema for error response."""
    detail: str


@app.post("/tag", response_model=ServerSentEvent, responses={
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "description": "Internal Service Error", "model": ErrorResponse}
})
async def tag_posted_input(
        tag_request: TagRequst,
        request: Request,
        rule_db: NeoAsyncSession = Depends(neo_session),
        sql: AsyncSession = Depends(session)):
    """Responds to post requests to tag a TagRequest.  Returns ServerSentEvents."""
    return EventSourceResponse(tag_text(tag_request.text, request, rule_db, sql))


async def tag_text(text: str, request: Request,
                   rule_db: NeoAsyncSession, sql: AsyncSession) -> Iterator[ServerSentEvent]:
    """Use DocuScope to tag the submitted text.
    Yields ServerSentEvent dicts because servlet-sse expects dicts."""
    # pylint: disable=too-many-locals
    start_time = perf_counter()
    ins: Result = await sql.execute(insert(Tagging).values(
        state='processing', detail={"processed": 0}))
    (doc_id,) = ins.inserted_primary_key
    logging.info("Started tagging %s", doc_id)
    text = re.sub(r'\n\s*\n', ' PZPZPZ\n\n', text)  # detect paragraph breaks.
    tokens = RegexTokenizer().tokenize(text)
    type_count = Counter([token.type for token in tokens])
    await sql.execute(update(Tagging).where(Tagging.id == doc_id).values(
        word_count=type_count[TokenType.WORD]))
    tagger = DocuscopeTaggerNeo(return_untagged_tags=True, return_no_rules_tags=True,
                                return_included_tags=True, wordclasses=WORDCLASSES,
                                session=rule_db, cache=CACHE)
    tagger_gen = tagger.tag_next(tokens)
    timeout = start_time + 1
    indx = 0
    while True:
        if await request.is_disconnected():
            await sql.execute(update(Tagging).where(Tagging.id == doc_id).values(
                state='abort', detail={"processed": indx, "token_count": len(tokens)}))
            await sql.commit()
            logging.warning("Client Disconnected on %s!", doc_id)
            return
        try:
            indx = await tagger_gen.asend(None)
        except StopAsyncIteration:
            break
        except Exception as exp:
            await sql.execute(update(Tagging).where(Tagging.id == doc_id).values(
                state='error',
                detail={"processed": indx, "token_count": len(tokens), "error": str(exp)}))
            await sql.commit()
            raise
        if perf_counter() > timeout:
            timeout = perf_counter() + 1
            await sql.execute(update(Tagging).where(Tagging.id == doc_id).values(
                detail={"processed": indx, "token_count": len(tokens)}))
            yield ServerSentEvent(
                event='processing',
                data=Message(
                    doc_id=doc_id, status=f"{indx * 100 // len(tokens)}").json()
            ).dict()
    await sql.execute(update(Tagging).where(Tagging.id == doc_id).values(
        detail={"processed": len(tokens), "token_count": len(tokens)}))
    yield ServerSentEvent(
        event='processing',
        data=Message(doc_id=doc_id, status='100').json()).dict()
    output = SimpleHTMLFormatter().format(
        tags=(tagger.rules, tagger.tags), tokens=tokens, text_str=text)
    try:
        soup = BeautifulSoup(output, features="lxml")
    except Exception as exp:
        await sql.execute(update(Tagging).where(Tagging.id == doc_id).values(
            state='error', detail={
                "processed": len(tokens),
                "token_count": len(tokens),
                "error": str(exp)}))
        await sql.commit()
        logging.error(output)
        logging.error(exp)
        raise HTTPException(detail="Unparsable tagged text.",
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from exp
    pats = defaultdict(Counter)
    count_patterns(soup, pats)
    patterns = sort_patterns(pats)
    # Update logged data.
    await sql.execute(update(Tagging).where(Tagging.id == doc_id).values(
        state='success',
        detail={
            "processed": len(tokens),
            "token_count": len(tokens),
            "patterns": patterns
        }))
    yield ServerSentEvent(
        data=DocuScopeDocument(
            doc_id=doc_id,
            html_content=generate_tagged_html(soup),
            patterns=patterns,
            word_count=type_count[TokenType.WORD],
            tagging_time=timedelta(seconds=perf_counter() - start_time)
            # pandas.Timedelta(datetime.now()-start_time).isoformat()
        ).json(),
        event='done').dict()


async def tag_document(  # pylint: disable=too-many-locals
        doc_id: UUID,
        request: Request,
        sql: AsyncSession,
        neo: NeoAsyncSession,
        cache: emcache.Client) -> Iterator[ServerSentEvent]:
    """Incrementally tag the given database document."""
    start_time = perf_counter()
    query: Result = await sql.execute(select(Submission.content, Submission.name)
                                      .where(Submission.id == doc_id))
    (doc_content, name) = query.first() or (None, None)
    if doc_content:
        await sql.execute(update(Submission).where(Submission.id == doc_id)
                          .values(state='submitted'))
        await sql.commit()
        if not await request.is_disconnected():
            yield ServerSentEvent(data=Message(doc_id=doc_id, status="0").json(),
                                  event='submitted').dict()
        try:
            if name is not None and name.endswith(".docx"):
                doc_content = docx_to_text(doc_content)
            tokenizer = RegexTokenizer()
            tokens = tokenizer.tokenize(doc_content)
            tagger = DocuscopeTaggerNeo(return_untagged_tags=False, return_no_rules_tags=True,
                                        return_included_tags=True, wordclasses=WORDCLASSES,
                                        session=neo, cache=cache)
            tagger_gen = tagger.tag_next(tokens)
            timeout = start_time + 1  # perf_counter returns seconds.
            while True:
                try:
                    indx = await tagger_gen.asend(None)
                except StopAsyncIteration:
                    break
                if perf_counter() > timeout:
                    timeout = perf_counter() + 1
                    if not await request.is_disconnected():
                        yield ServerSentEvent(
                            event='processing',
                            data=Message(
                                doc_id=doc_id, status=f"{indx * 100 // len(tokens)}").json()
                        ).dict()
            if not await request.is_disconnected():
                yield ServerSentEvent(event='processing',
                                      data=Message(doc_id=doc_id, status='100').json()).dict()
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
                    'tagging_time': str(timedelta(seconds=perf_counter() - start_time))
                }
            ))
            await sql.commit()
            raise HTTPException(detail=f"Tagging error ({exc}).",
                                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from exc
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
                num_included_tokens=sum(type_count[itype]
                                        for itype in not_excluded),
                num_excluded_tokens=sum(
                    type_count[etype] for etype in tokenizer.excluded_token_types),
                tag_chain=[tag.rules[0][0].split(
                    '.')[-1] for tag in tagger.tags],
                tagging_time=timedelta(seconds=perf_counter() - start_time)
            )).dict()
        ))
        await sql.commit()
        if not await request.is_disconnected():
            yield ServerSentEvent(
                event='done',
                data=Message(doc_id=doc_id,
                             status=str(
                                 timedelta(seconds=perf_counter() - start_time))
                             ).json()).dict()
    else:
        await sql.execute(update(Submission).where(Submission.id == doc_id).values(
            state='error',
            processed={
                'error': 'No file data to process.',
                'date_tagged': datetime.now(timezone.utc).astimezone().isoformat(),
                'tagging_time': 0
            }
        ))
        await sql.commit()
        if not await request.is_disconnected():
            yield ServerSentEvent(
                event='error',
                data=Message(doc_id=doc_id,
                             message=f"No content in document: {name}!").json()).dict()


@app.get("/tag/{uuid}", response_model=Union[Message, ServerSentEvent],
         responses={
             status.HTTP_400_BAD_REQUEST: {"descripton": "Bad request", "model": ErrorResponse},
             status.HTTP_404_NOT_FOUND: {
                 "description": "File not found error",
                 "model": ErrorResponse
             },
             status.HTTP_500_INTERNAL_SERVER_ERROR: {
                 "description": "Internal Server Error",
                 "model": ErrorResponse
             },
             status.HTTP_503_SERVICE_UNAVAILABLE: {
                 "description": "Service Unavailable",
                 "model": ErrorResponse
             }})
async def tag_database_document(
        uuid: UUID,
        request: Request,
        sql: AsyncSession = Depends(session),
        neo: NeoAsyncSession = Depends(neo_session)) -> Message | Iterator[ServerSentEvent]:
    """ Check the document status and tag if pending. """
    # check if uuid
    try:
        UUID(f"{uuid}")
    except ValueError as vexc:
        raise HTTPException(detail=f"{vexc}: {uuid}",
                            status_code=status.HTTP_400_BAD_REQUEST) from vexc
    # get current status.
    result: Result = await sql.execute(select(Submission.state).where(Submission.id == uuid))
    (state,) = result.first()
    if state == 'pending':
        # check for too many submitted? Need to find limit emperically.
        tagging = tag_document(uuid, request, sql, neo, CACHE)
        return EventSourceResponse(tagging)
    if state == 'submitted':
        return Message(doc_id=uuid, status=f"{uuid} already submitted.")
    if state == 'tagged':
        return Message(doc_id=uuid, status=f"{uuid} already tagged.")
    if state == 'error':
        raise HTTPException(detail=f"Tagging failed for {uuid}",
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if state is None:
        raise HTTPException(detail="Document unavailable.",
                            status_code=status.HTTP_404_NOT_FOUND)
    raise HTTPException(detail=f"Unknown state: {state} for {uuid}",
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


async def tag_documents(
    request: Request, neo: NeoAsyncSession, cache: emcache.Client
) -> Iterator[ServerSentEvent]:
    """Tag all pending documents in the database."""
    sql: AsyncSession
    while True:  # wait until outstanding processing is done.
        if await request.is_disconnected():
            # If disconnected while waiting for resources, abort.
            logging.info("Client Disconnected!")
            break
        async with SESSION() as sql:
            result: Result = await sql.execute(select(func.count(Submission.id))
                                               .execution_options(populate_existing=True)
                                               .where(Submission.state == 'submitted'))
            (submitted,) = result.first() or (0,)
            # await sql.commit()  # not necessary as no changes are made, but good idea.
            if submitted > 0:
                yield ServerSentEvent(event='pending', data=submitted).dict()
            else:
                break
        await asyncio.sleep(1)  # pause before checking again.
    while True:
        async with SESSION() as sql:
            pending: Result = await sql.execute(
                select(Submission.id).where(Submission.state == 'pending').limit(1))
            (docid,) = pending.first() or (None,)
            if docid:
                logging.info("Tagging %s", docid)
                tag_next = tag_document(docid, request, sql, neo, cache)
                while True:
                    try:
                        if await request.is_disconnected():
                            # continue but do not yield
                            await tag_next.asend(None)
                        else:
                            yield await tag_next.asend(None)
                    except StopAsyncIteration:
                        break
                await sql.commit()
            else:
                break
    if not await request.is_disconnected():
        yield ServerSentEvent(event='done', data="No more pending documents.").dict()


@app.get('/tag', response_model=ServerSentEvent)
async def tag_all_pending_documents(
        request: Request,
        neo: NeoAsyncSession = Depends(neo_session)):
    """Tag all of the pending documents in the database while emitting sse's on progress."""
    return EventSourceResponse(tag_documents(request, neo, CACHE))


class Status(BaseModel):
    """Return type for /status requests. The cound of states of documents."""
    state: Literal['pending', 'submitted', 'tagged',
                   'error', 'abort', 'success', 'processing']
    count: Optional[int]


class StatusState(BaseModel):
    """Return type for /status/{uuid} requestes.  The state of a document."""
    state: Literal['pending', 'submitted', 'tagged',
                   'error', 'abort', 'success', 'processing']


@app.get('/status/tagger', response_model=list[Status])
async def states_online_tagger(sql: AsyncSession = Depends(session)) -> list[Status]:
    """Get status of online tagger."""
    result: Result = await sql.execute(
        select(Tagging.state, func.count(Tagging.state)).group_by(Tagging.state))
    return result.all()


@app.get('/status/documents', response_model=list[Status])
async def states_all_documents(sql: AsyncSession = Depends(session)) -> list[Status]:
    """Get the count of the various states of the documents in the database."""
    result: Result = await sql.execute(select(Submission.state, func.count(Submission.state))
                                       .group_by(Submission.state))
    return result.all()


@app.get('/status/{uuid}', response_model=StatusState,
         responses={
             status.HTTP_404_NOT_FOUND: {
                 "description": "File not found error", "model": ErrorResponse
             }})
async def current_tagging_state(uuid: UUID, sql: AsyncSession = Depends(session)) -> Status:
    """Get the state of the given document."""
    # look in both tables as uuid's are used for both and we do not know a priori which one.
    sub = union_all(
        select(Submission.state).where(Submission.id == uuid),
        select(Tagging.state).where(Tagging.id == uuid)).subquery()
    result: Result = await sql.execute(select(column('state')).select_from(sub))
    state = result.first()
    if state is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"{uuid} not found in database.")
    return state


@app.get('/status', response_model=list[Status])
async def all_tagging_states(sql: AsyncSession = Depends(session)) -> list[Status]:
    """Get the count of the merged states of the documents and tagging events."""
    # result: Result = await sql.execute(text(
    #    """SELECT state, COUNT(state) AS count FROM (
    #        (SELECT state FROM filesystem)
    #         UNION ALL
    #        (SELECT state FROM tagging)) c GROUP BY state;"""))
    sub = union_all(select(Submission.state), select(Tagging.state)).subquery()
    state = column('state')
    query = select(state, func.count(state).label(
        'count')).select_from(sub).group_by(state)
    result: Result = await sql.execute(query)
    return result.all()


app.mount('/static', StaticFiles(directory="app/static", html=True))

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    config = Config()
    config.bind = ["0.0.0.0:8000"]
    config.loglevel = "info"
    asyncio.run(serve(app, config))
