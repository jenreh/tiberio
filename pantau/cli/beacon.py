"""pantau-beacon — CLI to publish the S3 endpoint beacon (KONZEPT §9).

Commands:
  publish  Write endpoint.json to the beacon bucket with the current base URL.

Run this whenever the tunnel URL changes (e.g. from a cloudflared/ngrok hook)
to announce the home server's new public address to the AWS edge.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated

import typer

from pantau.adapters.s3_beacon_publisher import S3BeaconPublisher
from pantau.application.publish_beacon import BeaconPublisher
from pantau.config.settings import get_settings
from pantau.domain.errors import BeaconPublishError

log = logging.getLogger(__name__)

app = typer.Typer(
    name="pantau-beacon",
    help="Publish the pantau-alexa S3 endpoint beacon.",
    no_args_is_help=True,
)


@app.callback()
def _callback() -> None:
    """Manage the pantau-alexa S3 endpoint beacon."""


@app.command()
def publish(
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            "-u",
            help="Public base URL to announce (defaults to PANTAU_PUBLIC_BASE_URL).",
            show_default=False,
        ),
    ] = None,
    bucket: Annotated[
        str | None,
        typer.Option(
            "--bucket", help="S3 bucket (defaults to settings).", show_default=False
        ),
    ] = None,
    key: Annotated[
        str | None,
        typer.Option(
            "--key", help="S3 object key (defaults to settings).", show_default=False
        ),
    ] = None,
    region: Annotated[
        str | None,
        typer.Option(
            "--region", help="AWS region (defaults to settings).", show_default=False
        ),
    ] = None,
) -> None:
    """Publish endpoint.json to the beacon bucket."""
    settings = get_settings()
    resolved_base_url = base_url or settings.public_base_url
    if not resolved_base_url:
        typer.echo(
            "Error: no base URL given (pass --base-url or set PANTAU_PUBLIC_BASE_URL).",
            err=True,
        )
        raise typer.Exit(1)

    resolved_bucket = bucket or settings.s3_beacon_bucket
    resolved_key = key or settings.s3_beacon_key
    publisher = S3BeaconPublisher(
        bucket=resolved_bucket,
        key=resolved_key,
        region=region or settings.aws_region,
    )
    use_case = BeaconPublisher(publisher, resolved_base_url)

    try:
        beacon = asyncio.run(use_case.execute())
    except BeaconPublishError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1) from exc

    typer.echo(
        f"Published beacon {beacon.base_url} -> s3://{resolved_bucket}/{resolved_key}"
    )


def main() -> None:  # pragma: no cover
    app()
