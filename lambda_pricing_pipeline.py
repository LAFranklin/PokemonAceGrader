"""AWS Lambda entry point for the ACE pricing pipeline.

The existing scraper and matcher remain the source of truth for the business logic.
This file only provides Lambda orchestration and Lambda-specific configuration.
"""

import json
import os

import boto3

import ebay_coldcomps_scrapper as scraper
import match_pokemon_to_price as matcher


SECRETS_REGION = os.environ.get("AWS_REGION", "eu-west-2")
SOLDCOMPS_SECRET_NAME = os.environ.get("SOLDCOMPS_SECRET_NAME", "")


class SharedConnection:
    """Keep one pyodbc connection alive for the whole Lambda invocation."""

    def __init__(self, connection):
        self._connection = connection

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def close(self):
        # The real connection is closed by lambda_handler().
        pass


def load_soldcomps_api_key():
    if not SOLDCOMPS_SECRET_NAME:
        raise RuntimeError("SOLDCOMPS_SECRET_NAME has not been configured.")

    client = boto3.client("secretsmanager", region_name=SECRETS_REGION)
    response = client.get_secret_value(SecretId=SOLDCOMPS_SECRET_NAME)
    secret_string = response.get("SecretString")

    if not secret_string:
        raise RuntimeError("SoldComps secret does not contain SecretString.")

    try:
        secret = json.loads(secret_string)
    except json.JSONDecodeError:
        return secret_string.strip()

    api_key = secret.get("soldcomps_api_key") or secret.get("api_key")

    if not api_key:
        raise RuntimeError(
            "SoldComps secret must contain 'soldcomps_api_key' or 'api_key'."
        )

    return api_key.strip()


def install_lambda_configuration():
    """Inject Lambda-only configuration without changing the existing pipeline logic."""

    scraper.SOLDCOMPS_API_KEY = load_soldcomps_api_key()

    # Load the existing RDS credentials before creating the shared connection.
    scraper.get_secret()

    connection = scraper.get_connection()
    shared = SharedConnection(connection)

    # Both scripts now reuse the same connection for this invocation.
    scraper.get_connection = lambda: shared
    matcher.get_connection = lambda: shared

    return connection


def lambda_handler(event, context):
    print("Starting ACE pricing Lambda pipeline...")

    connection = None

    try:
        connection = install_lambda_configuration()

        print("Running SoldComps scraper...")
        scraper.run()

        print("SoldComps scraper completed.")
        print("Running Pokémon price matching...")
        matcher.main()
        print("Pokémon price matching completed.")

        return {
            "status": "success",
            "message": "ACE pricing pipeline completed successfully.",
        }

    except Exception:
        print("ACE pricing Lambda pipeline failed.")
        raise

    finally:
        if connection is not None:
            connection.close()
        print("ACE pricing Lambda pipeline finished.")
