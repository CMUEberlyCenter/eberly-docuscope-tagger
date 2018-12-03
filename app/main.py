"""Defines the API for interacting with the DocuScope tagger.

This depends on the docuscope-dictionary project.
"""
import logging

#import requests
import celery
from flask_restful import Resource, Api, reqparse, abort

from app import create_flask_app
import tasks
import db

app = create_flask_app()
API = Api(app)
#logging.basicConfig(level=logging.INFO)

#pylint: disable=R0201

class CheckTagging(Resource):
    """Flask RESTful Resource for checking database for files to tag."""
    def get(self):
        """Responds to GET requests."""
        session = app.Session()
        processing_check = session.query(db.Filesystem.id).filter_by(state = '1').first()
        if processing_check:
            session.close()
            logging.warning("TAGGER: at least one unprocess file in database, aborting ({})".format(processing_check[0]))
            return {'message': "{} is still awaiting processing, no new documents staged for tagging".format(processing_check[0])}, 200
        docs = [doc[0] for doc in session.query(db.Filesystem.id).filter_by(state = '0').limit(app.config['TASK_LIMIT'])]
        session.close()
        if not docs:
            logging.warning("TAGGER: no pending documents available.")
            return {'message': 'No pending documents available.'}, 200
        task_def = celery.group([tasks.tag_entry.s(doc) for doc in docs])
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
        return self.parser
    def get(self):
        """Responds to GET calls to tag a database entry."""
        args = self.get_parser().parse_args()
        file_id = args['id'] #TODO: sanitize
        if db.id_exists(app.Session(), file_id):
            tag_tasks = [tasks.tag_entry.s(file_id)]
            task_def = celery.group(tag_tasks)
            task = task_def()
            task.save()
            logging.warning("Tagger: GET /tag?id=%s => task_id: %s", file_id, task.id)
            return {"task_id": task.id, "file": file_id}, 201
        return {"error": "File {} not found".format(file_id)}, 404
    def post(self):
        """Responds to POST calls to tag a database entry."""
        args = self.get_parser().parse_args()
        file_id = args['id'] #TODO: sanitize
        if db.id_exists(app.Session(), file_id):
            tag_tasks = [tasks.tag_entry.s(file_id)]
            task_def = celery.group(tag_tasks)
            task = task_def()
            task.save()
            logging.warning("Tagger: POST /tag/%s => task_id: %s", file_id, task.id)
            return {"task_id": task.id, "file": file_id}, 201
        return {"error": "File {} not found".format(file_id)}, 404

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
    def get_parser(self):
        if not self.parser:
            self.parser = reqparse.RequestParser()
            self.parser.add_argument('task_id', required=True,
                                     help='ID of a tag job.')
        return self.parser
    def post(self):
        """Responds to POST request for the status of a tagging job."""
        args = self.get_parser().parse_args()
        return task_status(args['task_id'])
    def get(self):
        """Responds to GET messages for the status of a tagging job."""
        args = self.get_parser().parse_args()
        return task_status(args['task_id'])
API.add_resource(TagJobStatus, '/tag_status')

@app.route("/")
def home():
    """Base response for this service which simply self identifies."""
    return "DocuScope Tagger Service\n"

if __name__ == '__main__':
    app.run(debug=True)
