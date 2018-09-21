"""Defines the API for interacting with the DocuScope tagger.

This depends on the docuscope-dictionary project.
"""
import base64
import glob
from functools import lru_cache
import json
import os
import shutil
import tempfile
import urllib3

import celery
from flask_restful import Resource, Api, reqparse, abort
import werkzeug

from app import create_flask_app
import tasks

app = create_flask_app()
API = Api(app)
HTTP = urllib3.PoolManager()

#pylint: disable=R0201

def allowed_file(filename):
    """Test a given file name to see if the archive extention is supported.

    Arguments:
    filename: (String) the name of an archive file.

    Returns:
    (Boolean) True if the archive extention is supported by shutil.
    """
    allowed = [ext for _, extensions, _ in shutil.get_unpack_formats() for ext in extensions]
    return any(filename.endswith(ext) for ext in allowed)

@lru_cache(maxsize=1)
def available_dictionaries():
    """Retrieve the list of available DocuScope dictionaries."""
    req = HTTP.request('GET',
                       "{}dictionary".format(app.config['DICTIONARY_SERVER']))
    return json.loads(req.data.decode('utf-8'))

class TagArchive(Resource):
    """Flask Restful Resource for handling /tag_archive which tags all of the
    docx files in an archive file."""
    parser = None

    def post(self):
        """Handles post requests for tagging all of the files in an archive.
        Post Arguments: (in the POST request)
        - file: an archive file

        Returns:
        - 403: if there is no file
        - 'OK': on successful upload.
        """
        if not self.parser:
            self.parser = reqparse.RequestParser()
            self.parser.add_argument('file',
                                     type=werkzeug.datastructures.FileStorage,
                                     location='files', required=True,
                                     help='An archive of docx files.')
            self.parser.add_argument('dictionary',
                                     required=False,
                                     default='default',
                                     choices=available_dictionaries(),
                                     help='DocuScope dictionary id.')
        args = self.parser.parse_args()
        afile = args['file']
        ds_dict = args['dictionary'] or 'default'
        if not afile or afile.filename == '':
            abort(400, message='No file selected')
        if allowed_file(afile.filename):
            task = None
            with tempfile.TemporaryDirectory() as upload_folder, \
                 tempfile.NamedTemporaryFile(suffix=afile.filename) as archive:
                afile.save(archive)
                shutil.unpack_archive(archive.name, upload_folder)
                tag_tasks = []
                for docx in glob.iglob(os.path.join(upload_folder, "**/*.docx"), recursive=True):
                    with open(docx, 'rb') as binf:
                        data = str(base64.encodebytes(binf.read()), encoding='utf-8')
                        tag_tasks.append(tasks.tag_document.s(os.path.basename(docx), data, ds_dict))
                task_def = celery.group(tag_tasks)
                task = task_def()
                task.save()
            if task:
                return {"task_id": task.id, "zipfile": afile.filename}
        else:
            abort(400, message="Unsupported archive format")

API.add_resource(TagArchive, '/tag_archive')

def task_status(task_id):
    """Get the status of a Celery task."""
    gtask = celery.result.GroupResult.restore(task_id)
    status = {'status': 'UNKNOWN'}
    if gtask:
        try:
            if (gtask.successful()):
                #gtask.forget()
                status = {'status': 'SUCCESS'}
            elif (gtask.failed()):
                #gtask.forget()
                status = {'status': 'ERROR', 'message': 'A job failed!'}
            elif (gtask.waiting()):
                completed = gtask.completed_count()
                total = len(gtask.results)
                status = {'status': 'WAITING',
                          'message': "{}/{}".format(completed, total)}
        except Exception as err:
            abort(500, message="{}".format(err))
    else:
        abort(400, message="Could not locate task {}".format(task_id))
    return status

class TagArchiveStatus(Resource):
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
API.add_resource(TagArchiveStatus, '/tag_status')

@app.route("/")
def home():
    """Base response for this service which simply self identifies."""
    return "DocuScope Tagger Service\n"

if __name__ == '__main__':
    app.run(debug=True)
