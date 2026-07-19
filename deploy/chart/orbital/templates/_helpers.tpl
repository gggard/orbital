{{- define "orbital.fullname" -}}
{{- printf "%s" .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "orbital.labels" -}}
app.kubernetes.io/name: orbital
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "orbital.controlPlaneName" -}}
{{ include "orbital.fullname" . }}-control-plane
{{- end -}}

{{- define "orbital.consoleName" -}}
{{ include "orbital.fullname" . }}-console
{{- end -}}

{{- define "orbital.pythonVersionsJson" -}}
{{- $d := dict -}}
{{- range .Values.baseImages.pythonVersions -}}
{{- $_ := set $d . (printf "streamlit-base:py%s" .) -}}
{{- end -}}
{{- $d | toJson -}}
{{- end -}}

{{- define "orbital.authSecretName" -}}
{{- if .Values.auth.console.existingSecret -}}
{{ .Values.auth.console.existingSecret }}
{{- else -}}
{{ include "orbital.fullname" . }}-auth
{{- end -}}
{{- end -}}
