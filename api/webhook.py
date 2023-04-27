from flask import url_for

from api.controller import Controller
from celery import shared_task, chain, signature, current_app
from itsdangerous import URLSafeSerializer, BadData
from config import config
import requests
import json
import openai

url = config.get("ZENDESK_URL")
username = config.get("ZENDESK_USERNAME")
password = config.get("ZENDESK_PASSWORD")


@shared_task()
def assign(ticket_id, assignee=None):
    uri = f"/api/v2/tickets/{ticket_id}"

    headers = {'Content-Type': 'application/json'}
    auth = (username, password)
    assignee_id = config.get("ASSIGNEE_ID")

    payload = {"ticket": {
        "assignee_id": assignee if assignee is not None else assignee_id}}
    response = requests.put(url + uri, json=payload, auth=auth, headers=headers)

    if response.status_code == 200:
        return True
    else:
        print(f'Error updating ticket {ticket_id}: {response.status_code}', response.text)
        return False


@shared_task()
def answer_or_take_action(conversation, ticket_id, via="email"):
    print(conversation, ticket_id, via)
    latest_message = conversation[-1][-1]
    latest_responder = conversation[-1][0]
    if latest_responder == config.get("ASSIGNEE_ID"):
        return None  # so it doesn't reply on its own reply
    if len(conversation) == 0 or latest_message == "/call_support_agent":
        # todo add functionality with Zendesk's conversation api
        # pass  # todo find out who's least busy support agents + mongoDB preferences
        assignee = 14750824466065
        assign.s(ticket_id=ticket_id, assignee=assignee).apply_async()
        return True
    else:
        token = config.get("OPENAI_SECRET_KEY")  # todo change to autogpt trained on 10web's help center
        openai.api_key = token

        messages = []
        for index in range(len(conversation)):
            messages.append({
                "role": "assistant" if conversation[index][1] == config.get("ASSIGNEE_ID") else "user",
                "content": conversation[index][1]})
        print(messages, "testing the messages")
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages
        )

        answer = completion.choices[0].message["content"]

        footer = ""
        if via == "email":
            answer = answer.replace('\n', '<br>')
            answer = "<p>" + answer + "</p>"

            footer = "<p>" + (f"""

Best regards,

Atlas, 10Web's AI Support Companion

You can always connect with Agent

<a href={generate_token(ticket_id, "reassign", "main.agent_assign")} style="background-color: #333; color: white; padding: 10px 20px; border-radius: 20px; text-decoration: none;"><b>Connect me with Support Agent</b></a> 

If your ticket is solved mark it as Solved 

<a href={generate_token(ticket_id, "mark_solved", "main.mark_solved")} style="background-color: #333; color: white; padding: 10px 20px; border-radius: 20px; text-decoration: none;"><b>Mark as Solved</b></a>""").replace('\n', '<br>') + "</p>"

        answer = answer + footer
        print("testing testing testing", answer)

        uri = f"/api/v2/tickets/{ticket_id}.json"
        headers = {'Content-Type': 'application/json'}
        auth = (username, password)
        payload = {"ticket": {'comment': {
            "html_body" if via == "email" else 'body': answer if answer is not None else "this is test response",
            "author_id": config.get("ASSIGNEE_ID"),
            'public': True}
        }}
        response = requests.put(url + uri, json=payload, auth=auth, headers=headers)
        if response.status_code != 200:
            print(f'Error creating comment: {response.status_code} {response.text}')
            return False
        return True


@shared_task()
def get_ticket_data(ticket_id):
    uri = f"/api/v2/tickets/{ticket_id}/comments"
    headers = {
        "Content-Type": "application/json",
    }

    response = requests.request(
        "GET",
        url + uri,
        auth=(username, password),
        headers=headers
    )

    if response.status_code == 200:
        print([[conversation['id'], conversation["body"]] for
               conversation in json.loads(response.text)["comments"]])
        return [[conversation['id'], conversation["body"]] for
                conversation in json.loads(response.text)["comments"]]
    else:
        print(f"Couldn't get ticket data for ticket {ticket_id}", response.text)
        return False


@shared_task()
def mark_as(ticket_id, status):
    uri = f"/api/v2/tickets/{ticket_id}"

    headers = {'Content-Type': 'application/json'}
    auth = (username, password)

    payload = {"ticket": {
        "status": status}}
    response = requests.put(url + uri, json=payload, auth=auth, headers=headers)

    if response.status_code == requests.codes.ok:
        return True
    else:
        print(f'Error setting status for ticket {ticket_id}: {response.status_code}', response.text)
        return False


def generate_token(ticket_id, salt, route):
    s = URLSafeSerializer(config.get("SECRET_KEY"), salt=salt)
    token = s.dumps(ticket_id)
    email_url = url_for(route, token=token, _external=True)
    print("generated")
    return email_url


class Webhook(Controller):

    def __init__(self, request):
        super().__init__(request)

    def handle_zendesk_webhook(self):
        contents = self.request_json
        try:
            if contents["type"] == "ticket_created":
                print("ticket_created")
                assign.s(ticket_id=contents['ticket_id']).apply_async()
                print("done1")
                chain(get_ticket_data.s(ticket_id=contents['ticket_id']) | answer_or_take_action.s(
                    ticket_id=contents['ticket_id'], via=contents["ticket_via"])) \
                    .apply_async()
                print("done2")
            if contents["type"] == "ticket_updated":
                if contents['assignee_id'] != config.get("ASSIGNEE_ID") or contents["ticket_status"] in ["solved", "closed"]:
                    pass  # todo IDK yet maybe delete some logs in mongo
                # todo just forget about this ticket
                else:
                    chain(get_ticket_data.s(contents['ticket_id']) | answer_or_take_action.s(
                        ticket_id=contents['ticket_id'], via=contents["ticket_via"])) \
                        .apply_async()
            return "OK", 200
        except Exception as e:
            print(str(e))
            return "something went wrong, IDK", 500

    def agent_assign(self):
        token = self.request.view_args.get('token')
        s = URLSafeSerializer(config.get("SECRET_KEY"), salt='reassign')

        try:
            ticket_id = s.loads(token)
        except BadData:
            return "Invalid Token", 400

        assign.s(ticket_id=ticket_id, assignee=14750824466065).apply_async()  # todo change it
        return "You'll be contacted with our support agent right away", 200

    def mark_solved(self):
        token = self.request.view_args.get('token')
        s = URLSafeSerializer(config.get("SECRET_KEY"), salt='mark_solved')

        try:
            ticket_id = s.loads(token)
        except BadData:
            return "Invalid Token", 400

        mark_as.s(ticket_id=ticket_id, status="solved").apply_async()  # todo closed?
        return "Thank you, your ticket is now marked as Solved", 200
