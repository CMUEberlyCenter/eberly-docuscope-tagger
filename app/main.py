""" The online DocuScope tagger interface. """
from datetime import datetime, timezone
import logging
import traceback
from typing import Dict
from uuid import UUID
from difflib import ndiff

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from jsondiff import diff
from neo4j import GraphDatabase
import neo4j
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
#from starlette.middeware.cors import CORSMiddleware
import uvicorn

from default_settings import Config
from ds_tagger import get_wordclasses
from ds_db import Filesystem
from docx_to_text import docx_to_text
from ity.tagger import neo_tagger

ENGINE = create_engine(Config.SQLALCHEMY_DATABASE_URI)
SESSION = sessionmaker(bind=ENGINE)
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

@app.on_event("startup")
async def startup_event():
    """Initialize some important static data on startup.
    Loads the _wordclasses json file for use by tagger.
    Initializes database driver."""
    global DRIVER # pylint: disable=global-statement
    DRIVER = GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.NEO4J_PASS))
    global WORDCLASSES # pylint: disable=global-statement
    WORDCLASSES = get_wordclasses()

@app.on_event("shutdown")
def shutdown_event():
    """Shutdown event handler.  Closes database connection cleanly."""
    if DRIVER is not None:
        DRIVER.close()

def session():
    """Establish a scoped session for accessing the database."""
    my_session: Session = SESSION()
    try:
        yield my_session
        my_session.commit()
    except:
        my_session.rollback()
        raise
    finally:
        my_session.close()
def neo_session():
    """Establish a scoped session for accessing the neo4j database."""
    my_session: neo4j.Session = DRIVER.session()
    try:
        yield my_session
    finally:
        my_session.close()

def tag_document(doc_id: UUID, sql: Session, neo: neo4j.Session) -> None:
    """ Tag the document of the given id. """
    state = "error"
    processed = {'error': 'No file data to process.'}
    start_time = datetime.now()
    (doc_content, name) = sql.query(
        Filesystem.content,
        Filesystem.name).filter(Filesystem.id == doc_id).first()
    if doc_content:
        sql.query(Filesystem).filter(Filesystem.id == doc_id).update(
            {"state": "submitted"}, synchronize_session=False)
        try:
            # convert docx files.
            if name.endswith(".docx"):
                doc_content = docx_to_text(doc_content)
            # Should no longer need as shared prepopulated tagger.
            tagger = neo_tagger(WORDCLASSES, neo)
            processed = tagger.tag(doc_content)
            if processed.get('ds_num_word_tokens', 0) == 0:
                state = 'error'
                processed['error'] = 'Document failed to parse: no word tokens found.'
                logging.error("Invalid parsing results %s: no word tokens.", doc_id)
            else:
                state = "tagged"
                logging.info("Successfully tagged %s", doc_id)
        except Exception as exc: #pylint: disable=W0703
            logging.error("Error while tagging %s", doc_id)
            traceback.print_exc()
            processed['error'] = f'{exc}'
            processed['trace'] = traceback.format_exc()
            state = 'error'
    processed['date_tagged'] = datetime.now(timezone.utc).astimezone().isoformat()
    processed['tagging_time'] = str(datetime.now() - start_time)
    sql.query(Filesystem).filter(Filesystem.id == doc_id).update(
        {"state": state, "processed": processed})
    logging.info("Finished tagging %s (%s)", doc_id, state)


class Message(BaseModel):
    """Model for tag responses."""
    #pylint: disable=too-few-public-methods
    message: str

@app.get("/tag/{uuid}", response_model=Message)
async def tag(uuid: UUID,
              background_tasks: BackgroundTasks,
              sql: Session = Depends(session),
              neo: neo4j.Session = Depends(neo_session)):
    """ Check the document status and start the tagging if appropriate. """
    # check if uuid
    try:
        UUID(uuid)
    except ValueError as vexc:
        raise HTTPException(detail=f"{vexc}: {uuid}",
                            status_code=status.HTTP_400_BAD_REQUEST) from vexc
    # get current status.
    (state,) = sql.query(Filesystem.state).filter(Filesystem.id == uuid).first()
    if state == 'pending':
        # TODO: check for too many submitted
        background_tasks.add_task(tag_document, uuid, sql, neo)
        return {"message": f"Tagging of {uuid} started."}
    if state == 'submitted':
        return {"message": f"{uuid} already submitted."}
    if state == 'tagged':
        return {"message": f"{uuid} already tagged."}
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
                       sql: Session = Depends(session),
                       neo: neo4j.Session = Depends(neo_session)):
    """ Check the document status and start the tagging if appropriate. """
    # check if uuid
    try:
        UUID(f"{uuid}")
    except ValueError as vexc:
        raise HTTPException(detail=f"{vexc}: {uuid}",
                            status_code=status.HTTP_400_BAD_REQUEST) from vexc
    # get current status.
    (state,) = sql.query(Filesystem.state).filter(Filesystem.id == uuid).first()
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

@app.post('/batchtest', response_model=Dict[UUID, CheckResults])
def test_corpus(
        corpus: list[UUID],
        sql: Session = Depends(session),
        neo: neo4j.Session = Depends(neo_session)):
    """Perform tagging check on multiple documents."""
    return {uuid: check_tagging(uuid, sql, neo) for uuid in corpus}

def check_tagging(doc_id: UUID, sql: Session, neo: neo4j.Session) -> CheckResults:
    """Perform tagging with neo4j tagger and check against the database. """
    (doc_content, doc_processed) = sql.query(Filesystem.content,
                                            Filesystem.processed).filter(
                                                Filesystem.id == doc_id).first()
    if doc_content:
        # tag document
        tagger = neo_tagger(WORDCLASSES, neo)
        processed = tagger.tag(docx_to_text(doc_content))
        tag_diff = diff(doc_processed, processed)
        if tag_diff:
            logging.warning("diff: %s", tag_diff)
        if doc_processed['ds_output'] != processed['ds_output']:
            logging.warning(''.join(ndiff(
                "</span>\n".join(
                    doc_processed['ds_output'].split('</span>')).splitlines(keepends=True),
                "</span>\n".join(
                    processed['ds_output'].split("</span>")).splitlines(keepends=True))))
        return {
            "output_check": doc_processed['ds_output'] == processed['ds_output'],
            "token_check": doc_processed['ds_num_tokens'] == processed['ds_num_tokens'],
            "tag_dict_check": len(doc_processed['ds_tag_dict']) - len(processed['ds_tag_dict']),
            #"tag_count": str(diff(doc_processed['ds_count_dict'], processed['ds_count_dict']))
        }
    logging.error("No document content for %s.", doc_id)
    raise HTTPException(detail=f"No document content for {doc_id}.",
                        status_code=status.HTTP_404_NOT_FOUND)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
