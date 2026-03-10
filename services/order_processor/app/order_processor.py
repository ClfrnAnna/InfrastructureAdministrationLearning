from fastapi import FastAPI, HTTPException
import aio_pika
import asyncpg
import asyncio
import os
import json
from datetime import datetime
from minio import Minio
from io import BytesIO
import redis.asyncio as redis
import logging
import socket
from pythonjsonlogger import jsonlogger
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter
import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)
log_formatter = jsonlogger.JsonFormatter('%(timestamp)s %(levelname)s %(module)s %(message)s %(hostname)s', timestamp=True)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

log_dir = 'log/processor'
os.makedirs(log_dir, exist_ok=True)
json_handler = logging.FileHandler('log/processor/gateway.log')
json_handler.setFormatter(log_formatter)
logger.addHandler(json_handler)

hostname = os.getenv('CONTAINER_NAME', socket.gethostname())

app = FastAPI()

orders_processed_total = Counter('orders_processed_total', 'Total number of processed orders')
orders_by_hour = Counter('orders_by_hour_total', 'Total orders by hour of day', ['hour'])
orders_created_total = Counter('orders_created_total', 'Total number of orders created')
order_views_total = Counter('order_views_total', 'Total number of successful order views')
Instrumentator().instrument(app).expose(app)

minio_client = Minio(
    os.getenv("MINIO_ENDPOINT", "minio:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
    secure=False)
s3_bucket = os.getenv("MINIO_BUCKET", "order-logs")

redis_client = redis.Redis(
    host=os.getenv('REDIS_HOST', 'redis'),
    port=int(os.getenv('REDIS_PORT', 6379)),
    password=os.getenv('REDIS_PASSWORD'),
    decode_responses=True)

DB_HOST = os.getenv("ORDERS_DB_HOST", "haproxy")
DB_WRITE_PORT = int(os.getenv("ORDERS_DB_WRITE_PORT", 5432))
DB_READ_PORT = int(os.getenv("ORDERS_DB_READ_PORT", 5433))
DB_USER = os.getenv("ORDERS_DB_USER", "postgres")
DB_PASSWORD = os.getenv("ORDERS_DB_PASSWORD", "postgres")
DB_NAME = os.getenv("ORDERS_DB_NAME", "orders_db")

write_pool = None
read_pool = None


async def init_db_pools(retries=60, delay=2):
    global write_pool, read_pool
    for i in range(retries):
        try:
            write_pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=DB_WRITE_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                min_size=1,
                max_size=5)
            read_pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=DB_READ_PORT,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                min_size=1,
                max_size=10)
            logger.info("Database pools created (write/read)", extra={'hostname': hostname})
            return
        except Exception as e:
            logger.warning(
                f"DB pools init attempt {i + 1}/{retries} failed: {e}",
                extra={'hostname': hostname})
            await asyncio.sleep(delay)
    raise Exception("Could not create DB pools after multiple attempts")


async def close_db_pools():
    if write_pool:
        await write_pool.close()
    if read_pool:
        await read_pool.close()
    logger.info("Database pools closed", extra={'hostname': hostname})


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
        except Exception:
            pass

        log_line = f"[{datetime.now().strftime('%H:%M:%S')}] Order {order_id}: {message}\n"
        new_content = existing_content + log_line.encode('utf-8')

        minio_client.put_object(s3_bucket, filename, BytesIO(new_content), len(new_content))
    except Exception as e:
        logger.error(f"S3 upload failed: {e}", extra={'hostname': hostname})


@app.get("/order/{order_id}")
async def get_order(order_id: int):
    logger.info(f"Requesting order {order_id} status...", extra={'hostname': hostname})

    cache_key = f"order:{order_id}:data"
    cached = await redis_client.get(cache_key)
    if cached:
        logger.info(f"Cache hit for order {order_id}", extra={'hostname': hostname})
        order_views_total.inc()
        return json.loads(cached)

    async with read_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, description FROM orders WHERE id = $1",
            order_id)

    if not row:
        logger.error(f"Order {order_id} not found", extra={'hostname': hostname})
        raise HTTPException(status_code=404, detail="Order not found")

    result = {
        "id": row['id'],
        "status": row['status'],
        "description": row['description']}

    await redis_client.setex(cache_key, int(os.getenv("REDIS_CACHE_TTL", 60)), json.dumps(result))

    save_log_to_s3(order_id, f"Status requested - current status: {row['status']}")

    logger.info(f"Order {order_id} status retrieved", extra={'hostname': hostname})
    order_views_total.inc()
    return result


async def process_message(message: aio_pika.IncomingMessage):
    logger.info("Message received, processing...", extra={'hostname': hostname})
    async with message.process():
        data = json.loads(message.body.decode('utf-8'))
        order_id = data['id']
        description = data['description']

        async with write_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO orders (id, status, description) VALUES ($1, 'created', $2)",
                order_id, description)
        cache_key = f"order:{order_id}:data"
        await redis_client.setex(cache_key, int(os.getenv("REDIS_CACHE_TTL", 60)), json.dumps({
            "id": order_id,
            "status": "created",
            "description": description}))

        save_log_to_s3(order_id, f"Order created: {description}")

        orders_processed_total.inc()
        orders_created_total.inc()

        logger.info(f"Order {order_id} created: {description}", extra={'hostname': hostname})
        current_hour = str(datetime.datetime.now().hour)
        orders_by_hour.labels(hour=current_hour).inc()


async def consume_queue(retries=30, delay=2):
    for i in range(retries):
        try:
            connection = await aio_pika.connect_robust(
                f"amqp://{os.getenv('RMQ_USER')}:{os.getenv('RMQ_PASSWORD')}@{os.getenv('RMQ_HOST')}/")
            channel = await connection.channel()
            queue = await channel.declare_queue(
                os.getenv("RMQ_QUEUE", "orders_queue"), durable=True)
            await queue.consume(process_message)
            logger.info("Connected to RabbitMQ, waiting for messages...", extra={'hostname': hostname})
            return
        except Exception as e:
            logger.warning(
                f"RabbitMQ connection attempt {i + 1}/{retries} failed: {e}",
                extra={'hostname': hostname})
            await asyncio.sleep(delay)
    raise Exception("Could not connect to RabbitMQ after multiple attempts")


@app.on_event("startup")
async def startup():
    await init_db_pools()
    asyncio.create_task(consume_queue())


@app.on_event("shutdown")
async def shutdown():
    await close_db_pools()
    await redis_client.close()


@app.get("/healthy")
async def healthy():
    status = {"redis": "ok", "postgres_write": "ok", "postgres_read": "ok", "minio": "ok"}

    try:
        await redis_client.ping()
    except Exception:
        status["redis"] = "nok"

    try:
        async with write_pool.acquire() as conn:
            await conn.execute("SELECT 1")
    except Exception:
        status["postgres_write"] = "nok"

    try:
        async with read_pool.acquire() as conn:
            await conn.execute("SELECT 1")
    except Exception:
        status["postgres_read"] = "nok"

    try:
        minio_client.list_buckets()
    except Exception:
        status["minio"] = "nok"

    return status