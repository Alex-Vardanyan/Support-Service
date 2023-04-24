from api.controller import Controller
# from celery import Celery
# from flask import Response, g
from celery import shared_task
from config import config
import requests
import json
import openai


class Webhook(Controller):

    url = config.get("ZENDESK_URL")
    username = config.get("ZENDESK_USERNAME")
    password = config.get("ZENDESK_PASSWORD")

    def __init__(self, request):
        super().__init__(request)

    def handle_zendesk_webhook(self):
        contents = self.request_json
        try:
            if contents["type"] == "ticket_created":
                assigned = self.__assign(contents['ticket_id']).delay().get()
                if assigned:
                    self.__answer_or_take_action.delay(contents['ticket_id']).get()
            if contents["type"] == "ticket_updated":
                if contents['assignee_id'] != config.get("ASSIGNEE_ID") or contents["ticket_status"] == "Solved":
                    pass
                else:
                    self.__answer_or_take_action.delay(contents['ticket_id']).get()
        except Exception as e:
            print(str(e))
            return "Something went wrong", 500
        return "OK", 200

    @shared_task(bind=True)
    def __get_ticket_data(self, ticket_id):
        uri = f"/api/v2/tickets/{ticket_id}/comments"
        headers = {
            "Content-Type": "application/json",
        }

        response = requests.request(
            "GET",
            self.url + uri,
            auth=(self.username, self.password),
            headers=headers
        )

        return sorted([[conversation['id'], conversation["plain_text"], conversation["created_at"]] for
                       conversation in json.loads(response.text)], key=lambda x: x[-1])

    @shared_task(bind=True)
    def __answer_or_take_action(self, ticket_id):
        conversation = self.__get_ticket_data(ticket_id)
        latest_message = conversation[-1][-1]
        if latest_message == "/call_support_agent":  # todo add functionality with Zendesk's conversation api
            pass  # todo find out who's least busy support agents, mongoDB
            try:
                ready = self.__assign.delay(ticket_id=ticket_id, assignee=None).get()  # todo change to agent's id
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
            auth = (self.username, self.password)
            payload = {"ticket": {'comment': {
                'body': answer if answer is not None else "this is test response",
                "author_id": config.get("ASSIGNEE_ID"),
                'public': True}
            }}
            response = requests.put(self.url + uri, json=payload, auth=auth, headers=headers)
            if response.status_code == 200:
                return True
            else:
                print(f'Error creating comment: {response.status_code} {response.text}')
                return False

    @shared_task(bind=True)
    def __assign(self, ticket_id, assignee: int | None):
        uri = f"/api/v2/tickets/{ticket_id}"
        headers = {'Content-Type': 'application/json'}
        auth = (self.username, self.password)
        assignee_id = config.get("ASSIGNEE_ID")

        payload = {"ticket": {
            "assignee_id": assignee if assignee is not None else assignee_id}}
        response = requests.put(self.url + uri, json=payload, auth=auth, headers=headers)

        if response.status_code == 200:
            return True
        else:
            print(f'Error updating ticket {ticket_id} assignee: {response.status_code}')
            return False
