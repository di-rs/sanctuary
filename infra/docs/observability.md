# Observe Sanctuary

Sign into the Grafana hostname using your Cloudflare Access email PIN. Grafana also verifies the assertion signature, your email, issuer and application audience. Open the Temporal UI hostname through its own Access application to inspect workflow progress. The tunnel connects directly to the two private services.

## Search across services

Grafana Explore provides **Metrics**, **Traces** and **Logs** data sources. Start with the service name `playground`, `playground-preview`, `boxie-api` or `boxie-supervisor`. Use the trace ID for a request across instrumented HTTP calls. Application events also carry a request ID where one exists. Use the Temporal UI to follow related workflow executions. Tempo retains traces for 48 hours, Loki retains logs for 72 hours and Prometheus retains metrics for up to seven days or 2 GB.

## Send email alerts

In Better Stack, add a **Prometheus Alertmanager** integration, choose the operator email as the incident escalation recipient and save the integration URL in the host's alert webhook file. Alertmanager sends grouped alerts and recoveries to that receiver. Use Better Stack's integration test to verify email delivery. [Better Stack integration](https://betterstack.com/docs/uptime/prometheus/)

Create a separate HTTPS monitor for `https://play.example.net/healthz` using your actual public hostname. Select the expected HTTP 200 response, a one-minute interval if your plan supports it, and confirmation after three consecutive failed checks or the equivalent confirmation window for your interval. This external monitor can alert when the host and its own monitoring are both down.

| Alert | Initial condition |
| --- | --- |
| Service unavailable | A configured Prometheus scrape target is down for 3 minutes |
| Server errors | At least 5 HTTP 5xx responses and more than 5% of requests in 10 minutes, by service |
| Provisioning failure | At least 3 failed sandbox provisions in 10 minutes |
| Queued starts | Oldest undelivered Boxie start exceeds 60 seconds for 5 minutes |
| Low disk | Less than 15% of the data filesystem is free for 15 minutes |
| Backup overdue | Last successful upload is more than 26 hours old or its metric is missing for 5 minutes |

The error rule uses server responses. Normal CLI command exit codes do not count toward provisioning failures. Tune these defaults once traffic provides a baseline. [Alert definitions](../services/monitoring/alerts.yml)
