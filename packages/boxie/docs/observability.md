# Observe Boxie

Use Sanctuary Grafana to inspect API and supervisor requests. Both processes accept an OTLP endpoint through the environment. Their private Prometheus listeners expose separate request, admission and lifecycle metrics. The supervisor emits provisioning outcomes when it observes committed transitions. A request ID can correlate a gateway request with Boxie events.

For dashboard access, traces, retention and email notifications, use the [Sanctuary observability guide](../../../infra/docs/observability.md). Boxie's [metric definitions](../src/boxie/observability/metrics.py) and [event catalog](../src/boxie/observability/events.py) identify the process that produces each signal.
