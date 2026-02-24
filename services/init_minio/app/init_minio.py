import os
import sys
from minio import Minio
from minio.error import S3Error


def main():
    endpoint = os.getenv('MINIO_ENDPOINT', 'minio:9000')
    access_key = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
    secret_key = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
    bucket_name = os.getenv('MINIO_BUCKET', 'order-logs')
    secure = False

    print(f"Connecting to MinIO at {endpoint} ...")
    client = Minio(endpoint,
                   access_key=access_key,
                   secret_key=secret_key,
                   secure=secure)

    try:
        buckets = client.list_buckets()
        print("MinIO connection successful.")
    except S3Error as e:
        print(f"MinIO connection failed: {e}")
        sys.exit(1)

    found = False
    for bucket in buckets:
        if bucket.name == bucket_name:
            found = True
            break

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
