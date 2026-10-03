# Доступ к площадке

Три вещи, которые надо знать, чтобы попасть в контур с чистого ноутбука.

## Узел с кластером

- адрес: `vm-node.internal` (в `values.local.yaml` — реальный), SSH-порт 22, пользователь `root`
- пароль — в локальном файле `values.local.yaml` / в менеджере паролей, в git не попадает
- внутри — k3s (`k3s`, `k3s kubectl`), docker как runtime, данных минимум: SQLite шлюза
  и TSDB Prometheus на PVC

Проверка после входа:

```bash
k3s kubectl get nodes
k3s kubectl -n llm get deploy,pods,svc
curl -s http://127.0.0.1:30080/api/health
```

## Инференс-хосты

Доступны только изнутри сети площадки, наружу не публикуются. Поэтому метрики и API
приходят через реверс-форвард с рабочей машины: на узле с кластером поднимаются локальные
порты, на них смотрит шлюз и Prometheus.

| порт на узле | что за ним |
|---|---|
| 8040 | шлюз инференс-парка: API и `/metrics` по пути маршрута |
| 9101 / 9401 | node-exporter и dcgm-exporter head-ноды |
| 9102 / 9402 | то же на worker-ноде |

## Релей

Поднимается на рабочей машине, переживает перезаход за счёт задачи Планировщика:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File host/register-task.ps1
python host/vm-relay.py status
```

Машинная специфика (имена нод, адреса, пароль) лежит в `values.local.yaml` — он в
`.gitignore`. В репозитории остаются только нейтральные имена из `values.yaml`.

## Быстрая диагностика

| симптом | где смотреть |
|---|---|
| Grafana открывает пустые панели | `python host/vm-relay.py status` — жив ли релей; затем `/api/v1/targets` в Prometheus |
| шлюз отдаёт 503 | тот же релей: при выключенной машине это ожидаемо, апстрим не виден |
| Prometheus не видит цели инференса | `k3s kubectl -n llm get servicemonitor,endpoints llm-inference`; путь метрик — `pathPrefix` + `/metrics` |
