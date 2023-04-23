from . import main
import json


@main.errorhandler(404)
def page_not_found():
    return json.dumps({"message": "Somethings wrong from your side",
                       "status_code": 400}), 400


@main.errorhandler(500)
def server_error(e):
    print(str(e))
    return json.dumps({"message": "internal server error",
                       "status_code": 500}), 500


@main.errorhandler(Exception)
def server_exception(e):
    print(str(e))
    return json.dumps({"message": "Something's wrong",
                       "status_code": 500}), 500
