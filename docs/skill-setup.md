# Alexa Skill Setup

Runbook for wiring the deployed AWS edge ([Terraform](https://github.com/jenreh/tiberio/tree/main/terraform)) to an Alexa
Smart-Home skill, linking the account, and verifying end-to-end. The manifest
and account-linking templates live in
[`skill-package/`](https://github.com/jenreh/tiberio/tree/main/skill-package).

## 0. Automated path (`tiberio-setup`)

Most of this runbook is automated by the `tiberio-setup` CLI. After creating the
skill (step 1, to obtain the skill ID) and configuring the `ask` CLI
(`ask configure`):

```bash
aws configure
aks configure

uv run tiberio-setup run \
  --skill-id amzn1.ask.skill.<your-skill-id> \
  --tfvars terraform/terraform.tfvars \
  --username <user> --base-url https://<your-tunnel> --yes
```

This generates `.env` secrets, deploys the AWS edge, renders
`skill-package/build/{skill.json,accountLinking.json}` from the Terraform
outputs, creates the user, publishes the beacon, and pushes the manifest +
account-linking config to the skill (`ask smapi`). Steps 4–6 below then reduce
to: copy the redirect URLs into `TIBERIO_OAUTH_ALLOWED_REDIRECT_URIS`, enable the
skill in the Alexa app, log in, and run device discovery. The manual steps
below remain the source of truth if you prefer to wire the console by hand.

## 1. Create the skill (placeholder endpoint)

There is a chicken-and-egg between the skill ID and the Lambda: the directive
Lambda's permission requires the skill ID (`alexa_skill_id` Terraform
variable), and the skill needs the Lambda ARN as endpoint. Resolve it in this
order:

1. [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask) →
   **Create Skill** → type **Smart Home**, language **German (DE)**
   (`de-DE`), payload version **v3** — or use `skill-package/skill.json`
   with the ASK CLI.
2. Copy the **Skill ID** (`amzn1.ask.skill.…`) from the console.

## 2. Deploy the AWS edge with the skill ID

```bash
cd terraform
./deploy-aws.sh migrate --tfvars terraform.tfvars \
  -var "alexa_skill_id=amzn1.ask.skill.<your-skill-id>"
terraform output deployment_summary
```

## 3. Terraform outputs → console fields

| Terraform output       | Alexa Developer Console field                            |
| ---------------------- | -------------------------------------------------------- |
| `directive_lambda_arn` | Smart Home → **Default endpoint** (and **Europe / India**) |
| `oauth_authorize_url`  | Account Linking → **Web Authorization URI**              |
| `oauth_token_url`      | Account Linking → **Access Token URI**                   |

The remaining `deployment_summary` values (`beacon_bucket_name`,
`beacon_object_key`, `shared_secret_param`) configure the home server's
beacon publisher and HMAC signing — not the console.

## 4. Account linking

Console → **Account Linking** (values mirror
`skill-package/accountLinking.json`):

| Field                       | Value                                                  |
| --------------------------- | ------------------------------------------------------ |
| Auth grant type             | **Auth Code Grant**                                    |
| Web Authorization URI       | `oauth_authorize_url` output                           |
| Access Token URI            | `oauth_token_url` output                               |
| Client ID                   | `alexa-skill` (free-form; the server binds it to the auth code) |
| Client Secret               | any non-empty value — SMAPI **requires** the field for Auth Code Grant, but the server is a PKCE-only public client and ignores it |
| Authentication Scheme       | **Credentials in request body**                        |
| Scope                       | `smart_home`                                           |
| PKCE                        | **Enabled** (`S256`) — see note below                  |
| Domain list / redirect URLs | leave empty / defaults                                 |

> **PKCE is mandatory, not optional.** The home server's `/oauth/authorize`
> rejects any request without a `code_challenge`, so account linking only works
> if Alexa is told to send PKCE. In the console this is the **Enable PKCE**
> toggle; in `accountLinking.json` it is the `pkceConfiguration` block
> (`{"status": "ENABLED", "codeChallengeMethod": "S256"}`). The automated
> `tiberio-setup` flow sets both `clientSecret` and `pkceConfiguration` for you.
> Without these two fields the `ask smapi update-account-linking-info` call
> fails with **HTTP 400** (missing `clientSecret`) or account linking fails at
> login (Alexa never sends `code_challenge`).

After saving, copy the three **Alexa Redirect URLs** shown in the console
into the home server's `TIBERIO_OAUTH_ALLOWED_REDIRECT_URIS` (comma-separated)
and restart the server.

Home-server prerequisites:

- `TIBERIO_JWT_SECRET`, `TIBERIO_SHARED_SECRET` set (the latter matching the
  SSM parameter from `shared_secret_param`).
- A user created via `uv run tiberio-users add <username>`.
- Tunnel running and the beacon published to S3 (`endpoint.json`).

Then: Alexa app → skill → **Enable to use** → log in on the home server's
login page. The token exchange runs Authorization Code + PKCE (`S256` is
enforced by the server; verify during E2E that Alexa sends
`code_challenge` — see risks below).

## 5. Device discovery

Alexa app → **Geräte suchen** (or say *„Alexa, suche nach neuen Geräten"*).
All endpoints from `config/devices.yaml` (channels, TV audio, blinds,
thermostats) must appear. After every change to `devices.yaml`, re-run
discovery.

Pre-check without hardware: invoke the Lambda with
`scripts/sample-events/discovery.json` (see
[`scripts/sample-events/README.md`](https://github.com/jenreh/tiberio/tree/main/scripts/sample-events)).

## 6. E2E verification checklist

Infrastructure (KONZEPT §12):

- [ ] `terraform plan/apply` clean; Lambda answers the sample events
      (`aws lambda invoke`, see `scripts/sample-events/`).
- [ ] Beacon updater writes `endpoint.json`; Lambda's conditional GET picks
      up a changed tunnel URL.
- [ ] Account linking completes in the Alexa app; token refresh works
      (wait > 60 min, issue a command).
- [ ] Directive latency < 8 s, token endpoint < 4.5 s (watch cold starts).

German utterances (verify against the real `de-DE` NLU model, KONZEPT §10):

- [ ] „Alexa, **schalte ZDF ein**" → TV activity starts, channel 2 — robust
      (PowerController device).
- [ ] „Alexa, **mach die Rollos in der Küche halb runter**" → blind at 50 %.
      If „halb" is not understood, use the fallback „**… auf 50 Prozent**"
      (RangeController semantics).
- [ ] „Alexa, **schalte den Fernseher stumm**" → mute on; „Alexa, schalte
      den Ton ein" → mute off (routing to `Speaker.SetMute(false)` is
      uncertain — mitigation: optional `Ton` PowerController synonym device).
- [ ] „Alexa, **stell die Heizung im Wohnzimmer auf 22 Grad**" → FRITZ!Box
      target temperature 22 °C.

## 7. Known risks (documented, KONZEPT §10)

- **Mute drift** — Harmony only offers a mute *toggle*; the server keeps an
  assumed state. Muting via the original remote desynchronizes it (residual
  risk, accepted).
- **NLU phrasing** — exact German sentences are decided by Alexa's
  Smart-Home NLU, not by this project. Verify the utterances above early on
  the real model and prefer the documented fallbacks („auf 50 Prozent",
  `Ton` synonym device).
- **Channel selection** depends on the Harmony activity name and digit
  timing. Alexa's account-linking flow does support **PKCE**, but only when
  `pkceConfiguration.status = ENABLED` is set in the account-linking request
  (it is **DISABLED** by default). The server enforces `S256` and rejects
  exchanges without `code_verifier`, so this flag is mandatory — see §4.
