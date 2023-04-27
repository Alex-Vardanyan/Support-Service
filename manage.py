import os
from os import path
from app import create_app  # , mongo

app, celery = create_app((os.getenv('FLASK_CONFIG') or 'default'))
app.app_context().push()
app.path = path

if __name__ == "__main__":
    app.run(host="0.0.0.0")
