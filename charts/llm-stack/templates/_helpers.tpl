{{- define "llm-stack.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Общие лейблы. Ровно Kubernetes-рекомендованные: по ним объекты находят друг друга,
а Prometheus отбирает ServiceMonitor'ы по лейблу release (см. releaseLabel).
*/}}
{{- define "llm-stack.labels" -}}
app.kubernetes.io/name: {{ include "llm-stack.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{/*
Лейбл, по которому Prometheus-operator берёт ServiceMonitor'ы. Совпадает с именем
helm-релиза observability-стека; если он ставился как release "monitoring" — так и
пишут в values.metrics.releaseLabel.
*/}}
{{- define "llm-stack.releaseLabel" -}}
{{- default .Release.Name .Values.metrics.releaseLabel -}}
{{- end -}}

{{/*
Имя образа: репозиторий + тег. Тег обязателен: с :latest не откатиться на предыдущее
состояние одним apply.
*/}}
{{- define "llm-stack.image" -}}
{{- printf "%s:%s" .Values.image.repository (.Values.image.tag | default .Chart.AppVersion) -}}
{{- end -}}
