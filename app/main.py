""" The online DocuScope tagger interface. """
import cProfile
import logging
import traceback
from datetime import datetime, timezone
from difflib import ndiff
from typing import Counter, Dict
from uuid import UUID

import neo4j
from fastapi import Depends, FastAPI, HTTPException, Request, status
#from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from jsondiff import diff
from neo4j import GraphDatabase
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
#from starlette.middeware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from .default_settings import SETTINGS, SQLALCHEMY_DATABASE_URI
from .docx_to_text import docx_to_text
from .ds_db import Filesystem
from .ds_tagger import get_wordclasses
from .ity.formatters.simple_html_formatter import SimpleHTMLFormatter
from .ity.tagger import ItyTaggerResult, neo_tagger, tag_json
from .ity.taggers.docuscope_tagger_neo import DocuscopeTaggerNeo
from .ity.tokenizers.regex_tokenizer import RegexTokenizer
from .ity.tokenizers.tokenizer import TokenType

ENGINE = create_async_engine(SQLALCHEMY_DATABASE_URI)
SESSION = sessionmaker(bind=ENGINE, expire_on_commit=False, class_=AsyncSession)
DRIVER: neo4j.Driver = None
WORDCLASSES = None
TAGGER = None

app = FastAPI(
    title="DocuScope Tagger",
    description="Run the DocuScope tagger on a document in the database.",
    version="3.1.6",
    license={
        'name': 'CC BY-NC-SA 4.0',
        'url': 'https://creativecommons.org/licenses/by-nc-sa/4.0/'
    })

#app.add_middleware(
#    CORSMiddleware,
#    allow_origins=['*'],
#    allow_credentials=True,
#    allow_methods=['GET', 'POST'],
#    allow_headers=['*'])
#app.add_middleware(HTTPSRedirectMiddleware)
#app.add_middleware(GZipMiddleware)

@app.on_event("startup")
async def startup_event():
    """Initialize some important static data on startup.
    Loads the _wordclasses json file for use by tagger.
    Initializes database driver."""
    global DRIVER, WORDCLASSES # pylint: disable=global-statement
    DRIVER = GraphDatabase.driver(
        SETTINGS.neo4j_uri,
        auth=(SETTINGS.neo4j_user, SETTINGS.neo4j_password.get_secret_value()))
    WORDCLASSES = get_wordclasses()

