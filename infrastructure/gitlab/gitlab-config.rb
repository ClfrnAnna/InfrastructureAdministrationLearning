external_url 'http://localhost:8888'
gitlab_rails['gitlab_host'] = 'localhost'
gitlab_rails['gitlab_port'] = 8888
gitlab_rails['gitlab_https'] = false

puma['worker_processes'] = 2
puma['min_threads'] = 1

sidekiq['concurrency'] = 5

prometheus_monitoring['enable'] = false
alertmanager['enable'] = false
node_exporter['enable'] = false
redis_exporter['enable'] = false
postgres_exporter['enable'] = false
gitlab_exporter['enable'] = false

postgresql['shared_buffers'] = "128MB"
postgresql['max_connections'] = 50

redis['maxmemory'] = "200mb"
redis['maxmemory_policy'] = "allkeys-lru"

gitlab_rails['usage_ping_enabled'] = false