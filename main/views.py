from . import main
from flask import request
from api.webhook import Webhook


@main.route("/", methods=["GET"])
def index():
    return "<h1>Hi</h1>"


@main.route("/zendesk-webhook", methods=["POST"])
def handle_zendesk_webhook():
    print(request)
    return Webhook(request).handle_zendesk_webhook()
