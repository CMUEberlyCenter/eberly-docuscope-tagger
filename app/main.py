"""Defines the API for interacting with the DocuScope tagger.

To see the API documents, check /docs on a running instance.

This depends on docuscope-dictionary.
"""
from enum import Enum
import logging
from typing import List
from uuid import UUID
import pkg_resources
import celery
from fastapi import Depends, FastAPI, Path, HTTPException
from pydantic import BaseModel, Json
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response, HTMLResponse, JSONResponse
from starlette.status import HTTP_200_OK, HTTP_201_CREATED,\
    HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR

from db import SESSION
from default_settings import Config
from ds_db import Filesystem, id_exists
import tasks

app = FastAPI( #pylint: disable=C0103
    title="DocuScope Tagger Service",
    description="Uses DocuScope to tag documents in a database.",
    version="2.0.2",
    contact={'email': 'ringenberg@cmu.edu'}, # unused, need to fix fastapi/applications.py
    license={'name': 'CC BY-NC-SA 4.0',
             'url': 'https://creativecommons.org/licenses/by-nc-sa/4.0/'}
)

def get_db(request: Request):
    """Simple method for retrieving the database connection."""
    return request.state.db

class TaskResponse(BaseModel):
    """Schema for task creation responses."""
    task_id: UUID = None
    files: List[UUID] = []

class MessageResponse(BaseModel):
    """Schema for message responses."""
    message: str

class ErrorResponse(BaseModel):
    """Schema for error response."""
    detail: Json

@app.get("/check",
         status_code=HTTP_201_CREATED, response_model=TaskResponse,
         responses={
             HTTP_200_OK: {
                 "model": MessageResponse,
                 "description": "Successful but no new tagging initiated."},
             HTTP_500_INTERNAL_SERVER_ERROR: {
                 "model": ErrorResponse,
                 "description": "Internal Server Error"
             }
         })
def check_for_tagging(session: Session = Depends(get_db)):
    """Check for 'submitted' documents in the database and starts tagging them."""
    processing_check = None
    try:
        processing_check = session.query(Filesystem.id)\
                                  .filter_by(state='submitted').first()
    except Exception as err: #pylint: disable=W0703
        raise HTTPException(detail="{}".format(err),
                            status_code=HTTP_500_INTERNAL_SERVER_ERROR)

    if processing_check:
        logging.warning("At least one unprocessed file exists in the database, aborting (%s)",
                        processing_check[0])
        return JSONResponse(
            content={
                "message":
                "{} is still processing, no new documents staged.".format(processing_check[0])
            },
            status_code=HTTP_200_OK)
    docs = [doc[0] for doc in session.query(Filesystem.id)
            .filter_by(state='pending').limit(Config.TASK_LIMIT)]
    if not docs:
        logging.info("TAGGER: no pending documents.")
        return JSONResponse(
            content={"message": 'No pending documents.'},
            status_code=HTTP_200_OK)
    task_def = celery.group([tasks.tag_entry.s(doc) for doc in docs])
    task = task_def()
    task.save()
    return TaskResponse(task_id=task.id, files=docs)

@app.get("/tag/{doc_id}", status_code=HTTP_201_CREATED,
         response_model=TaskResponse,
         responses={
             HTTP_404_NOT_FOUND: {
                 "model": ErrorResponse,
                 "description": "Document not found in database."
             }
         })
def tag(doc_id: UUID = Path(...,
                            title="Document UUID",
                            description="The UUID of a document in the database."),
        session: Session = Depends(get_db)):
    """Tag the given document in the database identified by a uuid."""
    if not id_exists(session, doc_id):
        logging.error("%s File Not Found %s", HTTP_404_NOT_FOUND, doc_id)
        raise HTTPException(detail="File {} not found.".format(doc_id),
                            status_code=HTTP_404_NOT_FOUND)
    task_def = celery.group([tasks.tag_entry.s(doc_id)])
    task = task_def()
    task.save()
    logging.info("Tagger: GET /tag/%s => task_id: %s", doc_id, task.id)
    return TaskResponse(task_id=task.id, files=[doc_id])

class StatusEnum(str, Enum):
    """Enumeration of possible job status states."""
    unknown = 'UNKNOWN'
    success = 'SUCCESS'
    error = 'ERROR'
    waiting = 'WAITING'

class StatusResponse(BaseModel):
    """Schema for job status response."""
    status: StatusEnum = ...
    message: str = None

@app.get("/status/{job_id}", response_model=StatusResponse,
         responses={
             HTTP_404_NOT_FOUND: {
                 'model': ErrorResponse,
                 'description': 'Job not found error'},
             HTTP_500_INTERNAL_SERVER_ERROR: {
                 'model': ErrorResponse,
                 'description': 'Internal Server Error'
             }
         })
async def get_status(
        job_id: UUID = Path(...,
                            title="Job UUID",
                            description="The UUID of a task as returned by either /check or /tag")):
    """Check the status of the given task."""
    gtask = celery.result.GroupResult.restore(str(job_id))
    status = StatusResponse(status='UNKNOWN')
    if gtask:
        try:
            if gtask.successful():
                status.status = StatusEnum.success
            elif gtask.failed():
                status.status = StatusEnum.error
                status.message = 'A job failed!'
            elif gtask.waiting():
                status.status = StatusEnum.waiting
                status.message = "{}/{}".format(gtask.completed_count(),
                                                len(gtask.results))
        except Exception as err:  #pylint: disable=W0703
            raise HTTPException(detail="{}".format(err),
                                status_code=HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        raise HTTPException(detail="Could not locate job {}".format(job_id),
                            status_code=HTTP_404_NOT_FOUND)
    return status

@app.get("/.*", include_in_schema=False)
async def home():
    """Top level return static index.html"""
    return HTMLResponse(pkg_resources.resource_string(__name__, 'static/index.html'))

@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    """Middleware for http requests to establish database session."""
    response = Response("Internal server error",
                        status_code=HTTP_500_INTERNAL_SERVER_ERROR)
    try:
        request.state.db = SESSION()
        response = await call_next(request)
        request.state.db.commit()
    except Exception as exp: #pylint: disable=W0703
        logging.error(exp)
        request.state.db.rollback()
    finally:
        request.state.db.close()
    return response