@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown event handler.  Closes database connection cleanly."""
    if DRIVER is not None:
        DRIVER.close()
    if ENGINE is not None:
        await ENGINE.dispose()

async def session():
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

def neo_session():
    """Establish a scoped session for accessing the neo4j database."""
    my_session: neo4j.Session = DRIVER.session()
    try:
        yield my_session
    finally:
        my_session.close()

class Message(BaseModel):
    """Model for tag responses."""
    #pylint: disable=too-few-public-methods
    message: str
    event: str

async def atag_document(doc_id: UUID, request: Request, sql: AsyncSession, neo: neo4j.Session):
    """"""
    start_time = datetime.now()
    query = await sql.execute(select(Filesystem.content, Filesystem.name).where(Filesystem.id == doc_id))
    (doc_content, name) = query.first()
    if doc_content:
        await sql.execute(update(Filesystem).where(Filesystem.id == doc_id).values(state='submitted'))
        await sql.commit()
        yield Message(event="submitted", message="0")
        try:
            if name.endswith(".docx"):
                doc_content = docx_to_text(doc_content)
            tokenizer = RegexTokenizer()
            tokens = tokenizer.tokenize(doc_content)
            tagger = DocuscopeTaggerNeo(return_untagged_tags=True, return_no_rules_tags=True,
                                        return_included_tags=True, wordclasses=WORDCLASSES, session=neo)
            tagger_gen = tagger.tag_next(tokens)
            tot_tokens = len(tokens)
            tenpc = tot_tokens // 10
            last_indx = 0
            while True:
                if await request.is_disconnected():
                    logging.info("Client Disconnected!")
                    return
                try:
                    indx = next(tagger_gen)
                except StopIteration:
                    break
                if indx - last_indx >= tenpc:
                    last_indx = indx
                    yield Message(event = 'processing', message=f"{indx * 100 // tot_tokens}")
            yield Message(event='processing', message='100')
            output = SimpleHTMLFormatter().format(tags = (tagger.rules, tagger.tags), tokens=tokens, text_str=doc_content)
        except Exception as exc:
            logging.error("Error while tagging %s", doc_id)
            traceback.print_exc()
            await sql.execute(update(Filesystem).where(Filesystem.id == doc_id).values(
                state = 'error',
                processed = {'error': f'{exc}', 'trace': traceback.format_exc(), 'date_tagged': datetime.now(timezone.utc).astimezone().isoformat(), 'tagging_time': 0}
            ))
            raise exc
        type_count = Counter([token.type for token in tokens])
        not_excluded = set(TokenType) - set(tokenizer.excluded_token_types)
        await sql.execute(update(Filesystem).where(Filesystem.id == doc_id).values(
            state = 'tagged',
            processed = tag_json(ItyTaggerResult(
                text_contents=doc_content,
                format_output=output,
                tag_dict=tagger.rules,
                num_tokens=len(tokens),
                num_word_tokens=type_count[TokenType.WORD],
                num_punctuation_tokens=type_count[TokenType.PUNCTUATION],
                num_included_tokens=sum([type_count[itype] for itype in not_excluded]),
                num_excluded_tokens=sum([type_count[etype] for etype in tokenizer.excluded_token_types]),
                tag_chain=[tag.rules[0][0].split('.')[-1] for tag in tagger.tags]
            )).dict()
        ))
        yield Message(event="done", message=str(datetime.now() - start_time))
    else:
        await sql.execute(update(Filesystem).where(Filesystem.id == doc_id).values(
            state = 'error',
            processed = {'error': 'No file data to process.', 'date_tagged': datetime.now(timezone.utc).astimezone().isoformat(), 'tagging_time': 0}
        ))
        yield Message(event="error", message=f"No content in document: {name} ({doc_id})!")


@app.get("/tag/{uuid}", response_model=Message)
async def tag(uuid: UUID,
              request: Request,
              #background_tasks: BackgroundTasks,
              sql: AsyncSession = Depends(session),
              neo: neo4j.Session = Depends(neo_session)):
    """ Check the document status and start the tagging if appropriate. """
    # check if uuid
    try:
        UUID(f"{uuid}")
    except ValueError as vexc:
        raise HTTPException(detail=f"{vexc}: {uuid}",
                            status_code=status.HTTP_400_BAD_REQUEST) from vexc
    # get current status.
    result = await sql.execute(select(Filesystem.state).where(Filesystem.id == uuid))
    (state,) = result.first()
    if state == 'pending':
        # TODO: check for too many submitted
        tagging = atag_document(uuid, request, sql, neo)
        return EventSourceResponse(tagging)
        #background_tasks.add_task(tag_document, uuid, sql, neo)
        #return {"message": f"Tagging of {uuid} started.", "state": state}
    if state == 'submitted':
        return {"message": f"{uuid} already submitted.", "event": 'state'}
    if state == 'tagged':
        return {"message": f"{uuid} already tagged.", "event": 'state'}
    if state == 'error':
        raise HTTPException(detail=f"Tagging failed for {uuid}",
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    if state is None:
        raise HTTPException(detail="Document unavailable.",
                            status_code=status.HTTP_404_NOT_FOUND)
    raise HTTPException(detail=f"Unknown state: {state} for {uuid}",
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

class CheckResults(BaseModel):
    """Model for testing results."""
    #pylint: disable=too-few-public-methods
    output_check: bool
    token_check: bool
    tag_dict_check: int

@app.get("/test/{uuid}", response_model=CheckResults)
async def test_tagging(uuid: UUID,
                       sql: AsyncSession = Depends(session),
                       neo: neo4j.Session = Depends(neo_session)):
    """ Check the document status and start the tagging if appropriate. """
    # check if uuid
    try:
        UUID(f"{uuid}")
    except ValueError as vexc:
        raise HTTPException(detail=f"{vexc}: {uuid}",
                            status_code=status.HTTP_400_BAD_REQUEST) from vexc
    # get current status.
    query = await sql.execute(select(Filesystem.state).where(Filesystem.id == uuid))
    (state,) = query.first()
    if state in ['pending', 'submitted']:
        return {"message": f"{uuid} is not yet tagged."}
    if state == 'tagged':
        # check for too many submitted
        return check_tagging(uuid, sql, neo)

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
        neo: neo4j.Session = Depends(neo_session)):
    """Profile tagging and dump to file."""
    query = await sql.execute(select(Filesystem.content).where(Filesystem.id == uuid))
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
        neo: neo4j.Session = Depends(neo_session)):
    """Perform tagging check on multiple documents."""
    return {uuid: await check_tagging(uuid, sql, neo) for uuid in corpus}

async def check_tagging(doc_id: UUID, sql: AsyncSession, neo: neo4j.Session) -> CheckResults:
    """Perform tagging with neo4j tagger and check against the database. """
    query = await sql.execute(select(Filesystem.content, Filesystem.processed).where(Filesystem.id == doc_id))
    (doc_content, doc_processed) = query.first()
    if doc_content:
        # tag document
        tagger = neo_tagger(WORDCLASSES, neo)
        processed = tagger.tag(docx_to_text(doc_content))
        tag_diff = diff(doc_processed, processed.dict())
        if tag_diff:
            logging.warning("diff: %s", tag_diff)
        if doc_processed['ds_output'] != processed.ds_output:
            logging.warning(''.join(ndiff(
                "</span>\n".join(
                    doc_processed['ds_output'].split('</span>')).splitlines(keepends=True),
                "</span>\n".join(
                    processed.ds_output.split("</span>")).splitlines(keepends=True))))
        return {
            "output_check": doc_processed['ds_output'] == processed.ds_output,
            "token_check": doc_processed['ds_num_tokens'] == processed.ds_num_tokens,
            "tag_dict_check": len(doc_processed['ds_tag_dict']) - len(processed.ds_tag_dict),
            #"tag_count": str(diff(doc_processed['ds_count_dict'], processed['ds_count_dict']))
        }
    logging.error("No document content for %s.", doc_id)
    raise HTTPException(detail=f"No document content for {doc_id}.",
                        status_code=status.HTTP_404_NOT_FOUND)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import asyncio

    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    config = Config()
    config.bind = ["0.0.0.0:8000"]
    config.loglevel = "info"
    asyncio.run(serve(app, config))
