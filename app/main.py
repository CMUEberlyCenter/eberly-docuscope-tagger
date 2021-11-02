""" The online DocuScope tagger interface. """
import logging
import traceback
from uuid import UUID
from difflib import ndiff

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from jsondiff import diff
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
#from starlette.middeware.cors import CORSMiddleware
from starlette.status import (HTTP_400_BAD_REQUEST,
                              HTTP_404_NOT_FOUND,
                              HTTP_500_INTERNAL_SERVER_ERROR,
                              HTTP_503_SERVICE_UNAVAILABLE)

from default_settings import Config
from ds_tagger import create_neo_tagger
from ds_db import Filesystem
from docx_to_text import docx_to_text

ENGINE = create_engine(Config.SQLALCHEMY_DATABASE_URI)
SESSION = sessionmaker(bind=ENGINE)
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

def session():
    """Establish a scoped session for accessing the database."""
    my_session = SESSION()
    try:
        yield my_session
        my_session.commit()
    except:
        my_session.rollback()
        raise
    finally:
        my_session.close()

#TAGGER = create_ds_tagger(Config.DICTIONARY)
#logging.warning("Tagger loaded")

def tag_document(doc_id: UUID, sql: Session):
    """ Tag the document of the given id. """
    doc_state = "error"
    doc_processed = {'error': 'No file data to process.'}
    (doc_content,) = sql.query(Filesystem.content).filter(Filesystem.id == doc_id).first()
    if doc_content:
        sql.query(Filesystem).filter(Filesystem.id == doc_id).update(
            {"state": "submitted"}, synchronize_session=False)
        try:
            doc_processed = TAGGER.tag(docx_to_text(doc_content))
            if doc_processed.get('ds_num_word_tokens', 0) == 0:
                doc_state = 'error'
                doc_processed['error'] = 'Document failed to parse: no word tokens found.'
                logging.error("Invalid parsing results %s: no word tokens.", doc_id)
            else:
                doc_state = "tagged"
                logging.info("Successfully tagged %s", doc_id)
        except Exception as exc: #pylint: disable=W0703
            logging.error("Error while tagging %s", doc_id)
            traceback.print_exc()
            doc_processed['error'] = f'{exc}'
            doc_processed['trace'] = traceback.format_exc()
            doc_state = 'error'
    sql.query(Filesystem).filter(Filesystem.id == doc_id).update(
        {"state": doc_state, "processed": doc_processed})
    logging.info("Finished tagging %s (%s)", doc_id, doc_state)

@app.get("/tag/{uuid}")
async def tag(uuid: UUID,
              background_tasks: BackgroundTasks,
              sql: Session = Depends(session)):
    """ Check the document status and start the tagging if appropriate. """
    # check if uuid
    try:
        UUID(uuid)
    except ValueError as vexc:
        raise HTTPException(detail=f"{vexc}: {uuid}",
                            status_code=HTTP_400_BAD_REQUEST) from vexc
    # get current status.
    (state,) = sql.query(Filesystem.state).filter(Filesystem.id == uuid).first()
    #match (state):
    #    case 'pending':
    if state == 'pending':
        # check for too many submitted
        background_tasks.add_task(tag_document, uuid, sql)
        return {"message": f"Tagging of {uuid} started."}
    #    case 'submitted':
    if state == 'submitted':
        return {"message": f"{uuid} already submitted."}
    #    case 'tagged':
    if state == 'tagged':
        return {"message": f"{uuid} already tagged."}
    #    case 'error':
    if state == 'error':
        raise HTTPException(detail=f"Tagging failed for {uuid}",
                            status_code=HTTP_500_INTERNAL_SERVER_ERROR)
    #    case None:
    if state is None:
        raise HTTPException(detail="Document unavailable.",
                            status_code=HTTP_404_NOT_FOUND)
    #    case _:
    raise HTTPException(detail=f"Unknown state: {state} for {uuid}",
                        status_code=HTTP_503_SERVICE_UNAVAILABLE)

NEO_TAGGER = create_neo_tagger()

@app.get("/test/{uuid}")
async def test_tagging(uuid: UUID,
                       sql: Session = Depends(session)):
    """ Check the document status and start the tagging if appropriate. """
    # check if uuid
    try:
        UUID(f"{uuid}")
    except ValueError as vexc:
        raise HTTPException(detail=f"{vexc}: {uuid}",
                            status_code=HTTP_400_BAD_REQUEST) from vexc
    # get current status.
    (state,) = sql.query(Filesystem.state).filter(Filesystem.id == uuid).first()
    #match (state):
    #    case 'pending':
    #    case 'submitted':
    if state in ['pending', 'submitted']:
        return {"message": f"{uuid} is not yet tagged."}
    #    case 'tagged':
    if state == 'tagged':
        # check for too many submitted
        return check_tagging(uuid, sql)

    #    case 'error':
    if state == 'error':
        raise HTTPException(detail=f"Tagging failed for {uuid}",
                            status_code=HTTP_500_INTERNAL_SERVER_ERROR)
    #    case None:
    if state is None:
        raise HTTPException(detail="Document unavailable.",
                            status_code=HTTP_404_NOT_FOUND)
    #    case _:
    raise HTTPException(detail=f"Unknown state: {state} for {uuid}",
                        status_code=HTTP_503_SERVICE_UNAVAILABLE)

def check_tagging(doc_id: UUID, sql: Session):
    """Perform tagging with neo4j tagger and check against the database. """
    (doc_content, doc_processed) = sql.query(Filesystem.content,
                                            Filesystem.processed).filter(
                                                Filesystem.id == doc_id).first()
    if doc_content:
        # tag document
        processed = NEO_TAGGER.tag(docx_to_text(doc_content))
        tag_diff = diff(doc_processed, processed)
        logging.warning("diff: %s", tag_diff)
        if doc_processed['ds_output'] != processed['ds_output']:
            print(''.join(ndiff("</span>\n".join(doc_processed['ds_output'].split('</span>')).splitlines(keepends=True), "</span>\n".join(processed['ds_output'].split("</span>")).splitlines(keepends=True))), end="")
        return {
            "output_check": doc_processed['ds_output'] == processed['ds_output'],
            #"included_check": doc_processed['ds_num_included_tokens'] == processed['ds_num_included_tokens'],
            "token_check": doc_processed['ds_num_tokens'] == processed['ds_num_tokens'],
            #"word_check": doc_processed['ds_num_word_tokens'] == processed['ds_num_word_tokens'],
            #"exclude_check": doc_processed['ds_num_excluded_tokens'] == processed['ds_num_excluded_tokens'],
            #"punctuation_check": doc_processed['ds_num_punctuation_tokens'] == processed['ds_num_punctuation_tokens'],
            "tag_dict_check": len(doc_processed['ds_tag_dict']) - len(processed['ds_tag_dict']),
            #"tag_count": str(diff(doc_processed['ds_count_dict'], processed['ds_count_dict']))
        }
    logging.error("No document content for %s.", doc_id)
    raise HTTPException(detail=f"No document content for {doc_id}.",
                        status_code=HTTP_404_NOT_FOUND)
