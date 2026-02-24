FROM minio/mc:latest

COPY create_bucket.sh /create_bucket.sh
RUN chmod +x /create_bucket.sh

CMD ["/create_bucket.sh"]