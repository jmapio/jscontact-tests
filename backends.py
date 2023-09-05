from dataclasses import dataclass
import pprint
import uuid
from typing import Dict

import requests
from requests.auth import HTTPBasicAuth


class BackendError(Exception):
    def __init__(self, message, json=None):
        super().__init__(message)
        self.json = json


class InvalidCardError(BackendError):
    pass


class CNRBackend:
    def __init__(self, url: str):
        self.url = url

    def to_vcard(self, card: Dict) -> str:
        res = requests.post(
            self.url, json=card, headers={"Content-Type": "application/jscontact+json"}
        )
        if not res.ok:
            if res.status_code == 422:
                raise InvalidCardError(res.text)
            else:
                raise BackendError(f"HTTP {res.status_code}: {res.text}")
        return res.text

    def to_jscard(self, vcard: str) -> Dict:
        res = requests.post(
            self.url,
            data=vcard.encode("utf-8"),
            headers={"Content-Type": "text/vcard;charset=utf-8"},
        )
        if not res.ok:
            raise BackendError(f"HTTP {res.status_code}: {res.text}")
        return res.json()


class CyrusBackend:
    def __init__(self, user: str, pwd: str, host: str):
        self.url = f"http://{host}/jmap"
        self.upload_url = self.url + "/upload/cassandane/"
        self.basicauth = HTTPBasicAuth(user, pwd)

    def call_jmap(self, methods: list):
        req = {
            "using": [
                "urn:ietf:params:jmap:core",
                "urn:ietf:params:jmap:contacts",
                "https://cyrusimap.org/ns/jmap/blob",
                "https://cyrusimap.org/ns/jmap/contacts",
            ],
            "methodCalls": methods,
        }
        try:
            res = requests.post(
                self.url,
                json=req,
                headers={"Content-Type": "application/json"},
                auth=self.basicauth,
            )
        except Exception as e:
            raise BackendError(e)
        if not res.ok:
            raise BackendError(f"HTTP {res.status_code}: {res.text}")
        return res.json()["methodResponses"]

    def to_vcard(self, jscard: Dict) -> str:
        # Create the Card and fetch its vCard blobId
        create_id = str(uuid.uuid4())
        res = self.call_jmap(
            [
                ["ContactCard/set", {"create": {create_id: jscard}}, "0"],
            ]
        )
        try:
            if res[0][1].get("notCreated", False):
                raise InvalidCardError(
                    "Invalid Card", res[0][1]["notCreated"][create_id]
                )
            card_id = res[0][1]["created"][create_id]["id"]
            blob_id = res[0][1]["created"][create_id]["cyrusimap.org:blobId"]
        except (KeyError, TypeError):
            raise BackendError("Unexpected response", res)
        assert card_id
        assert blob_id
        # Download the vCard blob and delete the Card
        res = self.call_jmap(
            [
                ["Blob/get", {"ids": [blob_id], "properties": ["data:asText"]}, "0"],
                ["ContactCard/set", {"destroy": [card_id]}, "1"],
            ]
        )
        data = res[0][1]["list"][0]["data:asText"]
        if not data or not res[1][1]["destroyed"] == [card_id]:
            raise BackendError("Unexpected response", res)
        return data

    def to_jscard(self, vcard: str) -> Dict:
        # Create the vCard blob
        hres = requests.post(
            self.upload_url,
            data=vcard.encode("utf-8"),
            headers={"Content-Type": "text/vcard;charset=utf-8"},
            auth=self.basicauth,
        )
        if not hres.ok or not "blobId" in hres.json():
            raise BackendError(f"HTTP {res.status_code}: {res.text}")
        blob_id = hres.json()["blobId"]
        # Parse the blob to a Card
        res = self.call_jmap(
            [
                [
                    "ContactCard/parse",
                    {"blobIds": [blob_id], "disableUriAsBlobId": True},
                    "0",
                ]
            ]
        )
        if not res[0][1]["parsed"] or not res[0][1]["parsed"][blob_id]:
            raise BackendError("Unexpected response", res)
        return res[0][1]["parsed"][blob_id]
