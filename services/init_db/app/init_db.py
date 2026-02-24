import asyncio
import os
import asyncpg
import sys


async def create_tables(conn):
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY,
            status VARCHAR(50) NOT NULL,
            description TEXT
        );
    ''')
    print("Table 'orders' ensured.")


async def main():
    host = os.getenv('ORDERS_DB_HOST', 'haproxy')
    port = os.getenv('ORDERS_DB_PORT', '5432')
    user = os.getenv('ORDERS_DB_USER', 'postgres')
    password = os.getenv('ORDERS_DB_PASSWORD', 'postgres')
    database = os.getenv('ORDERS_DB_NAME', 'orders_db')

    admin_conn = await asyncpg.connect(host=host,
                                       port=port,
                                       user=user,
                                       password=password,
                                       database='postgres')

    db_exists = await admin_conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", database)
    if not db_exists:
        print(f"Creating database '{database}'...")
        await admin_conn.execute(f'CREATE DATABASE {database}')
    else:
        print(f"Database '{database}' already exists.")
    await admin_conn.close()

    db_conn = await asyncpg.connect(host=host,
                                    port=port,
                                    user=user,
                                    password=password,
                                    database=database)

    await create_tables(db_conn)
    await db_conn.close()
    print("Database initialization completed successfully.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Initialization failed: {e}")
        sys.exit(1)
