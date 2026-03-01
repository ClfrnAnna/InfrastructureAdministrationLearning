import logging
import os
import time
import random
import socket
from pythonjsonlogger import jsonlogger

logger = logging.getLogger()
logger.setLevel(logging.INFO)

log_formatter = jsonlogger.JsonFormatter(
    '%(timestamp)s %(levelname)s %(name)s %(message)s %(hostname)s',
    timestamp=True)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)

log_dir = 'log/my_service'
os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(f'{log_dir}/app.log')
file_handler.setFormatter(log_formatter)
logger.addHandler(file_handler)

hostname = os.getenv('CONTAINER_NAME', socket.gethostname())

if __name__ == '__main__':
    logger.info("My service started", extra={'hostname': hostname})
    messages = [
        "Processing request",
        "Data loaded",
        "Operation completed",
        "User logged in",
        "File saved"
    ]
    levels = [logging.INFO, logging.WARNING, logging.ERROR]
    while True:
        level = random.choice(levels)
        msg = random.choice(messages)
        if level == logging.INFO:
            logger.info(f"INFO: {msg}", extra={'hostname': hostname})
        elif level == logging.WARNING:
            logger.warning(f"WARNING: {msg}", extra={'hostname': hostname})
        else:
            logger.error(f"ERROR: {msg}", extra={'hostname': hostname})
        time.sleep(5)