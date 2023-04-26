import api.webhook
from api.controller import Controller
# from celery import Celery
# from flask import Response, g, current_app
from celery.result import AsyncResult
from celery import shared_task, chain, signature, current_app
import celery
# from celery._state import current_app
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
def answer_or_take_action(conversation, ticket_id):
    print(conversation)
    latest_message = conversation[-1][-1]
    if len(conversation) == 0 or latest_message == "/call_support_agent":  # todo add functionality with Zendesk's conversation api
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
        print("testing testing testing", answer)
        uri = f"/api/v2/tickets/{ticket_id}.json"
        headers = {'Content-Type': 'application/json'}
        auth = (username, password)
        payload = {"ticket": {'comment': {
            'body': answer if answer is not None else "this is test response",
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
                    ticket_id=contents['ticket_id'])) \
                    .apply_async()
                print("done2")
            if contents["type"] == "ticket_updated":
                if contents['assignee_id'] != config.get("ASSIGNEE_ID") or contents["ticket_status"] == "Solved":
                    pass  # todo IDK yet maybe delete some logs in mongo
                # todo just forget about this ticket
                else:
                    chain(get_ticket_data.s(contents['ticket_id']) | answer_or_take_action.s(
                        ticket_id=contents['ticket_id'])) \
                        .apply_async()
            return "OK", 200
        except Exception as e:
            print(str(e))
            return "something went wrong, IDK", 500
