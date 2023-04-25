from api.controller import Controller
# from celery import Celery
# from flask import Response, g, current_app
from celery import shared_task
import celery
# from celery._state import current_app
from config import config
import requests
import json
import openai

# todo: for testing purposes .\-/.
url = config.get("ZENDESK_URL") or "https://alexvtest.zendesk.com"
username = config.get("ZENDESK_USERNAME") or "alexandervardanyan1@gmail.com"
password = config.get("ZENDESK_PASSWORD") or "Alevard2001"


class Webhook(Controller):

    def __init__(self, request):
        super().__init__(request)

    def handle_zendesk_webhook(self):
        contents = self.request_json
        if not contents['ticket_id']:
            try:
                if contents["type"] == "ticket_created":
                    print(contents['ticket_id'])  # todo refactor code
                    assigned = celery.current_app.assign.delay(contents['ticket_id'], assignee=None).get()
                    if assigned:
                        celery.current_app.answer_or_take_action.delay(contents['ticket_id']).get()
                if contents["type"] == "ticket_updated":
                    if contents['assignee_id'] != config.get("ASSIGNEE_ID") or contents["ticket_status"] == "Solved":
                        pass
                    else:
                        celery.current_app.answer_or_take_action.delay(contents['ticket_id']).get()
                return "OK", 200
            except Exception as e:
                print(str(e))
                return "something went wrong", 500

    @shared_task(bind=True)
    def get_ticket_data(self, ticket_id):
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

    @shared_task(bind=True)
    def answer_or_take_action(self, ticket_id):
        conversation = celery.current_app.send_task('get_ticket_data', args=[ticket_id])
        latest_message = conversation[-1][-1]
        if latest_message == "/call_support_agent":  # todo add functionality with Zendesk's conversation api
            pass  # todo find out who's least busy support agents + mongoDB preferences
            try:
                ready = celery.current_app.assign.delay(ticket_id=ticket_id, assignee=None).get()
                # todo change to agent's id
            except Exception as e:
                print(str(e))
                return False
            if not ready:
                print(f"Couldn't reassign {ticket_id} ticket")
            return ready
        else:
            token = config.get("OPENAI_SECRET_KEY")
            openai.api_key = token

            messages = []
            for index in range(len(conversation)):
                messages[index] = {
                    "role": "assistant" if conversation[index][1] == config.get("ASSIGNEE_ID") else "user",
                    "content": conversation[index][1]}

            completion = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=messages
            )

            answer = completion.choices[0].message

            uri = f"/api/v2/tickets/{ticket_id}.json"
            headers = {'Content-Type': 'application/json'}
            auth = (username, password)
            payload = {"ticket": {'comment': {
                'body': answer if answer is not None else "this is test response",
                "author_id": config.get("ASSIGNEE_ID"),
                'public': True}
            }}
            response = requests.put(url + uri, json=payload, auth=auth, headers=headers)
            if response.status_code == 200:
                return True
            else:
                print(f'Error creating comment: {response.status_code} {response.text}')
                return False

    @shared_task(bind=True)
    def assign(self, ticket_id, assignee=None):
        uri = f"/api/v2/tickets/{ticket_id}"
        print(url, uri)
        headers = {'Content-Type': 'application/json'}
        auth = (username, password)
        assignee_id = config.get("ASSIGNEE_ID")

        payload = {"ticket": {
            "assignee_id": assignee if assignee is not None else assignee_id}}
        response = requests.put(url + uri, json=payload, auth=auth, headers=headers)

        if response.status_code == 200:
            return True
        else:
            print(f'Error updating ticket {ticket_id} assignee: {response.status_code}')
            return False
