import sys
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
from matplotlib.gridspec import GridSpec
import pandas as pd
import uproot
import awkward as ak
import glob
import os
from datetime import datetime
from zoneinfo import ZoneInfo
import zoneinfo
from cycler import cycler
import zfit
import scipy.constants as const
import re

if len(sys.argv) < 4:
    print("Usage: python script.py <SN> <theta> <phi>")
    print("Example: python script.py SN12345 10 90")
    sys.exit(1)

SN = sys.argv[1]
theta = sys.argv[2]
phi = sys.argv[3]

JST = ZoneInfo("Asia/Tokyo")
curr_datetime = datetime.now(JST).strftime('%Y%m%d_%H%M%S')
curr_date = datetime.now(JST).strftime('%Y%m%d')

script_dir = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(script_dir, f"scan_output_{curr_datetime}", SN, f"data_theta{theta}_phi{phi}")
# output_dir = f'/data/gpfs/projects/punim1378/earles/Precal_GUI/scan_output_{SN}/{curr_date}/data_theta{theta}_phi{phi}/'

os.makedirs(output_dir, exist_ok=True)

print(f"Looking for ROOT files for SN={SN}, theta={theta}, phi={phi}")

# # search_pattern = f"/data/gpfs/projects/punim1378/earles/WaveDumpSaves/wavedump_output_*/{SN}/wavesave_theta{theta}_phi{phi}/new_wavesave_theta{theta}_phi{phi}.root"
# # search_pattern = f"/data/gpfs/projects/punim1378/earles/ROOT_scan_data_saves/{SN}/{curr_date}/scan_{curr_date}_{SN}_theta{theta}_phi{phi}.root"
# # search_pattern = os.path.join(script_dir, "ROOT_scan_data_saves", SN, curr_date, f"scan_{curr_date}_{SN}_theta{theta}_phi{phi}.root")

search_pattern = os.path.join(script_dir, "ROOT_SCAN_DATA_saves", f"pyrate_output_*", SN, f"scan_*_{SN}_theta{theta}_phi{phi}.root")

# search_pattern = os.path.join(script_dir, "ROOT_scan_data_saves", SN, "20260219", f"scan_20260219_{SN}_theta{theta}_phi{phi}.root")
files = glob.glob(search_pattern)

if not files:
    print(f"ERROR: No ROOT files found matching pattern: {search_pattern}")
    sys.exit(1)

# most recent file
files.sort(key=os.path.getmtime, reverse=True)
input_file = files[0]

print(f"Processing file: {input_file}")

match = re.search(r'live_data_(\d+_\d+)_', os.path.basename(input_file))
if match:
    input_datetime = match.group(1)
else:
    input_datetime = curr_datetime

print(f"Using datetime: {input_datetime}")

with uproot.open(input_file) as f: 
    # Get available trees
    available_trees = f.keys()
    print(f"Available trees: {available_trees}")
    
    sig_gen_tree = f['Tree_CH0']
    sipm_tree = f['Tree_CH1']
    ref_pmt_tree = f['Tree_CH2']
    # ref_pmt_tree = f['Tree_CH4']
    
    # Determine which PMT channel to use (check if any key starts with the tree name)
    has_ch2 = any(key.startswith('Tree_CH2') for key in available_trees)
    has_ch3 = any(key.startswith('Tree_CH3') for key in available_trees)
    
    if has_ch2:
        pmt_tree = f['Tree_CH2']
        pmt_channel = 2
    elif has_ch3:
        pmt_tree = f['Tree_CH3']
        pmt_channel = 3
    else:
        raise KeyError(f"Neither Tree_CH2 nor Tree_CH3 found in ROOT file. Available: {available_trees}")
    
    print(f"Using Tree_CH{pmt_channel} for PMT data")
    print(pmt_tree.keys())
