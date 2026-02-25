import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, FuncFormatter
import pandas as pd
import glob
import os
from datetime import datetime
import zoneinfo
from zoneinfo import ZoneInfo
from cycler import cycler

# if len(sys.argv) < 2:
#     print("Usage: python plot_gain_hv.py <SN> [output_base_dir]")
#     print("Example: python plot_gain_hv.py SN12345")
#     print("Example: python plot_gain_hv.py SN12345 /data/gpfs/projects/punim1378/earles/Precal_GUI/HV_CHECK")
#     sys.exit(1)

SN = sys.argv[1]

# if len(sys.argv) >= 3:
#     base_dir = sys.argv[1]
# else:
#     base_dir = '/data/gpfs/projects/punim1378/earles/Precal_GUI/HV_CHECK'

print(f"Reading gain and HV values for SN={SN}")
# print(f"Base directory: {base_dir}")

# Find all HV output directories for this SN
search_pattern = os.path.join(f"HV_output_*/{SN}/data_HV_*")
hv_dirs = sorted(glob.glob(search_pattern))

# Get the most recent HV_output_* directory
most_recent_hv_output = sorted(glob.glob("HV_output_*"))[-1]

# Create output directory as HV_output_*/{SN}
output_dir = os.path.join(most_recent_hv_output, SN)
os.makedirs(output_dir, exist_ok=True)
print(f"\nOutput directory: {output_dir}")

if not hv_dirs:
    print(f"ERROR: No HV directories found matching pattern: {search_pattern}")
    sys.exit(1)

print(f"Found {len(hv_dirs)} HV directories\n")

# Extract HV values and gain measurements
hv_values = []
gain_values = []
gain_errors = []
timestamps = []

for hv_dir in hv_dirs:
    # Extract HV value from directory name
    hv_match = os.path.basename(hv_dir).replace('data_HV_', '')
    
    # Find gain file in this directory
    gain_files = glob.glob(os.path.join(hv_dir, "*_GAIN.txt"))
    
    if not gain_files:
        print(f"WARNING: No GAIN file found in {hv_dir}")
        continue
    
    # Use most recent gain file if multiple exist
    gain_file = sorted(gain_files, key=os.path.getmtime)[-1]
    
    try:
        with open(gain_file, 'r') as f:
            lines = f.read().strip().split('\n')
            gain = float(lines[0])
            # Read error from second line if it exists, otherwise use 0
            gain_error = float(lines[1]) if len(lines) > 1 else 0.0
        
        hv_value = int(hv_match)
        hv_values.append(hv_value)
        gain_values.append(gain)
        gain_errors.append(gain_error)
        
        # Extract timestamp from filename
        filename = os.path.basename(gain_file)
        if 'live_data_' in filename:
            ts = filename.split('live_data_')[1].split('_' + SN)[0]
            timestamps.append(ts)
        else:
            timestamps.append("unknown")
        
    except Exception as e:
        print(f"WARNING: Could not read gain from {gain_file}: {e}")
        continue

if len(hv_values) == 0:
    print(f"ERROR: No valid gain values found for SN={SN}")
    sys.exit(1)

# Sort by HV value
sorted_indices = np.argsort(hv_values)
hv_values = np.array(hv_values)[sorted_indices]
gain_values = np.array(gain_values)[sorted_indices]
gain_errors = np.array(gain_errors)[sorted_indices]
timestamps = np.array(timestamps)[sorted_indices]

# Create DataFrame
df = pd.DataFrame({
    'HV': hv_values,
    'Gain': gain_values,
    'Gain_Error': gain_errors,
    'Timestamp': timestamps
})

print("="*60)
print(f"Gain and HV values for {SN}:")
print("="*60)
print(df.to_string(index=False))
print("="*60)
print(f"\nTotal measurements: {len(hv_values)}")
print(f"HV range: {hv_values.min()} - {hv_values.max()} V")
print(f"Gain range: {gain_values.min():.3e} - {gain_values.max():.3e}")
HVNOMLL=hv_values.min()
HVNOMHH=hv_values.max()
# Fit to find HV at gain = 1.00e7
target_gain = 1.00e7

if len(hv_values) >= 2:
    log_hv = np.log10(hv_values)
    log_gain = np.log10(gain_values)

    
    log_gain_errors = gain_errors / (gain_values * np.log(10))
    
    weights = 1.0 / log_gain_errors**2
    coeffs = np.polyfit(log_hv, log_gain, 1, w=np.sqrt(weights))
    b = coeffs[0]
    a = coeffs[1]

    log_gain_fit = a + b * log_hv
    residuals = log_gain - log_gain_fit
    chi2 = np.sum((residuals / log_gain_errors)**2)
    
    dof = len(hv_values) - 2  # 2 free parameters (slope and intercept)
    chi2_dof = chi2 / dof
    
    print(f"chi^2 = {chi2:.3f}")
    print(f"Degrees of freedom = {dof}")
    print(f"chi^2/dof = {chi2_dof:.3f}")

# if len(hv_values) >= 2:
#     log_hv = np.log10(hv_values)
#     log_gain = np.log10(gain_values)
    
#     # Fit: log(Gain) = a + b*log(HV)
#     coeffs = np.polyfit(log_hv, log_gain, 1)
#     b = coeffs[0]  # slope
#     a = coeffs[1]  # intercept
    
