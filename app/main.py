"""Defines the API for interacting with the DocuScope tagger.

This depends on the docuscope-dictionary project.
"""
#import base64
#import glob
#import json
import logging
#import os
#import shutil
#import tempfile
#import uuid

import requests
import celery
#from cloudant import couchdb
from flask_restful import Resource, Api, reqparse, abort
#import werkzeug

from app import create_flask_app
import tasks

app = create_flask_app()
API = Api(app)

#pylint: disable=R0201

class CheckTagging(Resource):
    """Flask RESTful Resource for checking database for files to tag."""
    def get(self):
        """Responds to GET requests."""
        req = requests.get("{}/api/db/list/pending".format(app.config['OLI_DOCUMENT_SERVER']))
        docs = req.json()
        if not docs:
            logging.info("TAGGER: no pending documents available.")
            return {'message': 'No pending documents available.'}, 200
        task_def = celery.group([tasks.tag_entry.s(doc['id']) for doc in docs])
        task = task_def()
        task.save()
        return {"task_id": task.id, "files": docs}, 201
API.add_resource(CheckTagging, '/check')

                
class TagEntry(Resource):
    """Flask RESTful Resource for tagging an existing database file."""
    parser = None
    def get_parser(self):
        """Initialize and return the request body parser."""
        if not self.parser:
            self.parser = reqparse.RequestParser()
            self.parser.add_argument(
                'id', required=True,
                help='An id of the file reference in the database.')
            #self.parser.add_argument(
            #    'data', required=False,
            #    help='A base64 encoded string of a docx file.')
            #self.parser.add_argument('dictionary',
            #                         required=False,
            #                         default='default',
            #                         choices=available_dictionaries(),
            #                         help='DocuScope dictionary id.')
        return self.parser
    def get(self):
        """Responds to GET calls to tag a database entry."""
        args = self.get_parser().parse_args() #TODO check if args work.
        #ds_dict = args['dictionary'] or 'default'
        file_id = args['file_id'] #TODO: sanitize
        #TODO check for existance of file_id
        tag_tasks = [tasks.tag_entry.s(file_id)]
        task_def = celery.group(tag_tasks)
        task = task_def()
        task.save()
        logging.info("Tagger: GET /tag/%s => task_id: %s", file_id, task.id)
        return {"task_id": task.id, "file": file_id}, 201
    def post(self):
        """Responds to POST calls to tag a database entry."""
        args = self.get_parser().parse_args()
        #ds_dict = args['dictionary'] or 'default'
        file_id = args['id'] #TODO: sanitize
        #file_id = add_filestring_to_db(args['data'], file_id)
        #TODO check for existance of file_id
        tag_tasks = [tasks.tag_entry.s(file_id)]
        task_def = celery.group(tag_tasks)
        task = task_def()
        task.save()
        logging.info("Tagger: POST /tag/%s => task_id: %s", file_id, task.id)
        return {"task_id": task.id, "file": file_id}, 201

API.add_resource(TagEntry, '/tag')

def task_status(task_id):
    """Get the status of a Celery task."""
    gtask = celery.result.GroupResult.restore(task_id)
    status = {'status': 'UNKNOWN'}
    if gtask:
        try:
            if gtask.successful():
                #gtask.forget()
                status = {'status': 'SUCCESS'}
            elif gtask.failed():
                #gtask.forget()
                status = {'status': 'ERROR', 'message': 'A job failed!'}
            elif gtask.waiting():
                completed = gtask.completed_count()
                total = len(gtask.results)
                status = {'status': 'WAITING',
                          'message': "{}/{}".format(completed, total)}
        except Exception as err:
            abort(500, message="{}".format(err))
    else:
        abort(400, message="Could not locate task {}".format(task_id))
    return status

class TagJobStatus(Resource):
    """Flask Restful Resource for checking on the status of a tagging job."""
    parser = None
    def post(self):
        """Responds to POST request for the status of a tagging job."""
        if not self.parser:
            self.parser = reqparse.RequestParser()
            self.parser.add_argument('task_id', required=True,
                                     help='ID of a tag job.')
        args = self.parser.parse_args()
        return task_status(args['task_id'])
    def get(self):
        """Responds to GET messages for the status of a tagging job."""
        abort(501, message="GET not yet supported.")
API.add_resource(TagJobStatus, '/tag_status')

@app.route("/")
def home():
    """Base response for this service which simply self identifies."""
    return "DocuScope Tagger Service\n"

if __name__ == '__main__':
    app.run(debug=True)