# pmt_data = pmt_tree.arrays(['PeakHeight', 'PeakLocation', 'PulseCharge', 'PulseStart'], library='pd')
# sig_gen_data = sig_gen_tree.arrays(['PeakHeight', 'PeakLocation', 'PulseCharge', 'PulseStart'], library='pd')
# sipm_data = sipm_tree.arrays(['PeakHeight', 'PeakLocation', 'PulseCharge', 'PulseStart'], library='pd')

sig_gen_data = sig_gen_tree.arrays(['PulseCharge', 'PulseStart'], library='pd')
sipm_data = sipm_tree.arrays(['PulseCharge', 'PulseStart'], library='pd')
ref_pmt_data = ref_pmt_tree.arrays(['PulseCharge', 'PulseStart'], library='pd')
pmt_data = pmt_tree.arrays(['PulseCharge', 'PulseStart'], library='pd')

PMT_PULSECHARGE = pmt_tree['PulseCharge'].arrays(library='pd')
PMT_PULSECHARGE = PMT_PULSECHARGE.rename(columns={'PulseCharge': 'PMT_PulseCharge'})
PMT_PULSECHARGE = PMT_PULSECHARGE.astype('float32')

ref_PMT_PULSECHARGE = ref_pmt_tree['PulseCharge'].arrays(library='pd')
ref_PMT_PULSECHARGE = ref_PMT_PULSECHARGE.rename(columns={'PulseCharge': 'ref_PMT_PulseCharge'})
ref_PMT_PULSECHARGE = ref_PMT_PULSECHARGE.astype('float32')

SG_PULSECHARGE = sig_gen_tree['PulseCharge'].arrays(library='pd')
SG_PULSECHARGE = SG_PULSECHARGE.rename(columns={'PulseCharge': 'SG_PulseCharge'})
SG_PULSECHARGE = SG_PULSECHARGE.astype('float32')

SIPM_PULSECHARGE = sipm_tree['PulseCharge'].arrays(library='pd')
SIPM_PULSECHARGE = SIPM_PULSECHARGE.rename(columns={'PulseCharge': 'SiPM_PulseCharge'})
SIPM_PULSECHARGE = SIPM_PULSECHARGE.astype('float32')

PMT_PULSESTART = pmt_tree['PulseStart'].arrays(library='pd')*2
PMT_PULSESTART = PMT_PULSESTART.rename(columns={'PulseStart': 'PMT_PulseStart'})
PMT_PULSESTART = PMT_PULSESTART.astype('float32')

ref_PMT_PULSESTART = ref_pmt_tree['PulseStart'].arrays(library='pd')*2
ref_PMT_PULSESTART = ref_PMT_PULSESTART.rename(columns={'PulseStart': 'ref_PMT_PulseStart'})
ref_PMT_PULSESTART = ref_PMT_PULSESTART.astype('float32')

SG_PULSESTART = sig_gen_tree['PulseStart'].arrays(library='pd')*2
SG_PULSESTART = SG_PULSESTART.rename(columns={'PulseStart': 'SG_PulseStart'})
SG_PULSESTART = SG_PULSESTART.astype('float32')

SIPM_PULSESTART = sipm_tree['PulseStart'].arrays(library='pd')*2
SIPM_PULSESTART = SIPM_PULSESTART.rename(columns={'PulseStart': 'SiPM_PulseStart'})
SIPM_PULSESTART = SIPM_PULSESTART.astype('float32')

PULSE_DF = pd.concat([PMT_PULSESTART, SG_PULSESTART, SIPM_PULSESTART, PMT_PULSECHARGE, SG_PULSECHARGE, SIPM_PULSECHARGE], axis=1)

ref_PULSE_DF = pd.concat([ref_PMT_PULSESTART, SG_PULSESTART, SIPM_PULSESTART, ref_PMT_PULSECHARGE, SG_PULSECHARGE, SIPM_PULSECHARGE], axis=1)

PULSE_DF['del_pmt_sg'] = PULSE_DF['PMT_PulseStart'] - PULSE_DF['SG_PulseStart']

