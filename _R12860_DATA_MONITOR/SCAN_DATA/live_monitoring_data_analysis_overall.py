import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Circle
import matplotlib.patches as mpatches
import glob
import os
from datetime import datetime
from cycler import cycler

if len(sys.argv) < 2:
    print("Usage: python plot_gain_polar.py <SN> [output_base_dir]")
    print("Example: python plot_gain_polar.py SN12345")
    print("Example: python plot_gain_polar.py SN12345 /data/gpfs/projects/punim1378/earles/Precal_GUI")
    sys.exit(1)

SN = sys.argv[1]

if len(sys.argv) >= 3:
    base_dir = sys.argv[2]
else:
    base_dir = '/data/gpfs/projects/punim1378/earles/Precal_GUI'

print(f"Reading gain values for SN={SN}")
print(f"Base directory: {base_dir}")

# Define coordinate arrays (same as bash script)
THETA_VALUES = [0, 10, 10, 10, 10, 20, 20, 20, 20, 30, 30, 30, 30, 40, 40, 40, 40, 50, 50, 50, 50]
PHI_VALUES = [0, 0, 90, 180, 270, 0, 90, 180, 270, 0, 90, 180, 270, 0, 90, 180, 270, 0, 90, 180, 270]

# Find all scan output directories for this SN
search_pattern = os.path.join(base_dir, f"archive/scan_output_*/{SN}/data_theta*_phi*")
scan_dirs = glob.glob(search_pattern)

if not scan_dirs:
    print(f"ERROR: No scan directories found matching pattern: {search_pattern}")
    sys.exit(1)

print(f"Found {len(scan_dirs)} scan directories\n")

# Dictionary to store gain values by (theta, phi)
gain_data = {}

# Read gain values
for scan_dir in scan_dirs:
    # Extract theta and phi from directory name
    dir_name = os.path.basename(scan_dir)
    import re
    match = re.search(r'data_theta(\d+)_phi(\d+)', dir_name)
    
    if not match:
        continue
    
    theta = int(match.group(1))
    phi = int(match.group(2))
    
    # Find GAIN file in this directory
    gain_files = glob.glob(os.path.join(scan_dir, "*_GAIN.txt"))
    
    if not gain_files:
        print(f"WARNING: No GAIN file found in {scan_dir}")
        continue
    
    # Use most recent gain file
    gain_file = sorted(gain_files, key=os.path.getmtime)[-1]
    
    try:
        with open(gain_file, 'r') as f:
            gain_str = f.read().strip()
            gain = float(gain_str)
        
        gain_data[(theta, phi)] = gain
        print(f"  θ={theta:2d}°, φ={phi:3d}° → Gain: {gain:.3e}")
        
    except Exception as e:
        print(f"WARNING: Could not read gain from {gain_file}: {e}")
        continue

if len(gain_data) == 0:
    print(f"ERROR: No valid gain values found for SN={SN}")
    sys.exit(1)

print(f"\nTotal measurements: {len(gain_data)}")

# Create output directory
curr_datetime = datetime.now().strftime('%Y%m%d')
output_dir = os.path.join(base_dir, f"scan_output_{curr_datetime}", SN)
os.makedirs(output_dir, exist_ok=True)

# Dark mode friendly colors
bg = "#0e1117"
fg = "#fafafa"
grid = "#262730"

plt.rcParams.update({
    "font.size": 10,
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
})

timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Create figure
fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))
ax.set_facecolor(bg)

# Convert gains to colors (normalize)
gains = np.array(list(gain_data.values()))
gain_min = gains.min()
gain_max = gains.max()

# Normalize gains to [0, 1] for colormap
if gain_max > gain_min:
    normalized_gains = (gains - gain_min) / (gain_max - gain_min)
else:
    normalized_gains = np.ones_like(gains) * 0.5

# Create colormap (red = low gain, green = normal, yellow = warning)
from matplotlib.colors import LinearSegmentedColormap
colors_list = ['#dc3545', '#ffc107', '#21c354']  # red, yellow, green
n_bins = 100
cmap = LinearSegmentedColormap.from_list('gain_cmap', colors_list, N=n_bins)

# Define target gain range
target_gain = 1.00e7
tolerance = 0.05  # 5% tolerance
gain_low = target_gain * (1 - tolerance)
gain_high = target_gain * (1 + tolerance)

