from flask import Flask, request
# from flask_pymongo import PyMongo
from main import main as main_blueprint
import os
from config import config
from utils import make_celery

# mongo = PyMongo()


def create_app(config_name):
    app = Flask(__name__)
    app.config.from_object(config)
    # mongo.init_app(app)

    celery = make_celery(app)
    celery.set_default()

    app.register_blueprint(main_blueprint)

    return app, celery

