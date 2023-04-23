class Controller:
    """ Base controller class """
    meta = {'allow_inheritance': True}

    def __init__(self, request):
        self.request = request
        self.request_json = (request.get_json())
