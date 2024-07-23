import json

import click
import requests

from .storage import Storage

API_URL_BASE = "https://us.sentry.io/api/0"


class Data:
    def __init__(
        self, storage: Storage, org: str, project: str, issues: list[str], limit: int, token: str
    ):
        self.data = None
        self.storage = storage
        self.org = org
        self.project = project
        self.issues = issues
        self.limit = limit
        self.token = token
        self.data = None

    def fetch_data(self) -> None:
        if self.issues:
            data = []
            for issue in self.issues:
                url = f"{API_URL_BASE}/issues/{self.org}/{self.project}/{issue}/events/?full=true&sample=true"
                url = f"{API_URL_BASE}/organizations/{self.org}/issues/{issue}/events/?full=true"

                data += self.fetch_data_from_url(url)
        else:
            url = f"{API_URL_BASE}/projects/{self.org}/{self.project}/events/?full=true&sample=true"
            data = self.fetch_data_from_url(url)
        self.raw_data = data

    def fetch_data_from_url(self, url: str) -> list[dict]:
        data = []
        with click.progressbar(label="Fetching events data", length=self.limit) as bar:
            while len(data) < self.limit:
                headers = {"Authorization": f"Bearer {self.token}"}
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                bar.update(len(response.json()))
                data += (
                    response.json()
                )  # TODO: yield data instead of appending to list, to save memory
                link_next = response.links.get("next")
                if not link_next["results"] == "true":
                    break
                url = link_next["url"]

        click.secho(f"Fetched {len(data)} events", fg="green")
        return data[: self.limit]

    def write_raw_data(self) -> None:
        with click.progressbar(self.raw_data, label="Writing raw events data") as events:
            for event in events:
                with open(self.storage.raw_data_dir / f"{event['id']}.json", "w") as f:
                    json.dump(event, f)

    def read_raw_data(self) -> None:
        with click.progressbar(
            list(self.storage.raw_data_dir.glob("*.json")), label="Reading raw events data"
        ) as json_files:
            self.raw_data = []
            for json_file in json_files:
                with open(json_file) as f:
                    self.raw_data.append(json.load(f))

    def transform_data(self) -> None:
        with click.progressbar(self.raw_data, label="Transforming events data") as events:
            for event in events:
                transformed_event = self.transform_event(event)
                with open(self.storage.inputs_dir / f"{event['id']}.json", "w") as f:
                    json.dump(transformed_event, f)

    @staticmethod
    def transform_event(event: dict) -> dict:

        data = {
            "event_id": event["id"],
        }

        for key in (
            "culprit",
            "environment",
            "platform",
            "logger",
            "release",
            "message",
            "title",
            "type",
        ):
            if key in event:
                data[key] = event[key]

        for entry in event.get("entries", []):
            if entry["type"] == "exception":
                data["exception"] = entry["data"]

        return data
