{{- define "sh.fullname" -}}
{{- printf "%s" .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}

{{- define "sh.labels" -}}
app.kubernetes.io/name: streamlit-host
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "sh.controlPlaneName" -}}
{{ include "sh.fullname" . }}-control-plane
{{- end -}}

{{- define "sh.consoleName" -}}
{{ include "sh.fullname" . }}-console
{{- end -}}

{{- define "sh.pythonVersionsJson" -}}
{{- $d := dict -}}
{{- range .Values.baseImages.pythonVersions -}}
{{- $_ := set $d . (printf "streamlit-base:py%s" .) -}}
{{- end -}}
{{- $d | toJson -}}
{{- end -}}

{{- define "sh.authSecretName" -}}
{{- if .Values.auth.console.existingSecret -}}
{{ .Values.auth.console.existingSecret }}
{{- else -}}
{{ include "sh.fullname" . }}-auth
{{- end -}}
{{- end -}}
