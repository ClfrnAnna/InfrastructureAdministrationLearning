from fastapi import FastAPI, Request, Response, HTTPException
import aio_pika
from redis import asyncio as redis
import json
import os
import random
import httpx
import logging
import socket
from pythonjsonlogger import jsonlogger

logger = logging.getLogger()
logger.setLevel(logging.INFO)
log_formatter = jsonlogger.JsonFormatter(
    '%(timestamp)s %(levelname)s %(module)s %(message)s %(hostname)s',
    timestamp=True)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

log_dir = 'log/main'
os.makedirs(log_dir, exist_ok=True)

json_handler = logging.FileHandler('log/main/gateway.log')
json_handler.setFormatter(log_formatter)
logger.addHandler(json_handler)

hostname = socket.gethostname()

processor_url = os.getenv('PROCESSOR_URL')
rmq_queue = os.getenv('RABBITMQ_QUEUE', 'orders_queue')
redis_queue = os.getenv('REDIS_QUEUE', 'my_redis_queue')

r = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=6379,
    password=os.getenv('REDIS_PASSWORD'),
    decode_responses=True)

app = FastAPI()
logger.info("FastAPI gateway started", extra={'hostname': hostname})


@app.get("/")
def read_root():
    return {"message": "Hello, world"}


@app.get("/healthy")
async def healthy(response: Response):
    redis_status = "nok"
    rabbit_status = "nok"
    try:
        await r.ping()
        redis_status = "ok"
    except Exception as e:
        logger.error(f"Redis failed: {e}", extra={'hostname': hostname})

    try:
        conn = await aio_pika.connect_robust(
            f"amqp://{os.getenv('RMQ_USER')}:{os.getenv('RMQ_PASSWORD')}@{os.getenv('RMQ_HOST')}/",
            timeout=5)
        await conn.close()
        rabbit_status = "ok"
    except Exception as e:
        logger.error(f"RabbitMQ failed: {e}", extra={'hostname': hostname})

    if redis_status != "ok" or rabbit_status != "ok":
        response.status_code = 503
    return {"redis": redis_status, "rabbitmq": rabbit_status}


@app.post("/order/create", status_code=201)
async def create_order(request: Request):
    description = (await request.body()).decode('utf-8')
    order_id = random.randint(1, 9999)
    logger.info(f"Creating order {order_id}", extra={'hostname': hostname})

    try:
        connection = await aio_pika.connect_robust(
            f"amqp://{os.getenv('RMQ_USER')}:{os.getenv('RMQ_PASSWORD')}@{os.getenv('RMQ_HOST')}/"
        )
        async with connection:
            channel = await connection.channel()
            await channel.declare_queue(rmq_queue, durable=True)
            await channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps({"id": order_id, "description": description}).encode()),
                routing_key=rmq_queue)
    except Exception as e:
        logger.error(f"RabbitMQ error: {e}", extra={'hostname': hostname})
        raise HTTPException(status_code=503, detail="RabbitMQ unavailable")

    logger.info(f"Order {order_id} created", extra={'hostname': hostname})
    return {"order_id": order_id}


@app.get("/order/{order_id}")
async def get_order(order_id: int):
    logger.info(f"Fetching order {order_id}", extra={'hostname': hostname})
    if not processor_url:
        logger.error("PROCESSOR_URL not configured", extra={'hostname': hostname})
        raise HTTPException(status_code=500, detail="Processor URL not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{processor_url}/order/{order_id}")
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Order not found")
            logger.error(f"Processor error: {e}", extra={'hostname': hostname})
            raise HTTPException(status_code=503, detail="Processor unavailable")
        except Exception as e:
            logger.error(f"Processor unavailable: {e}", extra={'hostname': hostname})
            raise HTTPException(status_code=503, detail="Processor unavailable")
