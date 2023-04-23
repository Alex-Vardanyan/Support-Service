from . import main
from flask import request
from ..api.webhook import Webhook

@main.route("/")
def index():
    return "<h1>Hi<h1/>", 200


@main.route("/zendesk-webhook", methods=["POST"])
def handle_zendesk_webhook():
    return Webhook(request).handle_zendesk_webhook()
