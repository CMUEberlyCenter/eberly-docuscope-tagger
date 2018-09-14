from flask import Flask
from flask_restful import Resource, Api, abort

app = Flask(__name__)
API = Api(app)


if __name__ == '__main__':
    app.run(debug=True)