# ref_PULSE_DF['del_ref_pmt_sg'] = PULSE_DF['ref_PMT_PulseStart'] - PULSE_DF['SG_PulseStart']

PMT_PulseCharge_quer = PULSE_DF.query('0.5<PMT_PulseCharge<4.5 & 321<del_pmt_sg<330').PMT_PulseCharge

# ref_PMT_PulseCharge_quer = PULSE_DF.query('0.5<ref_PMT_PulseCharge<4.5 & 321<del_ref_pmt_sg<330').ref_PMT_PulseCharge


if len(PMT_PulseCharge_quer) < 10:
    print(f"WARNING: Insufficient data after filtering. Only {len(PMT_PulseCharge_quer)} events found.")
    print("Skipping fit and saving placeholder values.")
    gain_PMT = 0.0
    gain_PMT_err = 0.0
else:
    
    pmt_pc_min = np.min(PMT_PulseCharge_quer)
    pmt_pc_max = np.max(PMT_PulseCharge_quer)
    obs = zfit.Space(obs='t', lower=pmt_pc_min, upper=pmt_pc_max)
    pmt_pc_data = PMT_PulseCharge_quer.to_numpy()

    mu_1PE = zfit.Parameter('mu_1PE', 1.5, 1.0, 2, step_size=0.2)
    sigma_num_1PE = zfit.Parameter('sigma_1PE', 1, 0.1, 2, floating=True)
    mu_2PE = zfit.ComposedParameter("mu_2PE", lambda m: 2 * m, params=[mu_1PE])
    sigma_num_2PE = zfit.Parameter('sigma_2PE', 1, 0.1, 2, floating=True)
    frac_1PE = zfit.Parameter("frac_1pe", 0.6, lower=0, upper=1)
    total_yield = zfit.Parameter("total_yield", len(PMT_PulseCharge_quer), 
                                 lower=len(PMT_PulseCharge_quer)*0.5, 
                                 upper=len(PMT_PulseCharge_quer)*1.5)

    gauss_1PE = zfit.pdf.Gauss(mu=mu_1PE, sigma=sigma_num_1PE, obs=obs)
    gauss_2PE = zfit.pdf.Gauss(mu=mu_2PE, sigma=sigma_num_2PE, obs=obs)
    sum_pdf = zfit.pdf.SumPDF([gauss_1PE, gauss_2PE], fracs=[frac_1PE], extended=total_yield)

    nll = zfit.loss.ExtendedUnbinnedNLL(model=sum_pdf, data=pmt_pc_data)
    minimizer = zfit.minimize.Minuit()
    result = minimizer.minimize(nll)
    result.hesse()

    mu_1PE_val = float(result.params['mu_1PE']["value"])
    mean_err_1PE = float(result.params['mu_1PE']["hesse"]['error'])

    elementary_charge = const.elementary_charge
    gain_PMT = (mu_1PE_val / elementary_charge) * 1e-12
    gain_PMT_err = (mean_err_1PE / elementary_charge) * 1e-12

    print(f"Electron Charge: {elementary_charge} C")
    print("*---------------------------------------*")
    print(f"| GAIN: {gain_PMT:.3e} ± {gain_PMT_err:.3e}      |")
    print("*---------------------------------------*")


# if len(ref_pmt_PulseCharge_quer) < 10:
#     print(f"WARNING: Insufficient data after filtering. Only {len(ref_pmt_PulseCharge_quer)} events found.")
#     print("Skipping fit and saving placeholder values.")
#     gain_ref_pmt = 0.0
#     gain_ref_pmt_err = 0.0
# else:
    
#     ref_pmt_pc_min = np.min(ref_pmt_PulseCharge_quer)
#     ref_pmt_pc_max = np.max(ref_pmt_PulseCharge_quer)
#     obs = zfit.Space(obs='t', lower=ref_pmt_pc_min, upper=ref_pmt_pc_max)
#     ref_pmt_pc_data = ref_pmt_PulseCharge_quer.to_numpy()

