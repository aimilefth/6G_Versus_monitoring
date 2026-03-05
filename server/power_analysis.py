import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

def load_prom_data(filepath, offset_us, start_dt, end_dt):
    """Loads, offsets, and filters Prometheus data."""
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp_iso'], format='ISO8601').dt.tz_localize(None)
    
    if offset_us != 0:
        df['timestamp'] += pd.Timedelta(microseconds=offset_us)
        
    if start_dt is not None:
        df = df[df['timestamp'] >= start_dt]
    if end_dt is not None:
        df = df[df['timestamp'] <= end_dt]
        
    return df.sort_values('timestamp').reset_index(drop=True)

def load_dlog_data(filepath, offset_us, start_dt, end_dt):
    """Loads, offsets, and filters N6705C Dlog data."""
    df = pd.read_csv(filepath)
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_localize(None)
    
    if offset_us != 0:
        df['timestamp'] += pd.Timedelta(microseconds=offset_us)
        
    if start_dt is not None:
        df = df[df['timestamp'] >= start_dt]
    if end_dt is not None:
        df = df[df['timestamp'] <= end_dt]
        
    return df.sort_values('timestamp').reset_index(drop=True)

def power_analysis(prom_file, dlog_files, prom_offset_us=0, dlog_offset_us=0, 
                   start_time=None, end_time=None, ma_window=1000):
    
    # Parse cutoffs
    start_dt = pd.to_datetime(start_time).tz_localize(None) if start_time else None
    end_dt = pd.to_datetime(end_time).tz_localize(None) if end_time else None
    
    # Load Prometheus
    df_prom = load_prom_data(prom_file, prom_offset_us, start_dt, end_dt)
    
    # Load all Dlogs into a dictionary
    dlogs = {}
    for label, filepath in dlog_files.items():
        dlogs[label] = load_dlog_data(filepath, dlog_offset_us, start_dt, end_dt)

    # Determine absolute T=0 for the X-axis (Seconds from start)
    if start_dt:
        t0 = start_dt
    else:
        # If no start_dt provided, use the earliest time found in any dataset
        t0_prom = df_prom['timestamp'].min()
        t0_dlogs = min([df['timestamp'].min() for df in dlogs.values()])
        t0 = min(t0_prom, t0_dlogs)

    # Convert timestamps to "seconds from t0"
    df_prom['sec_from_start'] = (df_prom['timestamp'] - t0).dt.total_seconds()
    for label in dlogs:
        dlogs[label]['sec_from_start'] = (dlogs[label]['timestamp'] - t0).dt.total_seconds()

    # Calculate Moving Average for the baseline (highest resolution) dlog
    base_label = list(dlog_files.keys())[0]  # Assuming first entry is the baseline
    df_base = dlogs[base_label]
    df_base['Power_MA'] = df_base['Power avg 1'].rolling(window=ma_window, center=True).mean()

    # ====================================================
    # PLOT 1: Baseline Dlog, Prometheus, and Moving Average
    # ====================================================
    plt.figure(figsize=(14, 7))
    plt.plot(df_base['sec_from_start'], df_base['Power avg 1'], 
             label=f'{base_label} Raw', color='lightcoral', alpha=0.5, linewidth=1)
    
    plt.plot(df_prom['sec_from_start'], df_prom['value'], 
             label='SW (INA3221)', color='blue', alpha=0.8, linewidth=2)
    
    plt.plot(df_base['sec_from_start'], df_base['Power_MA'], 
             label=f'{base_label} Moving Avg (Window={ma_window})', color='darkred', alpha=0.9, linewidth=2)
    
    plt.xlabel('Time (Seconds from start)')
    plt.ylabel('Power (Watts)')
    plt.title('Plot 1: HW () vs SW (INA3221) with Moving Average')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig('analysis_plot1_baseline_and_ma.png')
    print("Saved Plot 1: 'analysis_plot1_baseline_and_ma.png'")

    # ====================================================
    # PLOT 2: Comparison of all sampling rates
    # ====================================================
    plt.figure(figsize=(14, 7))
    colors = ['red', 'green', 'orange', 'purple']
    
    for i, (label, df) in enumerate(dlogs.items()):
        color = colors[i % len(colors)]
        plt.plot(df['sec_from_start'], df['Power avg 1'], 
                 label=label, color=color, alpha=0.7, linewidth=1.5)
        
    plt.xlabel('Time (Seconds from start)')
    plt.ylabel('Power (Watts)')
    plt.title('Plot 2: Derived HW Comparisons (Different Sampling Rates)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig('analysis_plot2_sampling_rates.png')
    print("Saved Plot 2: 'analysis_plot2_sampling_rates.png'")

    # ====================================================
    # PLOT 3: Difference (Dlog Moving Average - Prometheus)
    # ====================================================
    # Drop NaNs from the Moving Average so numpy.interp works correctly
    valid_ma = df_base.dropna(subset=['Power_MA'])
    
    # Interpolate the Dlog Moving Average values onto the exact Prometheus time points
    interpolated_dlog_ma = np.interp(
        df_prom['sec_from_start'],   # X values to predict at
        valid_ma['sec_from_start'],  # Known X values
        valid_ma['Power_MA']         # Known Y values
    )
    
    # Calculate the difference
    prom_diff = interpolated_dlog_ma - df_prom['value']
    
    plt.figure(figsize=(14, 7))
    plt.plot(df_prom['sec_from_start'], prom_diff, 
             label='Diff (HW MA - SW (INA3221))', color='purple', linewidth=2)
    
    # Add a horizontal line at 0 for visual reference
    plt.axhline(0, color='black', linestyle='--', linewidth=1)
    
    plt.xlabel('Time (Seconds from start)')
    plt.ylabel('Power Difference (Watts)')
    plt.title('Plot 3: Difference between HW Moving Avg and SW (INA3221)')
    plt.legend()
    plt.grid(True, linestyle='--', alpha=0.6)
    plt.tight_layout()
    plt.savefig('analysis_plot3_difference.png')
    print("Saved Plot 3: 'analysis_plot3_difference.png'")


if __name__ == "__main__":
    PROM_FILE = 'prometheus_xavier_nx_data_2m.csv'
    
    # Dictionary of all Dlog files to load and compare
    # The first item will be treated as the "baseline" for Plot 1 and Plot 3
    DLOG_FILES = {
        'HW (0.04ms)': 'derived_dlog6.csv',
        'HW 2.5 (0.1ms)': 'derived_dlog6_2.5.csv',
        'HW 25 (1ms)': 'derived_dlog6_25.csv',
        'HW 250 (10ms)': 'derived_dlog6_250.csv'
    }
    
    PROM_OFFSET_US = 69 * 1000000  # Example offset
    DLOG_OFFSET_US = 0
    
    PLOT_START = '2026-03-04 13:48:52.000000'
    PLOT_END   = '2026-03-04 13:50:52.000000'
    
    # Configure the moving average window size (number of rows based on the 0.04ms file)
    MA_WINDOW_SIZE = 25000
    
    power_analysis(
        prom_file=PROM_FILE, 
        dlog_files=DLOG_FILES,
        prom_offset_us=PROM_OFFSET_US,
        dlog_offset_us=DLOG_OFFSET_US,
        start_time=PLOT_START,
        end_time=PLOT_END,
        ma_window=MA_WINDOW_SIZE
    )