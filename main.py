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
    method, properties, body = channel.basic_get(queue=rmq_queue, auto_ack=True)
    connection.close()
    if body:
        return {"message": "Message received",
                "app_instance": app_instance,
                "queue": rmq_queue,
                "data": body.decode()}
    else:
        return {"message": "No messages in queue",
                "app_instance": app_instance,
                "queue": rmq_queue}


@app.get("/queue-info")
def get_queue_info():
    return {"app_instance": app_instance,
            "queue_name": rmq_queue,
            "rabbitmq_host": os.getenv('RABBITMQ_HOST', 'rabbitmq')}
