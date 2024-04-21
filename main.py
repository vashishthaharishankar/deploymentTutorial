import pandas as pd

def data_sample():
    # Create a dictionary with sample data
    data = {
        'Name': ['Alice', 'Bob', 'Charlie', 'David'],
        'Age': [25, 30, 35, 40],
        'City': ['New York', 'Los Angeles', 'Chicago', 'Houston']
    }

    # Create DataFrame from dictionary
    df = pd.DataFrame(data)

    # Print the DataFrame
    return df
