class Controller:
    """ Base controller class """
    meta = {'allow_inheritance': True}

    def __init__(self, request):
        self.request = request
        try:
            self.request_json = (request.get_json())
        except Exception as e:
            print(str(e))
            self.request_json = None
