from fastapi import FastAPI, Request, Response
import pika
import redis
import json
import os

app_instance = os.getenv('APP_INSTANCE', '0')
rmq_queue = f"{os.getenv('RABBITMQ_QUEUE_PREFIX', 'my_queue')}_{app_instance}"
redis_queue = os.getenv('REDIS_QUEUE', 'my_redis_queue')
r = redis.Redis(host=os.getenv('REDIS_HOST', 'redis'),
                port=6379,
                password=os.getenv('REDIS_PASSWORD', None),
                decode_responses=True)
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
    redis_ok = True
    rabbitmq_ok = True
    try:
        r.ping()
    except:
        redis_ok = False
    try:
        connection = rmq_get_connection()
        connection.close()
    except:
        rabbitmq_ok = False

    if not redis_ok and not rabbitmq_ok:
        response.status_code = 503

    return {"redis": "ok" if redis_ok else "fail",
            "rabbitmq": "ok" if rabbitmq_ok else "fail",
            "status": "degraded" if not redis_ok or not rabbitmq_ok else "healthy"}


@app.post("/send-message")
async def send_message(request: Request):
    message = await request.body()
    message_str = message.decode('utf-8')
    try:
        connection = rmq_get_connection()
        channel = connection.channel()
        channel.queue_declare(rmq_queue, durable=True)
        channel.basic_publish(exchange='', routing_key=rmq_queue, body=message_str)
        connection.close()

        return {"status": "sent",
                "service": "rabbitmq",
                "message": message_str,
                "app_instance": app_instance}
    except Exception as e:
        try:
            r.rpush(redis_queue, message_str)
            return {"status": "sent",
                    "service": "redis",
                    "message": message_str,
                    "note": "Using Redis because RabbitMQ failed",
                    "app_instance": app_instance}

        except Exception as redis_error:
            return {"status": "failed",
                    "error": f"Both services failed: RabbitMQ: {e}, Redis: {redis_error}",
                    "app_instance": app_instance}, 503


@app.get("/get-message")
def get_message():
    try:
        connection = rmq_get_connection()
        channel = connection.channel()
        channel.queue_declare(rmq_queue, durable=True, passive=True)
        method_frame, properties, body = channel.basic_get(queue=rmq_queue, auto_ack=True)
        connection.close()

        if method_frame and body:
            return {"status": "received",
                    "service": "rabbitmq",
                    "message": body.decode('utf-8'),
                    "app_instance": app_instance}

    except:
        pass
    try:
        message = r.lpop(redis_queue)
        if message:
            return {"status": "received",
                    "service": "redis",
                    "message": message,
                    "app_instance": app_instance}
    except:
        pass

    return {"status": "no_messages",
            "app_instance": app_instance}


@app.get("/queue-status")
def queue_status():
    rabbitmq_count = 0
    redis_count = 0
    try:
        connection = rmq_get_connection()
        channel = connection.channel()
        queue_info = channel.queue_declare(queue=rmq_queue, durable=True, passive=True)
        rabbitmq_count = queue_info.method.message_count
        connection.close()
    except:
        rabbitmq_count = -1

    try:
        redis_count = r.llen(redis_queue)
    except:
        redis_count = -1

    return {"app_instance": app_instance,
            "rabbitmq": {"status": "available" if rabbitmq_count >= 0 else "unavailable",
                         "message_count": rabbitmq_count},
            "redis": {"status": "available" if redis_count >= 0 else "unavailable",
                      "message_count": redis_count}}


@app.post("/rmq-send")
async def rmq_send_message(request: Request):
    body = await request.body()
    try:
        connection = rmq_get_connection()
        channel = connection.channel()
        channel.queue_declare(rmq_queue)
        channel.basic_publish(exchange='', routing_key=rmq_queue, body=body)
        connection.close()
        return {"message": "Message sent successfully",
                "app_instance": app_instance,
                "queue": rmq_queue,
                "data": body.decode()}
    except Exception as e:
        return {"error": f"Failed to send: {e}"}, 503


@app.get("/rmq-get")
def rmq_receive_message():
    try:
        connection = rmq_get_connection()
        channel = connection.channel()
        channel.queue_declare(rmq_queue)

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
    except Exception as e:
        return {"error": f"Failed to get messages: {e}"}, 503


@app.post("/redis-send")
async def redis_send(request: Request):
    message = await request.body()
    try:
        await r.rpush(redis_queue, message.decode('utf-8'))
        return {"status": "sent", "message": message.decode('utf-8')}
    except Exception as e:
        return {"error": f"Failed to send: {e}"}, 503


@app.get("/redis-get")
async def redis_get():
    try:
        message = r.lpop(redis_queue)
        return {"message": message if message else 'No messages present'}
    except Exception as e:
        return {"error": f"Failed to get: {e}"}, 503


@app.get("/calculate")
def heavy_calc():
    cached = r.get("calc_result")
    if cached:
        return {"result": json.loads(cached), "from_cache": True}

    result = sum(i ** 2 for i in range(100000000))
    r.setex("calc_result", os.getenv('REDIS_CACHE_TIME', 60), json.dumps(result))
    return {"result": result, "from_cache": False}
