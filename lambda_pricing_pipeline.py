"""AWS Lambda entry point for the ACE pricing pipeline."""

import json
import os
import boto3

import ebay_coldcomps_scrapper as scraper
import match_pokemon_to_price as matcher


SECRET_NAME = os.environ.get("SOLDCOMPS_SECRET_NAME", "pokemon/soldcomps-api")


def load_api_key():
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=SECRET_NAME)
    value = response.get("SecretString", "")

    try:
        return json.loads(value)["soldcomps_api_key"]
    except (json.JSONDecodeError, KeyError):
        return value.strip()


def lambda_handler(event, context):
    print("Starting ACE pricing pipeline")

    scraper.SOLDCOMPS_API_KEY = load_api_key()

    print("Running SoldComps scraper...")
    scraper.run()

    print("Running Pokemon price matching...")
    matcher.main()

    print("ACE pricing pipeline completed successfully")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "status": "success",
            "message": "ACE pricing pipeline completed successfully"
        })
    }