# Plot each measurement as a wedge
phi_segments = [0, 90, 180, 270]
theta_rings = [0, 10, 20, 30, 40, 50]

for (theta, phi), gain in gain_data.items():
    # Convert to radians
    phi_rad = np.deg2rad(phi)
    
    # Determine radial position based on theta
    if theta == 0:
        # Center circle
        radius = 0.15
        circle = Circle((0, 0), radius, 
                       color=cmap((gain - gain_min) / (gain_max - gain_min) if gain_max > gain_min else 0.5),
                       transform=ax.transData._b, 
                       zorder=2)
        ax.add_patch(circle)
        
        # Add text at center
        ax.text(0, 0, f'{gain:.2e}', 
               ha='center', va='center', 
               fontsize=8, color=fg, weight='bold',
               zorder=3)
    else:
        # Ring segments
        r_inner = 0.15 + (theta_rings.index(theta) - 1) * 0.15
        r_outer = r_inner + 0.15
        
        # Width of each segment (90 degrees)
        theta_width = np.deg2rad(90)
        theta_start = phi_rad - theta_width/2
        theta_end = phi_rad + theta_width/2
        
        # Determine color based on gain
        if gain_low <= gain <= gain_high:
            color = '#21c354'  # green - good
        elif gain < gain_low * 0.9 or gain > gain_high * 1.1:
            color = '#dc3545'  # red - bad
        else:
            color = '#ffc107'  # yellow - warning
        
        # Create wedge
        wedge = mpatches.Wedge((0, 0), r_outer, np.rad2deg(theta_start), np.rad2deg(theta_end),
                              width=r_outer-r_inner, 
                              facecolor=color, 
                              edgecolor=grid, 
                              linewidth=1.5,
                              alpha=0.8,
                              zorder=2)
        ax.add_patch(wedge)
        
        # Add gain text
        r_text = (r_inner + r_outer) / 2
        phi_text = phi_rad
        ax.text(phi_text, r_text, f'{gain:.2e}', 
               ha='center', va='center', 
               fontsize=7, color=fg, weight='bold',
               rotation=np.rad2deg(phi_text) - 90,
               zorder=3)

# Configure polar plot
ax.set_ylim(0, 1.0)
ax.set_theta_zero_location('N')
ax.set_theta_direction(-1)

# Set angle labels
ax.set_xticks(np.deg2rad([0, 90, 180, 270]))
ax.set_xticklabels(['0°', '90°', '180°', '270°'], color=fg, fontsize=10)

# Remove radial labels
ax.set_yticks([])

# Add theta ring labels
for i, theta in enumerate([10, 20, 30, 40, 50]):
    r = 0.15 + i * 0.15
    ax.text(np.deg2rad(45), r + 0.075, f'θ={theta}°', 
           ha='center', va='center',
           fontsize=8, color=grid, style='italic',
           bbox=dict(boxstyle='round,pad=0.3', facecolor=bg, edgecolor=grid, alpha=0.8))

# Title
fig.suptitle(f'{timestamp} | SN: {SN}\nGain Distribution Map', 
            color=fg, fontsize=14, weight='bold', y=0.98)

# Add legend
legend_elements = [
    mpatches.Patch(facecolor='#21c354', edgecolor=grid, label=f'Good ({gain_low:.2e} - {gain_high:.2e})'),
    mpatches.Patch(facecolor='#ffc107', edgecolor=grid, label='Warning'),
    mpatches.Patch(facecolor='#dc3545', edgecolor=grid, label='Poor')
]
ax.legend(handles=legend_elements, loc='upper right', 
         bbox_to_anchor=(1.15, 1.1),
         framealpha=0.9, facecolor=bg, edgecolor=grid,
         fontsize=9)

# Add statistics text
stats_text = f'Min: {gain_min:.2e}\nMax: {gain_max:.2e}\nTarget: {target_gain:.2e}'
ax.text(0.02, 0.98, stats_text,
       transform=fig.transFigure,
       fontsize=9, color=fg,
       verticalalignment='top',
       bbox=dict(boxstyle='round,pad=0.5', facecolor=bg, edgecolor=grid, alpha=0.9))

plt.tight_layout()

# Save plot
plot_filename = os.path.join(output_dir, f"{SN}_gain_polar_map.png")
fig.savefig(plot_filename, dpi=150, bbox_inches="tight", facecolor=bg)
plt.close(fig)

print(f"\nPolar map saved to {plot_filename}")
print("Processing complete!")