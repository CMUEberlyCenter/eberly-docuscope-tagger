from app import create_flask_app
from flask_restful import Resource, Api, reqparse, abort
import werkzeug
import shutil
import tempfile
import os
import tasks
import base64
import glob
import celery

app = create_flask_app()
API = Api(app)

def allowed_file(filename):
    allowed = [ext for _, extensions, _ in shutil.get_unpack_formats() for ext in extensions]
    return any(filename.endswith(ext) for ext in allowed)

class TagArchive(Resource):
    def post(self):
        parse = reqparse.RequestParser()
        parse.add_argument('file', type=werkzeug.datastructures.FileStorage, location='files')
        args = parse.parse_args()
        afile = args['file']
        if not afile or afile.filename == '':
            abort(401, message='No file selected')
        if afile and allowed_file(afile.filename):
            with tempfile.TemporaryDirectory() as upload_folder, \
                 tempfile.NamedTemporaryFile(suffix=afile.filename) as archive:
                afile.save(archive)
                shutil.unpack_archive(archive.name, upload_folder)
                tag_tasks = []
                for f in glob.iglob(os.path.join(upload_folder, "**/*.docx"), recursive=True):
                    with open(f, 'rb') as bf:
                        data = str(base64.encodebytes(bf.read()), encoding='utf-8')
                        tag_tasks.append(tasks.tag_document.s(os.path.basename(f), data))
                task_def = celery.group(tag_tasks)
                task = task_def()
                task.save()
        return 'Ok'

API.add_resource(TagArchive, '/tag_archive')

@app.route("/")
def home():
    return "DocuScope Tagger Service\n"

if __name__ == '__main__':
    app.run(debug=True)
