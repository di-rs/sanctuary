# First deployment

Use an existing x86-64 Hetzner server running Ubuntu 24.04. You need access to its browser console, the existing host administration identity, repository settings, and a Cloudflare zone. Enrollment installs Docker Compose and gVisor if needed. Existing applications must release any hostnames you assign to this installation at cutover. Routine releases use GitHub Actions.

## Prepare private storage

1. In Cloudflare R2 create two private buckets, one for delivery and one for encrypted database backups. Keep public development URLs and custom domains disabled on both.
2. Scope an Object Read & Write credential to the delivery bucket for GitHub. Give the host a separate Object Read Only credential for that bucket. Scope a third credential to the backup bucket for the backup job. Existing keys with those scopes can be reused. Set a lifecycle rule on `incoming/` to expire abandoned uploads after one day. Keep `blobs/`, `desired/` and `history/` available for releases and rollbacks.
3. In the repository create the GitHub Environment **sanctuary-delivery**. Restrict deployment branches to the protected `master` branch. Add environment variables `CLOUDFLARE_ACCOUNT_ID`, `SANCTUARY_R2_BUCKET` and `R2_PUBLISH_KEY_ID`. Add the matching secret as `R2_PUBLISH_SECRET`. Set the **repository** variable `PREVIEW_ZONE` to your preview DNS suffix so the PR link job can read it.

Each artifact stays in a private bucket. The preview builder receives a read-only source mount and a disposable work volume. Its trusted runner uses a two-hour PUT URL for exactly one staging object. A fresh runner verifies the current PR and checksum before publishing. [Cloudflare R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)

## Configure ingress and your admin identity

1. In Cloudflare Zero Trust, enable **One-time PIN** as a login method. Create two self-hosted Access applications covering the entire Grafana and Temporal UI hostnames. Add an **Allow** policy with **Emails** set to your exact address. Select One-time PIN for each application. Save the team hostname and the Grafana application audience tag.
2. Create or reuse a remotely managed Cloudflare Tunnel. Add these public hostname routes in order. Enable **Protect with Access** on both administration routes and select the corresponding application audience. The connector must validate the appropriate assertion before forwarding either request.

   | Public hostname example | Tunnel origin |
   | --- | --- |
   | `grafana.example.net` | `http://grafana:3000` |
   | `temporal.example.net` | `http://temporal-ui:8080` |
   | `play.example.net` | `http://playground-proxy:80` |
   | `*.example.net` | `http://playground-proxy:80` |

   Use the tunnel's proxied DNS records, including a wildcard CNAME for previews. Choose a suffix covered by your edge certificate. The example produces `pr-42.example.net`. Nested preview subdomains require matching certificate coverage. Keep the original HTTP Host header for the Playground proxy. Caddy returns 404 for unconfigured hosts. A remotely managed tunnel uses the token supplied by Cloudflare. [Tunnel routing](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/) · [Access email PIN](https://developers.cloudflare.com/cloudflare-one/integrations/identity-providers/one-time-pin/)

3. Configure the Hetzner firewall for outbound tunnel and registry traffic. Administration through the provider console permits closing public inbound traffic to this stack. Preserve any existing access you need for other workloads.
4. Set up the Alertmanager integration and external check in the [monitoring guide](observability.md). Save the Alertmanager receiver URL for enrollment.

## Enroll once in the Hetzner browser console

Use the host's root console. Keep credentials in the server's private configuration and GitHub's secret controls. Choose the public recipient of an existing backup decryption key you control. The corresponding private key stays off the host.

```sh
install -d -m 700 /etc/sanctuary
git clone --branch master https://github.com/di-rs/sanctuary.git /opt/sanctuary
cd /opt/sanctuary
install -m 600 infra/host.env.example /etc/sanctuary/host.env
install -m 600 infra/backup.env.example /etc/sanctuary/backup.env
```

Use an editor in that console to fill the two files and put the raw tunnel token and raw alert webhook URL in `/etc/sanctuary/tunnel-token` and `/etc/sanctuary/alert-webhook`. Use your actual account ID, hostnames, Access email and audience. The examples list every required setting. For an existing controller checkout, verify that it is clean and on the intended protected commit before enrollment. [Host settings](../host.env.example) · [Backup settings](../backup.env.example)

```sh
cd /opt/sanctuary
bash infra/enroll.sh
```

Enrollment registers the host updater and daily backup timer. It generates service credentials, a local CA and separate client certificates. Allow existing operator-owned data to remain at its original path during cutover. This installation owns its own `/var/lib/sanctuary` tree. Confirm that destination is available before starting.

## Start the services

From the GitHub Actions tab on `master`, use **Deploy Sanctuary services** for `postgres`, `temporal` and `observability`. Next run **Deploy Boxie**, **Deploy Playground**, then **Deploy Sanctuary services** for `edge`. A successful release workflow means the desired revision is in R2. The host polls it every 90 seconds and retries dependencies that are still starting.

Open the production Playground, start a terminal and run `echor hello`. Verify that both dashboard origins prompt for your email in a private browser and that your approved account can view them. Check an unrecognized hostname for a 404. Verify the external monitor and an off-host backup before relying on the deployment for persistent work. [Rollbacks and recovery](releases.md)
