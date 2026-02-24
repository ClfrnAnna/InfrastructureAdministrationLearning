#!/bin/sh
set -e

MC_ALIAS="myminio"
MC_HOST="http://${MINIO_ENDPOINT:-minio:9000}"
BUCKET="${MINIO_BUCKET:-order-logs}"

echo "Waiting for MinIO at $MC_HOST ..."
until mc alias set $MC_ALIAS "$MC_HOST" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" 2>/dev/null; do
    echo "MinIO not ready yet, retrying in 2 seconds..."
    sleep 2
done
echo "MinIO is ready."

if mc ls $MC_ALIAS | grep -w "$BUCKET" > /dev/null 2>&1; then
    echo "Bucket '$BUCKET' already exists."
else
    echo "Creating bucket '$BUCKET'..."
    mc mb $MC_ALIAS/"$BUCKET"
    echo "Bucket created."
fi

echo "MinIO initialization completed."