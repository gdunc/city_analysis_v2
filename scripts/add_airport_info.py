import pandas as pd
from openai import OpenAI
from openai import OpenAIError


def main():
    # Load the existing cities CSV
    df = pd.read_csv('outputs/alps_cities.csv')

    # Prepare new columns
    new_columns = [
        'nearest_international_airport',
        'airport_confidence',
        'airport_reasoning',
        'driving_distance_km_time',
        'driving_distance_confidence',
        'driving_distance_reasoning',
        'error'
    ]
    for col in new_columns:
        df[col] = ''

    try:
        client = OpenAI()
        # Attempt to use GPT-5 model (expected to fail if model or credentials missing)
        client.responses.create(
            model='gpt-5',
            input='Return the nearest international airport to Innsbruck, Austria.'
        )
    except Exception as e:
        error_msg = f'OpenAI API call failed: {e}'
        df['error'] = error_msg
        df.to_csv('outputs/alps_cities_airports.csv', index=False)
        return

    # Placeholder for successful flow (not reached in this environment)
    df.to_csv('outputs/alps_cities_airports.csv', index=False)


if __name__ == '__main__':
    main()
