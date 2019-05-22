"""Defines the API for interacting with the DocuScope tagger.

To see the API documents, check /docs on a running instance.

This depends on docuscope-dictionary.
"""
from enum import Enum
import logging
from typing import List
from uuid import UUID
import celery
from fastapi import Depends, FastAPI, Path
from pydantic import BaseModel
#from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response
from starlette.status import HTTP_200_OK, HTTP_201_CREATED,\
    HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR

from db import SESSION
from default_settings import Config
from ds_db import Filesystem, id_exists
import tasks

app = FastAPI()

def get_db(request: Request):
    return request.state.db

class TaskResponse(BaseModel):
    task_id: str = None
    files: List[UUID] = []

@app.get("/check", status_code=HTTP_201_CREATED, response_model=TaskResponse)
def check_for_tagging(session: Session = Depends(get_db)):
    processing_check = None
    try:
        processing_check = session.query(Filesystem.id)\
                                  .filter_by(state='submitted').first()
    except Exception as err:
        return Response("{}".format(err), status_code=HTTP_500_INTERNAL_SERVER_ERROR)

    if processing_check:
        logging.warning("At least one unprocessed file exists in the database, aborting (%s)",
                        processing_check[0])
        return Response("{} is still processing, no new documents staged."
                        .format(processing_check[0]),
                        status_code=HTTP_200_OK)
    docs = [doc[0] for doc in session.query(Filesystem.id)
            .filter_by(state='pending').limit(Config.TASK_LIMIT)]
    if not docs:
        logging.info("TAGGER: no pending documents.")
        return Response('No pending documents.', status_code=HTTP_200_OK)
    task_def = celery.group([tasks.tag_entry.s(doc) for doc in docs])
    task = task_def()
    task.save()
    return TaskResponse(task_id=task.id, files=docs)

@app.get("/tag/{doc_id}", status_code=HTTP_201_CREATED, response_model=TaskResponse)
def tag(doc_id: UUID = Path(...,
                            title="The ID of the document in the database."),
        session: Session = Depends(get_db)):
    if not id_exists(session, doc_id):
        logging.error("%s File Not Found %s", HTTP_404_NOT_FOUND, doc_id)
        return Response("File {} not found.".format(doc_id),
                        status_code=HTTP_404_NOT_FOUND)
    task_def = celery.group([tasks.tag_entry.s(doc_id)])
    task = task_def()
    task.save()
    logging.info("Tagger: GET /tag/%s => task_id: %s", doc_id, task.id)
    return TaskResponse(task_id=task.id, files=[doc_id])

class StatusEnum(str, Enum):
    unknown = 'UNKNOWN'
    success = 'SUCCESS'
    error = 'ERROR'
    waiting = 'WAITING'

class StatusResponse(BaseModel):
    status: StatusEnum = ...
    message: str = None

@app.get("/status/{job_id}", response_model=StatusResponse)
async def get_status(
        job_id: str = Path(...,
                           title="The ID of the task as returned by either /check or /tag")):
    gtask = celery.result.GroupResult.restore(job_id)
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
        except Exception as err:
            return Response("{}".format(err), status_code=HTTP_500_INTERNAL_SERVER_ERROR)
    else:
        return Response("Could not locate job {}".format(job_id),
                        status_code=HTTP_404_NOT_FOUND)
    return status

@app.get("/")
async def home():
    return "DocuScope Tagger Service"

@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    response = Response("Internal server error",
                        status_code=HTTP_500_INTERNAL_SERVER_ERROR)
    try:
        request.state.db = SESSION()
        response = await call_next(request)
        session.commit()
    except:
        request.state.db.rollback()
    finally:
        request.state.db.close()
    return response
