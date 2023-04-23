from controller import Controller
from celery import Celery
from flask import Response, g
from config import config
import requests
import json
import openai

url = config.get("ZENDESK_URL")
username = config.get("ZENDESK_USERNAME")
password = config.get("ZENDESK_PASSWORD")


def __get_ticket_data(ticket_id):
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

    return sorted([[conversation['id'], conversation["plain_text"], conversation["created_at"]] for
                   conversation in json.loads(response.text)], key=lambda x: x[-1])


def __answer_or_take_action(ticket_id):
    conversation = __get_ticket_data(ticket_id)
    latest_message = conversation[-1][-1]
    if latest_message == "/call_support_agent":  # todo add functionality with Zendesk's conversation api
        pass  # todo find out who's least busy support agents, mongoDB
    else:
        answer = ""
        token = config.get("OPENAI_SECRET_KEY")

        openai_endpoint = "https://api.openai.com/v1/completions"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

        prompt = ""
        for message in conversation:
            prompt += ("AI: " if message[1] == config.get("ASSIGNEE_ID") else "USER: ") + message[1] + '\\n'

        ai_response = requests.post(openai_endpoint, headers=headers, data=json.dumps({"prompt": prompt}))
        answer = json.dumps(ai_response.text)["choices"][0]["message"]

        uri = f"/api/v2/tickets/{ticket_id}.json"
        headers = {'Content-Type': 'application/json'}
        auth = (username, password)
        payload = {"ticket": {'comment': {
            'body': answer,
            "author_id": config.get("ASSIGNEE_ID"),
            'public': True}
        }}
        response = requests.put(url + uri, json=payload, auth=auth, headers=headers)
        if response.status_code == 200:
            return True
        else:
            print(f'Error creating comment: {response.status_code} {response.text}')
            return False


def __assign_to_me(ticket_id):
    uri = f"/api/v2/tickets/{ticket_id}"
    headers = {'Content-Type': 'application/json'}
    auth = (username, password)
    assignee_id = config.get("ASSIGNEE_ID")

    payload = {"ticket": {
        "assignee_id": assignee_id}}
    response = requests.put(url + uri, json=payload, auth=auth, headers=headers)

    if response.status_code == 200:
        return True
    else:
        print(f'Error updating ticket {ticket_id} assignee: {response.status_code}')
        return False


class Webhook(Controller):

    def __init__(self, request):
        super().__init__(request)

    def handle_zendesk_webhook(self):
        contents = self.request_json
        if contents["type"] == "ticket_created":
            pass  # todo create celery job
        if contents["type"] == "ticket_updated":
            if contents['assignee_id'] != config.get("ASSIGNEE_ID") or contents["ticket_status"] == "Solved":
                pass  # todo create celery job
            else:
                pass  # todo create celery job
