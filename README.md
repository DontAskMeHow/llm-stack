# llm-stack

Инфраструктурный слой для небольшого self-hosted контура LLM: шлюз + наблюдаемость на
одном узле k3s, целиком описанные файлами. Два способа применения — helm-чарт или
kustomize-овверлей; содержимое у них одинаковое, выбирается по тому, что уже есть в
кластере.

Слой приложения (сам шлюз) — в отдельном репозитории `home-ai-gateway`: там код,
`Dockerfile` и приёмочный скрипт, здесь — только то, как это живёт на кластере.

## Состав

```
charts/llm-stack/        # helm-чарт
├── Chart.yaml
├── values.yaml          # нейтральные значения + комментарии к каждому полю
├── values-office.yaml   # пример оверлея под другую площадку
├── files/               # JSON дашборда Grafana
└── templates/           # namespace, ConfigMap, Secret, Deployment+PVC, Service,
                         # ServiceMonitor на шлюз и на инференс, HelmChart CR, NOTES
kustomize/               # тот же набор статичными манифестами
scripts/sync.sh          # pull → применить → rollout status → записать ревизию
host/                    # слой вне кластера: релей, задача Планировщика, заметки о доступе
VERSION                  # short SHA последнего применённого состояния
```

## Быстрый старт

```bash
# helm (k3s: helm-контроллер встроен)
helm upgrade --install llm charts/llm-stack \
  -f charts/llm-stack/values.yaml -f charts/llm-stack/values.local.yaml

# или без helm
kubectl apply -k kustomize/

kubectl -n llm rollout status deploy/llm-gateway
curl -s http://<узел>:30080/healthz
```

Образ, собранный локально (`docker build` в `home-ai-gateway`), k3s сам не видит —
он живёт в containerd самого k3s, а не в Docker. После сборки:
`docker save -o /tmp/gw.tar home-ai-gateway:1.0 && k3s ctr images import /tmp/gw.tar`,
иначе под падает в `ErrImagePull`.

Дальше цикл такой: правка в `values.local.yaml` или в шаблонах → `scripts/sync.sh` →
коммит. Ревизия, которая реально применена, лежит в `VERSION`; откат — `git revert` плюс
повторный `sync.sh`.

## Что внутри

**Шлюз** — один Deployment с политикой `Recreate`: база SQLite на `ReadWriteOnce` PVC,
и два пода одновременно только мешают друг другу. Каталог моделей, лимиты и цены —
в ConfigMap, токены — в Secret; под перезапускается по checksum от ConfigMap, чтобы не
помнить про `rollout restart`. Readiness и liveness смотрят на `/healthz`.

**Метрики.** ServiceMonitor на шлюз и на инференс-хосты выбираются по различающему
лейблу `scrape-target`. Это не косметика: `kube-prometheus-stack` вешает `release:
monitoring` на все свои службы, и широкий selector тянет в цели чужие сервисы — они
отвечают 404 на нестандартном пути. Метрики самих инференс-хостов приходят не из пода,
а с адреса узла (реверс-форвард на localhost), поэтому для них заведены Service без
selector плюс Endpoints с явным адресом, и каждый эндпоинт получает лейбл `member`.

**Наблюдаемость** ставится HelmChart CR (`kube-prometheus-stack`) — в k3s это штатный
путь, локальный helm не нужен. Ретеншен Prometheus — 90 дней, Grafana на NodePort,
пароль администрера приходит из оверлея. Дашборд подкладывается ConfigMap'ом с лейблом
`grafana_dashboard=1`, панель одна — и по инференсу, и по нодам, с разбивкой `member`.

**Слой `host/`.** До инференс-эндпоинтов из кластера достучаться нельзя — они в
сети площадки, наружу публикуется только то, что выводит сам хост. Поэтому цепочка
идёт через реверс-форвард с рабочей машины: `host/vm-relay.py` держит три ssh-процесса
(API и метрики инференса, метрики двух нод), `host/register-task.ps1` заводит задачу
Планировщика, чтобы это поднималось при входе. Если машины нет — шлюз честно отдаёт 503,
и в Prometheus это видно как пропавший таргет, а не как «всё хорошо, но пусто».

## Значения и приватное

В `values.yaml` — нейтральные имена (`llm-a.internal`, `llm-node.internal`), цены и
лимиты. Реальные адреса, пароли и токены кладутся в `charts/llm-stack/values.local.yaml`
и в `host/*.local.*`; оба исключены через `.gitignore`. Так репозиторий остаётся
читаемым без контекста, и в нём нет ни одного секрета.

## Проверки

```bash
helm lint charts/llm-stack -f charts/llm-stack/values.yaml
helm template llm charts/llm-stack -f charts/llm-stack/values.yaml | head
kubectl apply -k kustomize/ --dry-run=server
./scripts/sync.sh        # APPLY=0 — только diff
```

Из живого прогона на этой схеме: `up` по всем таргетам, дашборд заполнен (TTFT p99
около 5 с, prefix-cache ≈ 96 %, приём спекулятивного декода ≈ 1.75 токена на драфт),
шлюз отдаёт те же четыре букета токенов, что и прямой запрос к инференс-хосту.