#     mu_1PE = zfit.Parameter('mu_1PE', 1.5, 1.0, 2, step_size=0.2)
#     sigma_num_1PE = zfit.Parameter('sigma_1PE', 1, 0.1, 2, floating=True)
#     mu_2PE = zfit.ComposedParameter("mu_2PE", lambda m: 2 * m, params=[mu_1PE])
#     sigma_num_2PE = zfit.Parameter('sigma_2PE', 1, 0.1, 2, floating=True)
#     frac_1PE = zfit.Parameter("frac_1pe", 0.6, lower=0, upper=1)
#     total_yield = zfit.Parameter("total_yield", len(ref_pmt_PulseCharge_quer), 
#                                  lower=len(ref_pmt_PulseCharge_quer)*0.5, 
#                                  upper=len(ref_pmt_PulseCharge_quer)*1.5)

#     gauss_1PE = zfit.pdf.Gauss(mu=mu_1PE, sigma=sigma_num_1PE, obs=obs)
#     gauss_2PE = zfit.pdf.Gauss(mu=mu_2PE, sigma=sigma_num_2PE, obs=obs)
#     sum_pdf = zfit.pdf.SumPDF([gauss_1PE, gauss_2PE], fracs=[frac_1PE], extended=total_yield)

#     nll = zfit.loss.ExtendedUnbinnedNLL(model=sum_pdf, data=ref_pmt_pc_data)
#     minimizer = zfit.minimize.Minuit()
#     result = minimizer.minimize(nll)
#     result.hesse()

#     mu_1PE_val = float(result.params['mu_1PE']["value"])
#     mean_err_1PE = float(result.params['mu_1PE']["hesse"]['error'])

#     elementary_charge = const.elementary_charge
#     gain_ref_pmt = (mu_1PE_val / elementary_charge) * 1e-12
#     gain_ref_pmt_err = (mean_err_1PE / elementary_charge) * 1e-12

#     print(f"Electron Charge: {elementary_charge} C")
#     print("*---------------------------------------*")
#     print(f"| GAIN: {gain_ref_pmt:.3e} ± {gain_ref_pmt_err:.3e}      |")
#     print("*---------------------------------------*")

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

timestamp = datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')

fig, ax = plt.subplots(figsize=(6.69, 2.8))

counts, bin_edges = np.histogram(PMT_PulseCharge_quer, bins=50)
bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
errors = np.sqrt(counts)

ax.errorbar(
    bin_centers,
    counts,
    yerr=errors,
    fmt='o',
    color="#ff4b4b",
    ecolor="#ff4b4b",
    markersize=4,
    capsize=2,
    alpha=0.9,
    label="PMT charge",
    linewidth=1.5,
    capthick=1.5
)

ax.set_title(f"{timestamp} | SN: {SN} | θ={theta}°, φ={phi}°", color=fg, pad=10)
ax.set_xlabel("Charge")
ax.set_ylabel("Events")

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

ax.legend(
    [f"PMT charge\nGain: {gain_PMT:.3e}"],
    loc="upper right",
    fontsize="small",
    framealpha=0.85,
    facecolor="#262730",
    edgecolor=grid,
)

plot_filename = os.path.join(output_dir, f"live_data_{input_datetime}_{SN}_theta{theta}_phi{phi}_charge.png")
fig.savefig(
    plot_filename,
    dpi=150,
    bbox_inches="tight",
)
plt.close(fig)

print(f"Plot saved to {plot_filename}")

gain_filename = os.path.join(output_dir, f"live_data_{input_datetime}_{SN}_theta{theta}_phi{phi}_GAIN.txt")
with open(gain_filename, 'w') as f:
    f.write(f"{gain_PMT:.3e}")

print(f"Gain saved to {gain_filename}")
print("Processing complete!")