from fastapi import FastAPI, Request, Response, HTTPException
import aio_pika
from redis.asyncio import Redis
import json
import os
import random
import httpx

processor_url = os.getenv('PROCESSOR_URL')
rmq_queue = os.getenv('RABBITMQ_QUEUE', 'orders_queue')
redis_queue = os.getenv('REDIS_QUEUE', 'my_redis_queue')

r = Redis(host=os.getenv('REDIS_HOST', 'redis'), port=6379, decode_responses=True)

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Hello, world"}


@app.get("/healthy")
async def healthy(response: Response):
    try:
        await r.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "nok"

    try:
        connection = await aio_pika.connect_robust(
            f"amqp://{os.getenv('RMQ_USER')}:{os.getenv('RMQ_PASSWORD')}@{os.getenv('RMQ_HOST')}/",
            timeout=5
        )
        await connection.close()
        rabbit_status = "ok"
    except Exception:
        rabbit_status = "nok"

    if redis_status != "ok" or rabbit_status != "ok":
        response.status_code = 503

    return {
        "redis": redis_status,
        "rabbitmq": rabbit_status
    }


@app.post("/order/create", status_code=201)
async def create_order(request: Request):
    description = (await request.body()).decode('utf-8')
    order_id = random.randint(1, 9999)

    message = json.dumps({
        "id": order_id,
        "description": description
    })

    try:
        connection = await aio_pika.connect_robust(
            f"amqp://{os.getenv('RMQ_USER')}:{os.getenv('RMQ_PASSWORD')}@{os.getenv('RMQ_HOST')}/"
        )
        async with connection:
            channel = await connection.channel()
            await channel.declare_queue(rmq_queue, durable=True)
            await channel.default_exchange.publish(
                aio_pika.Message(body=message.encode()),
                routing_key=rmq_queue
            )
    except Exception as e:
        raise HTTPException(status_code=503, detail="Message broker unavailable")

    return {"order_id": order_id}


@app.get("/order/{order_id}")
async def get_order(order_id: int):
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{processor_url}/order/{order_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail="Order not found")
            raise HTTPException(status_code=503, detail="Processor unavailable")
        except Exception:
            raise HTTPException(status_code=503, detail="Processor unavailable")
