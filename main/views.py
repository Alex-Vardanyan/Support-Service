from . import main
from flask import request
from api.webhook import Webhook


@main.route("/", methods=["GET"])
def index():
    return "<h1>Hi</h1>"

@main.route("/test", methods=["GET"])
def test():
    return """<!-- Start of alexvtest Zendesk Widget script --><script id="ze-snippet" src="https://static.zdassets.com/ekr/snippet.js?key=72313fa3-a590-47dc-a581-6cc2863af775"> </script><!-- End of alexvtest Zendesk Widget script -->"""


@main.route("/zendesk-webhook", methods=["POST"])
def handle_zendesk_webhook():
    print(request)
    return Webhook(request).handle_zendesk_webhook()


@main.route("/app/agent-assign/<token>", methods=["GET"])
def agent_assign(token):
    return Webhook(request).agent_assign()


@main.route("/app/mark-solved/<token>", methods=["GET"])
def mark_solved(token):
    return Webhook(request).mark_solved()
