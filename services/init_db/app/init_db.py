import asyncio
import os
import asyncpg
import sys

SQL_FILE = os.getenv('INIT_SQL_FILE', '/app/init-db.sql')


async def read_sql_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Failed to read SQL file {filepath}: {e}")
        sys.exit(1)


async def wait_for_db(host, port, user, password, database, retries=30, delay=2):
    for i in range(retries):
        try:
            conn = await asyncpg.connect(host=host, port=port, user=user, password=password, database=database)
            await conn.close()
            print(f"Database '{database}' is ready!")
            return
        except Exception as e:
            print(f"Attempt {i + 1}/{retries}: DB not ready yet - {e}")
            await asyncio.sleep(delay)
    raise Exception(f"Could not connect to database '{database}' after {retries} attempts")


async def execute_sql(conn, sql):
    statements = [stmt.strip() for stmt in sql.split(';') if stmt.strip()]
    for stmt in statements:
        try:
            await conn.execute(stmt)
            print(f"Executed: {stmt[:50]}...")
        except Exception as e:
            print(f"Error executing statement: {stmt[:100]}...\n{e}")
            raise


async def main():
    host = os.getenv('ORDERS_DB_HOST', 'haproxy')
    port = os.getenv('ORDERS_DB_PORT', '5432')
    user = os.getenv('ORDERS_DB_USER', 'postgres')
    password = os.getenv('ORDERS_DB_PASSWORD', 'postgres')
    database = os.getenv('ORDERS_DB_NAME', 'orders_db')

    await wait_for_db(host, port, user, password, 'postgres')

    admin_conn = await asyncpg.connect(host=host, port=port, user=user, password=password, database='postgres')
    db_exists = await admin_conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
    if not db_exists:
        print(f"Creating database '{database}'...")
        await admin_conn.execute(f'CREATE DATABASE {database}')
    else:
        print(f"Database '{database}' already exists.")
    await admin_conn.close()

    await wait_for_db(host, port, user, password, database)

    sql = await read_sql_file(SQL_FILE)

    db_conn = await asyncpg.connect(host=host, port=port, user=user, password=password, database=database)
    await execute_sql(db_conn, sql)
    await db_conn.close()
    print("Database initialization completed successfully.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Initialization failed: {e}")
        sys.exit(1)
