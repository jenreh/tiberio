# Sample directive events

Alexa Smart-Home v3 directive events for the directive-proxy Lambda
(`lambda/directive_proxy/handler.py`). The Lambda receives the directive
object as-is, so the same files work against the Lambda **and** against the
home server's `POST /alexa/directive`.

| File                                      | Directive                                       | Endpoint             |
| ----------------------------------------- | ----------------------------------------------- | -------------------- |
| `discovery.json`                          | `Alexa.Discovery.Discover`                      | —                    |
| `power_turn_on_channel.json`              | `Alexa.PowerController.TurnOn`                  | `zdf` (channel)      |
| `speaker_set_mute.json`                   | `Alexa.Speaker.SetMute`                         | `tv-audio`           |
| `thermostat_set_target_temperature.json`  | `Alexa.ThermostatController.SetTargetTemperature` | `wohnzimmer-heizung` |
| `range_set_range_value.json`              | `Alexa.RangeController.SetRangeValue` (50 %)    | `kueche-rollo`       |

Replace `REPLACE_WITH_ACCESS_TOKEN` with a real access token from the OAuth
token endpoint (or any value when the home server runs with
`PANTAU_DEV_MODE=true`). Endpoint IDs match the example
`config/devices.yaml` — adjust to your device config.

## Invoke the deployed Lambda

```bash
aws lambda invoke \
  --function-name pantau-alexa-directive-proxy \
  --cli-binary-format raw-in-base64-out \
  --payload file://scripts/sample-events/discovery.json \
  /dev/stdout
```

## Run locally with SAM

```bash
sam local invoke DirectiveProxy \
  --event scripts/sample-events/power_turn_on_channel.json
```

(Requires a SAM template that points at `lambda/directive_proxy/handler.handler`
and the beacon/secret env vars — see `terraform/modules/lambda_directive`.)

## POST directly to the home server

```bash
curl -X POST http://localhost:8000/alexa/directive \
  -H "Content-Type: application/json" \
  -d @scripts/sample-events/thermostat_set_target_temperature.json
```
