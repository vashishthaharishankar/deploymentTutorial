import json
from main import data_sample


def lambda_handler(event, context):
    # TODO implement
    print("Executed 1")
    return {
        'statusCode': 200,
        'body': json.dumps(data_sample())
    }