#     print(f"\nPower Law Fit: Gain = 10^{a:.3f} * HV^{b:.3f}")
    
#     # Calculate R-squared
#     log_gain_fit = a + b * log_hv
#     residuals = log_gain - log_gain_fit
#     ss_res = np.sum(residuals**2)
#     ss_tot = np.sum((log_gain - np.mean(log_gain))**2)
#     r_squared = 1 - (ss_res / ss_tot)
#     print(f"R² = {r_squared:.4f}")
    
    # Find HV at target gain using the fit
    # log(target_gain) = a + b*log(HV_target)
    # log(HV_target) = (log(target_gain) - a) / b
    log_target_gain = np.log10(target_gain)
    log_hv_at_target = (log_target_gain - a) / b
    hv_at_target = 10**log_hv_at_target
    
    print(f"\n*---------------------------------------*")
    print(f"| HV at Gain={target_gain:.2e}: {hv_at_target:.1f} V |")
    print(f"*---------------------------------------*")
else:
    print(f"\nWARNING: Need at least 2 data points for fitting.")
    hv_at_target = None
    b = None
    a = None




# Dark mode friendly colors
bg = "#0e1117"      # Streamlit dark background
fg = "#fafafa"      # Light text
grid = "#262730"    # Subtle grid lines

plt.rcParams.update({
    "font.size": 12,
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans"],
    "mathtext.fontset": "dejavusans",
    "figure.facecolor": bg,
    "axes.facecolor": bg,
    "axes.edgecolor": fg,
    "text.color": fg,
    "axes.labelcolor": fg,
    "xtick.color": fg,
    "ytick.color": fg,
    "axes.grid": True,
    "grid.color": grid,
    "grid.alpha": 0.3,
    "grid.linestyle": "-",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "lines.linewidth": 2.0,
})

plt.rcParams["axes.prop_cycle"] = cycler(color=[
    "#ff4b4b",  # Streamlit red (primary accent)
    "#00d4ff",  # Cyan blue
    "#ffa421",  # Orange
    "#21c354",  # Green
])


JST = ZoneInfo("Asia/Tokyo")
curr_date = datetime.now(JST).strftime('%Y%m%d')
timestamp = datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')

fig, ax = plt.subplots(figsize=(6, 3))

# Plot data points with error bars
ax.errorbar(
    hv_values,
    gain_values,
    yerr=gain_errors,
    fmt='o',
    color="#ff4b4b",
    ecolor="#ff4b4b",
    markersize=1,
    capsize=3,
    capthick=1.0,
    alpha=0.9,
    label="Measured",
)
ax.set_xscale('log')
ax.set_yscale('log')

# Add fit line if we have enough points
if len(hv_values) >= 2 and b is not None:
    hv_smooth = np.logspace(np.log10(hv_values.min()*0.9), np.log10(hv_values.max()*1.1), 100)
    log_hv_smooth = np.log10(hv_smooth)
    log_gain_smooth = a + b * log_hv_smooth
    gain_smooth = 10**log_gain_smooth
    
    ax.plot(
        hv_smooth,
        gain_smooth,
        '--',
        color="#00d4ff",
        linewidth=1.5,
        alpha=0.6,
        label="loglog fit"
    )
    
    # Mark the target gain point if it exists
    if hv_at_target is not None:
        ax.plot(
            hv_at_target,
            target_gain,
            '+',
            color="#21c354",
            markersize=10,
            markeredgewidth=1,
            alpha=0.9,
            label=f"HV @ {target_gain:.2e}",
            zorder=5
        )
        
        # Add horizontal and vertical lines to target
        ax.axhline(y=target_gain, color=grid, linestyle='--', alpha=0.5, linewidth=1)
        ax.axvline(x=hv_at_target, color=grid, linestyle='--', alpha=0.5, linewidth=1)

ax.set_title(f"{timestamp} | SN: {SN}", color=fg, pad=10)
ax.set_xlabel("High Voltage [V]")
ax.set_ylabel("Gain")
ax.set_xlim(HVNOMLL-25, HVNOMHH+25)
ax.xaxis.set_major_locator(MultipleLocator(50))
ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: f'{int(x)}'))


ax.minorticks_on()
ax.tick_params(
    axis="both",
    which="both",
    direction="in",
    top=True,
    right=True,
    labelright=False,
    labeltop=False,
)

# Create legend text
if hv_at_target is not None:
    legend_text = f"Required Voltage:\n{hv_at_target:.1f} V"
else:
    legend_text = f"Required Voltage:\nOut of range"

ax.legend(
    [legend_text, chi2_dof],
    loc="upper left",
    fontsize="small",
    framealpha=0.9,
    facecolor="#262730",
    edgecolor="#31333F",
)

plot_filename = os.path.join(output_dir, f"{SN}_gain_vs_hv_loglog.png")
fig.savefig(
    plot_filename,
    dpi=150,
    bbox_inches="tight",
)
plt.close(fig)

print(f"\nPlot saved to {plot_filename}")

# Save HV at target gain
if hv_at_target is not None:
    hv_filename = os.path.join(output_dir, f"{SN}_HV_at_gain_{target_gain:.2e}.txt")
    with open(hv_filename, 'w') as f:
        f.write(f"{hv_at_target:.1f}")
    print(f"HV value saved to {hv_filename}")

print("Processing complete!")