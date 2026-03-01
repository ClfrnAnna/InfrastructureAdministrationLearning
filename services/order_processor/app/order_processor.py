from fastapi import FastAPI, HTTPException
import aio_pika
import asyncpg
import asyncio
import os
import json
from datetime import datetime
from minio import Minio
from io import BytesIO

app = FastAPI()

minio_client = Minio(
    os.getenv("MINIO_ENDPOINT", "minio:9000"),
    access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
    secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
    secure=False)

s3_bucket = os.getenv("MINIO_BUCKET", "order-logs")


async def get_db_pool():
    return await asyncpg.create_pool(
        host=os.getenv("ORDERS_DB_HOST"),
        port=os.getenv("ORDERS_DB_PORT"),
        user=os.getenv("ORDERS_DB_USER"),
        password=os.getenv("ORDERS_DB_PASSWORD"),
        database=os.getenv("ORDERS_DB_NAME")
    )


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
            pass

        log_line = f"[{datetime.now().strftime('%H:%M:%S')}] Order {order_id}: {message}\n"
        new_content = existing_content + log_line.encode('utf-8')

        minio_client.put_object(
            s3_bucket, filename, BytesIO(new_content), len(new_content)
        )
    except Exception as e:
        print(f"S3 upload failed: {e}")


@app.get("/order/{order_id}")
async def get_order(order_id: int):
    pool = await get_db_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, status, description FROM orders WHERE id = $1",
            order_id
        )

    await pool.close()

    if not row:
        raise HTTPException(status_code=404, detail="Order not found")

    save_log_to_s3(order_id, f"Status requested - current status: {row['status']}")

    return {
        "id": row['id'],
        "status": row['status'],
        "description": row['description']
    }


async def process_message(message: aio_pika.IncomingMessage):
    async with message.process():
        data = json.loads(message.body.decode('utf-8'))
        order_id = data['id']
        description = data['description']

        pool = await get_db_pool()

        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO orders (id, status, description) VALUES ($1, 'created', $2)",
                order_id, description
            )

        await pool.close()
        save_log_to_s3(order_id, f"Order {order_id} created: {description}")


@app.on_event("startup")
async def startup():
    asyncio.create_task(consume_queue())


async def consume_queue():
    connection = await aio_pika.connect_robust(
        host=os.getenv("RMQ_HOST", "rabbitmq"),
        login=os.getenv("RMQ_USER", "admin"),
        password=os.getenv("RMQ_PASSWORD", "admin")
    )

    channel = await connection.channel()
    queue = await channel.declare_queue(
        os.getenv("RMQ_QUEUE", "orders_queue"), durable=True)

    await queue.consume(process_message)
    print('Processor started, waiting for messages...')
