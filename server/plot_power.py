import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

def plot_power_data(prometheus_file, derived_file, 
                    prom_offset_us=0, dlog_offset_us=0, 
                    start_time=None, end_time=None):
    """
    Plots power data from Prometheus and Dlog files.
    
    :param prometheus_file: Path to Prometheus CSV
    :param derived_file: Path to Derived N6705C Dlog CSV
    :param prom_offset_us: Microseconds to add/subtract to Prometheus timestamps
    :param dlog_offset_us: Microseconds to add/subtract to Dlog timestamps
    :param start_time: String or Datetime. Cutoff plot to start exactly at this time.
    :param end_time: String or Datetime. Cutoff plot to end exactly at this time.
    """
    
    # ----------------------------------------------------
    # 1. Load and process Prometheus data
    # ----------------------------------------------------
    df_prom = pd.read_csv(prometheus_file)
    df_prom['timestamp'] = pd.to_datetime(df_prom['timestamp_iso'], format='ISO8601').dt.tz_localize(None)
    
    # Apply fine-grained microsecond offset
    if prom_offset_us != 0:
        df_prom['timestamp'] += pd.Timedelta(microseconds=prom_offset_us)
        
    # ----------------------------------------------------
    # 2. Load and process Derived Dlog data
    # ----------------------------------------------------
    df_dlog = pd.read_csv(derived_file)
    df_dlog['timestamp'] = pd.to_datetime(df_dlog['timestamp']).dt.tz_localize(None)
    
    # Apply fine-grained microsecond offset
    if dlog_offset_us != 0:
        df_dlog['timestamp'] += pd.Timedelta(microseconds=dlog_offset_us)
        
    # ----------------------------------------------------
    # 3. Apply Time Window Filtering (Cutoffs)
    # ----------------------------------------------------
    if start_time is not None:
        start_dt = pd.to_datetime(start_time).tz_localize(None)
        df_prom = df_prom[df_prom['timestamp'] >= start_dt]
        df_dlog = df_dlog[df_dlog['timestamp'] >= start_dt]
        
    if end_time is not None:
        end_dt = pd.to_datetime(end_time).tz_localize(None)
        df_prom = df_prom[df_prom['timestamp'] <= end_dt]
        df_dlog = df_dlog[df_dlog['timestamp'] <= end_dt]
        
    # ----------------------------------------------------
    # 4. Plotting
    # ----------------------------------------------------
    plt.figure(figsize=(14, 7))
    
    # Plot Prometheus data
    plt.plot(df_prom['timestamp'], df_prom['value'], 
             label='Prometheus (Xavier NX VDD_IN)', color='blue', alpha=0.7, linewidth=2)
    
    # Plot N6705C derived data
    plt.plot(df_dlog['timestamp'], df_dlog['Power avg 1'], 
             label='N6705C (Power avg 1)', color='red', alpha=0.7, linewidth=2)
    
    # Formatting X and Y axes
    plt.xlabel('Timestamp')
    plt.ylabel('Power (Watts)')
    plt.title('Power Measurement Comparison: Prometheus vs N6705C Datalogger')
    
    # Formatting the x-axis to display time neatly (showing microseconds)
    plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d %H:%M:%S.%f'))
    plt.gcf().autofmt_xdate() # Rotates dates so they fit without overlapping
    
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    
    # Save plot as a PNG image
    output_image = 'power_comparison_plot.png'
    plt.savefig(output_image)
    print(f"Plot successfully saved as '{output_image}'")

if __name__ == "__main__":
    PROM_FILE = 'prometheus_xavier_nx_data_2m.csv'
    DERIVED_FILE = 'derived_dlog6.csv'
    
    # Example 1: Adjust Prometheus timestamps forward by 500,000 microseconds (0.5s)
    PROM_OFFSET_US = 69*1000000
    
    # Example 2: Adjust DLog timestamps backward by 250,000 microseconds (-0.25s)
    DLOG_OFFSET_US = 0
    
    # Example 3: Set exact plot cutoffs (Set to None if you want the full timeline)
    # Formats supported: 'YYYY-MM-DD HH:MM:SS.ffffff' or standard ISO strings
    PLOT_START = '2026-03-04 13:48:52.000000'
    PLOT_END   = '2026-03-04 13:50:52.000000'
    
    plot_power_data(
        prometheus_file=PROM_FILE, 
        derived_file=DERIVED_FILE,
        prom_offset_us=PROM_OFFSET_US,
        dlog_offset_us=DLOG_OFFSET_US,
        start_time=PLOT_START,
        end_time=PLOT_END
    )