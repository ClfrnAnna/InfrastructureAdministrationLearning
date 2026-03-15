# Infrastructure Administration Learning Project

Этот проект содержит набор микросервисов и инфраструктурных компонентов для изучения администрирования и CI/CD.

## Состав
- **fastapi-app** – основное FastAPI приложение (два экземпляра)
- **order-processor** – обработчик заказов
- **health-checker** – проверка здоровья
- **init-db** – инициализация базы данных
- **init-minio** – инициализация MinIO
- **my-service** – дополнительный сервис
- **fluentd** – сбор логов

## Запуск
Для запуска всех сервисов используйте docker-compose:
```bash
docker network create rabbitmq-network
docker network create app1-network
docker network create app2-network
docker network create postgres-cluster
docker network create logging-network
docker network create cicd-network

docker-compose -f docker-compose-infra.yml up -d
docker-compose -f docker-compose-services.yml up -d
docker-compose -f docker-compose-cicd.yml up -d
or
docker-compose -f docker-compose-infra.yml -f docker-compose-services.yml -f docker-compose-cicd.yml up -d

