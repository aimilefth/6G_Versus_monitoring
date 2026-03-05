import pandas as pd

# 1. Read the original CSV file
df = pd.read_csv('prometheus_xavier_nx_data_3m.csv')

# 2. Apply the filters
filtered_df = df[(df['metric'] == 'xavier_nx_power_watts') & (df['component'] == 'VDD_IN')]

# 3. Save the filtered data to a new CSV
filtered_df.to_csv('prometheus_xavier_nx_data_3m_VDD_IN_power.csv', index=False)

print(f"Filtered down to {len(filtered_df)} rows.")