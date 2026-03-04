import pandas as pd
import re
from datetime import datetime, timedelta

def process_dlog(input_file, output_file, offset_seconds=0.0):
    sample_interval = None
    start_date = None
    skip_lines = 0
    
    # Read the file line by line to parse the header
    with open(input_file, 'r') as f:
        for line in f:
            skip_lines += 1
            # Extract sample interval (updated regex to handle scientific notation)
            if "Sample interval:" in line:
                match = re.search(r'Sample interval:\s*([0-9.eE+-]+)', line)
                if match:
                    sample_interval = float(match.group(1))
            
            # Extract start date
            elif "Date:" in line:
                # Remove quotes and capture the date string
                clean_line = line.strip().strip('"')
                match = re.search(r'Date:\s*(.*)', clean_line)
                if match:
                    date_str = match.group(1).strip()
                    # Clean up multiple spaces (e.g., "Mar  3" -> "Mar 3")
                    date_str = re.sub(r'\s+', ' ', date_str)
                    # Parse the string into a datetime object
                    start_date = datetime.strptime(date_str, "%a %b %d %H:%M:%S %Y")
            
            # Stop skipping lines when the CSV table header begins
            elif "Sample," in line:
                skip_lines -= 1  # We want pandas to use this line as the header
                break

    if start_date is None or sample_interval is None:
        raise ValueError("Could not find 'Date' or 'Sample interval' in the file header.")

    # Apply the -2 hours adjustment and the user-defined offset (in seconds)
    start_date = start_date - timedelta(hours=2) + timedelta(seconds=offset_seconds)

    # Load the tabular data
    df = pd.read_csv(input_file, skiprows=skip_lines)
    
    # Calculate timestamps using vectorized operation (Start Date + (Sample index * Sample Interval))
    # This is much faster than apply() and works natively with Pandas datetime tools
    datetime_series = start_date + pd.to_timedelta(df['Sample'] * sample_interval, unit='s')
    
    # Format the timestamp as ISO 8601 to match your other CSV (e.g., 2026-03-04T13:47:54.707000Z)
    df['timestamp'] = datetime_series.dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    
    # Calculate derived power: P = V * I
    df['Power avg 1'] = df['Volt avg 1'] * df['Curr avg 1']
    
    # Reorder columns to make 'timestamp' the first column
    cols = ['timestamp'] + [col for col in df.columns if col != 'timestamp']
    df = df[cols]
    
    # Save the modified dataframe to a new CSV file
    df.to_csv(output_file, index=False)
    print(f"Processed file saved to {output_file}")

if __name__ == "__main__":
    # Example usage: Change offset_seconds as needed
    INPUT_FILE = 'dlog6.csv'
    OUTPUT_FILE = 'derived_dlog6.csv'
    OFFSET_SECONDS = 0.0
    
    process_dlog(INPUT_FILE, OUTPUT_FILE, offset_seconds=OFFSET_SECONDS)