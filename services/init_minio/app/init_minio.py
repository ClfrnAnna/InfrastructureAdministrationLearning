import os
import sys
import time
from minio import Minio
from minio.error import S3Error


def wait_for_minio(endpoint, access_key, secret_key, secure=False, retries=30, delay=2):
    for i in range(retries):
        try:
            client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
            client.list_buckets()
            print("MinIO is ready!")
            return client
        except Exception as e:
            print(f"Attempt {i + 1}/{retries}: MinIO not ready yet - {e}")
            time.sleep(delay)
    raise Exception(f"Could not connect to MinIO after {retries} attempts")


def main():
    endpoint = os.getenv('MINIO_ENDPOINT', 'minio:9000')
    access_key = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
    secret_key = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
    bucket_name = os.getenv('MINIO_BUCKET', 'order-logs')
    secure = False

    print(f"Connecting to MinIO at {endpoint} ...")
    client = wait_for_minio(endpoint, access_key, secret_key, secure)
    found = False
    try:
        buckets = client.list_buckets()
        for bucket in buckets:
            if bucket.name == bucket_name:
                found = True
                break
    except S3Error as e:
        print(f"Failed to list buckets: {e}")
        sys.exit(1)

    if not found:
        print(f"Creating bucket '{bucket_name}' ...")
        try:
            client.make_bucket(bucket_name)
            print(f"Bucket '{bucket_name}' created.")
        except S3Error as e:
            print(f"Failed to create bucket: {e}")
            sys.exit(1)
    else:
        print(f"Bucket '{bucket_name}' already exists.")

    print("MinIO initialization completed successfully.")


if __name__ == "__main__":
    main()
