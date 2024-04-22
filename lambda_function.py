import json
import pandas as pd


def lambda_handler(event, context):

    data = {
        'Name': ['Alice', 'Bob', 'Charlie', 'David'],
        'Age': [25, 30, 35, 40],
        'City': ['New York', 'Los Angeles', 'Chicago', 'Houston']
    }

    # Create DataFrame from dictionary
    df = pd.DataFrame(data)


    return {
        'statusCode': 200,
        'body': df.shape
    }
