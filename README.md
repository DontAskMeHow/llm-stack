# llm-stack

Инфраструктурный слой для self-hosted LLM на одном узле k3s: helm-чарт и равнозначный
набор kustomize. Внутри — деплой шлюза `home-ai-gateway` (Deployment с PVC, ConfigMap,
Secret, Service NodePort), наблюдаемость (kube-prometheus-stack через HelmChart CR,
Grafana с дашбордом) и ServiceMonitor'ы на шлюз и инференс-хосты. Всё разворачивается
из файлов; ревизия, применённая на кластере, лежит в `VERSION`.

## Как применить

```bash
# helm (в k3s helm-контроллер встроен)
helm upgrade --install llm charts/llm-stack \
  -f charts/llm-stack/values.yaml -f charts/llm-stack/values.local.yaml

# или без helm
kubectl apply -k kustomize/
```

Образ шлюза собирается в репозитории `home-ai-gateway`; для k3s его нужно импортировать:
`docker save -o gw.tar home-ai-gateway && k3s ctr images import gw.tar`.
Реальные адреса и токены — в `values.local.yaml` (вне git), публичные значения —
в `values.yaml`.
