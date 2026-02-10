from fastapi import FastAPI, Request, Response
import pika
import os

rmq_queue = os.getenv('RABBITMQ_QUEUE', 'my_queue')
app = FastAPI()


def rmq_get_connection():
    return pika.BlockingConnection(pika.ConnectionParameters(
        host=os.getenv('RABBITMQ_HOST', 'rabbitmq'),
        credentials=pika.PlainCredentials(
            os.getenv('RABBITMQ_USER', 'admin'),
            os.getenv('RABBITMQ_PASSWORD', 'admin')
        )
    ))


@app.get("/")
def read_root():
    return {"message": "Hello, world"}


@app.get("/healthy")
def healthy(response: Response):
    try:
        connection = rmq_get_connection()
        connection.close()
        rabbit_status = "ok"
    except:
        rabbit_status = "nok"

    if rabbit_status != "ok":
        response.status_code = 503
    return {
        "app": "ok",
        "rabbitmq": rabbit_status
    }


@app.post("/rmq-send")
async def rmq_send_message(request: Request):
    body = await request.body()
    connection = rmq_get_connection()
    channel = connection.channel()
    channel.queue_declare(rmq_queue, durable=True)
    channel.basic_publish(exchange='', routing_key=rmq_queue, body=body)
    connection.close()
    return {"yoo, check what I've just sent": body.decode()}


@app.get("/rmq-get")
def rmq_receive_message():
    connection = rmq_get_connection()
    channel = connection.channel()
    channel.queue_declare(rmq_queue, durable=True)
    method, properties, body = channel.basic_get(queue=rmq_queue, auto_ack=True)
    connection.close()
    return {
        "damn, dats what I've just received": body.decode() if body else 'hah actually no message found in the queue'}
