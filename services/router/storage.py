"""Swappable storage layer.

This is the single file you change to migrate between clouds.
Select a backend with the STORAGE_BACKEND env var:

    memory        - in-process dict, no cloud needed (good for local tests)
    cloudstorage  - GCP Cloud Storage bucket  (GCS_BUCKET)
    firestore     - GCP Firestore collection  (FIRESTORE_COLLECTION)
    s3            - AWS S3 bucket              (S3_BUCKET)         [migration]
    dynamodb      - AWS DynamoDB table         (DYNAMODB_TABLE)    [migration]

The rest of the application never imports a cloud SDK directly, so swapping
GCP for AWS is a config change plus this one module.
"""
import json
import os


class StorageBackend:
    def save(self, ticket_id: str, record: dict) -> dict:
        raise NotImplementedError


class MemoryBackend(StorageBackend):
    def __init__(self):
        self._data = {}

    def save(self, ticket_id, record):
        self._data[ticket_id] = record
        return {"backend": "memory", "id": ticket_id}


class CloudStorageBackend(StorageBackend):
    def __init__(self, bucket: str):
        from google.cloud import storage
        self._bucket_name = bucket
        self._bucket = storage.Client().bucket(bucket)

    def save(self, ticket_id, record):
        path = f"tickets/{ticket_id}.json"
        self._bucket.blob(path).upload_from_string(
            json.dumps(record), content_type="application/json")
        return {"backend": "cloudstorage", "bucket": self._bucket_name, "path": path}


class FirestoreBackend(StorageBackend):
    def __init__(self, collection: str):
        from google.cloud import firestore
        self._collection = collection
        self._db = firestore.Client()

    def save(self, ticket_id, record):
        self._db.collection(self._collection).document(ticket_id).set(record)
        return {"backend": "firestore", "collection": self._collection, "id": ticket_id}


class S3Backend(StorageBackend):
    """AWS equivalent of CloudStorageBackend (used after migration)."""
    def __init__(self, bucket: str):
        import boto3
        self._bucket = bucket
        self._client = boto3.client("s3")

    def save(self, ticket_id, record):
        key = f"tickets/{ticket_id}.json"
        self._client.put_object(Bucket=self._bucket, Key=key,
                                Body=json.dumps(record).encode("utf-8"),
                                ContentType="application/json")
        return {"backend": "s3", "bucket": self._bucket, "path": key}


class DynamoDBBackend(StorageBackend):
    """AWS equivalent of FirestoreBackend (used after migration)."""
    def __init__(self, table: str):
        import boto3
        self._table = boto3.resource("dynamodb").Table(table)

    def save(self, ticket_id, record):
        self._table.put_item(Item={**record, "ticket_id": ticket_id})
        return {"backend": "dynamodb", "table": self._table.name, "id": ticket_id}


def get_backend() -> StorageBackend:
    backend = os.getenv("STORAGE_BACKEND", "memory").lower()
    if backend == "cloudstorage":
        return CloudStorageBackend(os.getenv("GCS_BUCKET", "tickets-poc"))
    if backend == "firestore":
        return FirestoreBackend(os.getenv("FIRESTORE_COLLECTION", "tickets"))
    if backend == "s3":
        return S3Backend(os.getenv("S3_BUCKET", "tickets-poc"))
    if backend == "dynamodb":
        return DynamoDBBackend(os.getenv("DYNAMODB_TABLE", "tickets"))
    return MemoryBackend()
