from fastapi import FastAPI, Request, Response
import pika
import os

app_instance = os.getenv('APP_INSTANCE', '0')
rmq_queue = f"{os.getenv('RABBITMQ_QUEUE_PREFIX', 'my_queue')}_{app_instance}"
app = FastAPI()


def rmq_get_connection():
    return pika.BlockingConnection(pika.ConnectionParameters(host=os.getenv('RABBITMQ_HOST', 'rabbitmq'),
                                                             credentials=pika.PlainCredentials(
                                                                 os.getenv('RABBITMQ_USER', 'admin'),
                                                                 os.getenv('RABBITMQ_PASSWORD', 'admin'))))


@app.get("/")
def read_root():
    return {"message": "Hello, world",
            "app_instance": app_instance,
            "queue": rmq_queue}


@app.get("/healthy")
def healthy(response: Response):
    try:
        connection = rmq_get_connection()
        channel = connection.channel()
        channel.queue_declare(rmq_queue, durable=True, passive=True)
        connection.close()
        rabbit_status = "ok"
    except Exception as e:
        print(f"Health check error: {e}")
        rabbit_status = "nok"

    if rabbit_status != "ok":
        response.status_code = 503
    return {"app": "ok",
            "app_instance": app_instance,
            "queue": rmq_queue,
            "rabbitmq": rabbit_status}


@app.post("/rmq-send")
async def rmq_send_message(request: Request):
    body = await request.body()
    connection = rmq_get_connection()
    channel = connection.channel()
    channel.queue_declare(rmq_queue, durable=True)
    channel.basic_publish(exchange='', routing_key=rmq_queue, body=body)
    connection.close()
    return {"message": "Message sent successfully",
            "app_instance": app_instance,
            "queue": rmq_queue,
            "data": body.decode()}


@app.get("/rmq-get")
def rmq_receive_message():
    connection = rmq_get_connection()
    channel = connection.channel()
    channel.queue_declare(rmq_queue, durable=True)
    messages = []
    max_messages = 1000
    message_count = 0

    queue_info = channel.queue_declare(queue=rmq_queue, durable=True, passive=True)
    total_messages = queue_info.method.message_count

    if total_messages == 0:
        connection.close()
        return f"Queue: {rmq_queue}\nNo messages in queue\n"

    for i in range(min(total_messages, max_messages)):
        method_frame, properties, body = channel.basic_get(queue=rmq_queue, auto_ack=True)

        if method_frame is None or body is None:
            break
        try:
            messages.append({"message_id": method_frame.delivery_tag - 1,
                             "data": body.decode('utf-8'),
                             "redelivered": method_frame.redelivered,
                             "exchange": method_frame.exchange,
                             "routing_key": method_frame.routing_key})
            message_count += 1

        except Exception as e:
            messages.append({"message_id": method_frame.delivery_tag,
                             "data": str(body),
                             "error": f"Decoding error: {str(e)}"})
            message_count += 1

    connection.close()

    return {"app_instance": app_instance,
            "queue": rmq_queue,
            "total_messages_in_queue": total_messages,
            "messages_retrieved": message_count,
            "messages": messages,
            "note": f"Retrieved {message_count} out of {total_messages} messages"
            if message_count < total_messages
            else "All messages retrieved"}


@app.post("/rmq-purge")
def rmq_purge_queue():
    connection = rmq_get_connection()
    channel = connection.channel()
    channel.queue_declare(rmq_queue, durable=True)
    purged_count = channel.queue_purge(queue=rmq_queue)
    connection.close()

    return {"app_instance": app_instance,
            "queue": rmq_queue,
            "action": "purged",
            "messages_removed": purged_count}


@app.get("/queue-info")
def get_queue_info():
    connection = rmq_get_connection()
    channel = connection.channel()

    try:
        queue_info = channel.queue_declare(queue=rmq_queue, durable=True, passive=True)
        message_count = queue_info.method.message_count
        consumer_count = queue_info.method.consumer_count
    except Exception as e:
        message_count = 0
        consumer_count = 0

    connection.close()

    return {"app_instance": app_instance,
            "queue_name": rmq_queue,
            "rabbitmq_host": os.getenv('RABBITMQ_HOST', 'rabbitmq'),
            "message_count": message_count,
            "consumer_count": consumer_count,
            "status": "active" if message_count is not None else "inactive"}
