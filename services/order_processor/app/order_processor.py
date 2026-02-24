from fastapi import FastAPI, HTTPException
import aio_pika
import asyncpg
import asyncio
import os
import json
from datetime import datetime
from minio import Minio
from io import BytesIO
import redis.asyncio as aioredis
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger("order-processor")

app = FastAPI()
redis_client = None
minio_client = Minio(os.getenv("MINIO_ENDPOINT", "minio:9000"),
                     access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
                     secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
                     secure=False)

s3_bucket = os.getenv("MINIO_BUCKET", "order-logs")

db_pool = None


async def get_db_pool():
    return await asyncpg.create_pool(host=os.getenv("ORDERS_DB_HOST"),
                                     port=os.getenv("ORDERS_DB_PORT"),
                                     user=os.getenv("ORDERS_DB_USER"),
                                     password=os.getenv("ORDERS_DB_PASSWORD"),
                                     database=os.getenv("ORDERS_DB_NAME"),
                                     min_size=1,
                                     max_size=10)


def save_log_to_s3(order_id: int, message: str):
    try:
        date_str = datetime.now().strftime("%d-%m-%Y")
        filename = f"orders-{date_str}.log"

        existing_content = b""
        try:
            response = minio_client.get_object(s3_bucket, filename)
            existing_content = response.read()
            response.close()
            response.release_conn()
        except:
            logger.debug(f"No existing log file or error reading: {e}")

        log_line = f"[{datetime.now().strftime('%H:%M:%S')}] Order {order_id}: {message}\n"
        new_content = existing_content + log_line.encode('utf-8')

        minio_client.put_object(s3_bucket, filename, BytesIO(new_content), len(new_content))
        logger.info(f"Logged to MinIO: order {order_id} - {message}")
    except Exception as e:
        logger.error(f"S3 upload failed for order {order_id}: {e}")


@app.get("/order/{order_id}")
async def get_order(order_id: int):
    logger.info(f"Request received for order {order_id}")
    cache_key = f"order:{order_id}"
    cached = await redis_client.get(cache_key)
    if cached:
        logger.info(f"Cache hit for order {order_id}")
        return json.loads(cached)

    logger.info(f"Cache miss for order {order_id}, querying database")
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, description FROM orders WHERE id = $1",
            order_id)

    if not row:
        logger.warning(f"Order {order_id} not found in database")
        raise HTTPException(status_code=404, detail="Order not found")

    result = {"id": row['id'],
              "status": row['status'],
              "description": row['description']}

    ttl = int(os.getenv("REDIS_CACHE_TTL", 60))
    await redis_client.setex(cache_key, ttl, json.dumps(result))
    logger.info(f"Cached order {order_id} with TTL {ttl}")
    asyncio.create_task(
        asyncio.to_thread(save_log_to_s3, order_id, f"Status requested - current status: {row['status']}"))

    return result


async def process_message(message: aio_pika.IncomingMessage):
    async with message.process():
        data = json.loads(message.body.decode('utf-8'))
        order_id = data['id']
        description = data['description']
        logger.info(f"Processing message for order {order_id}: {description}")
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO orders (id, status, description) VALUES ($1, 'created', $2)",
                order_id, description)
            logger.info(f"Processing message for order {order_id}: {description}")

        asyncio.create_task(asyncio.to_thread(save_log_to_s3, order_id, f"Order {order_id} created: {description}"))


@app.on_event("startup")
async def startup():
    global redis_client, db_pool
    logger.info("Starting up order-processor...")
    redis_client = aioredis.from_url(
        f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', 6379)}",
        password=os.getenv('REDIS_PASSWORD'),
        decode_responses=True)
    await redis_client.ping()
    logger.info("Redis connection established")
    db_pool = await get_db_pool()
    logger.info("Redis connection established")
    asyncio.create_task(consume_queue())
    logger.info("Startup complete")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Startup complete")
    if redis_client:
        await redis_client.close()
        logger.info("Redis connection closed")
    if db_pool:
        await db_pool.close()
        logger.info("Redis connection closed")


async def consume_queue():
    connection = await aio_pika.connect_robust(
        host=os.getenv("RMQ_HOST", "rabbitmq"),
        login=os.getenv("RMQ_USER", "admin"),
        password=os.getenv("RMQ_PASSWORD", "admin"))
    logger.info("Redis connection closed")

    channel = await connection.channel()
    queue = await channel.declare_queue(
        os.getenv("RABBITMQ_QUEUE", "orders_queue"), durable=True)
    logger.info(f"Consuming from queue: {queue.name}")

    await queue.consume(process_message)
    logger.info("Processor started, waiting for messages...")
    await asyncio.Future()
