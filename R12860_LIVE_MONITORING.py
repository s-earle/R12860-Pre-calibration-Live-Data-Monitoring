import sys
import os

import streamlit as st
from streamlit_autorefresh import st_autorefresh
from streamlit_extras.stylable_container import stylable_container
import subprocess
import time
import json
import threading
import signal
import re
import glob
from PIL import Image
import io
import pandas as pd

SYNC_DATA_DIR = "synced_data/"
os.makedirs(SYNC_DATA_DIR, exist_ok=True)

st.set_page_config(page_title="H-K R12860 Precalibration Live Data Monitoring", page_icon="📡", layout="wide")

st.title("H-K R12860 Precalibration Live Data Monitoring")

# ============================================================================
# GLOBAL PMT CONFIGURATION (Above Tabs)
# ============================================================================
st.header("PMT Configuration")
st.caption("Enter serial numbers for both PMTs before starting any scans")

col_pmt1, col_pmt2 = st.columns(2)

with col_pmt1:
    st.subheader("🔵 PMT 1")
    serial_number_pmt1 = st.text_input(
        "Serial Number (PMT 1):",
        value=st.session_state.get("serial_number_pmt1", ""),
        placeholder="e.g. SN12345",
        key="sn_pmt1_global"
    )
    st.session_state.serial_number_pmt1 = serial_number_pmt1
    
    if st.session_state.serial_number_pmt1.strip():
        st.success(f"✓ PMT 1: {st.session_state.serial_number_pmt1}")
    else:
        st.warning("⚠️ PMT 1: Not set")

with col_pmt2:
    st.subheader("🟢 PMT 2")
    serial_number_pmt2 = st.text_input(
        "Serial Number (PMT 2):",
        value=st.session_state.get("serial_number_pmt2", ""),
        placeholder="e.g. SN67890",
        key="sn_pmt2_global"
    )
    st.session_state.serial_number_pmt2 = serial_number_pmt2
    
    if st.session_state.serial_number_pmt2.strip():
        st.success(f"✓ PMT 2: {st.session_state.serial_number_pmt2}")
    else:
        st.warning("⚠️ PMT 2: Not set")

st.divider()

# ============================================================================
# TABS
# ============================================================================
st.markdown("""
<style>
    /* Increase font size of the tab labels */
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p {
        font-size: 20px;
    }
    /* Optional: Add padding to make tabs wider/taller */
    .stTabs [data-baseweb="tab"] {
        padding: 15px 20px;
    }
</style>
""", unsafe_allow_html=True)
tab1, tab2 = st.tabs(["⚡ High Voltage/Gain Check", "📊 Scanning Data"])

CONFIG_FILE = "executor_config.json"
STATUS_FILE = "executor_status.json"
EXECUTOR_PID_FILE = "executor_pid.txt"

# *---- Remove old data: --------------------------------------------------------------------------*
def cleanup_old_data(directory, max_age_hours):
    """Delete data files older than max_age_hours"""
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        return 0
    
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600
    deleted_count = 0
    
    png_files = glob.glob(f"{directory}/**/*.png", recursive=True)
    txt_files = glob.glob(f"{directory}/**/*_GAIN.txt", recursive=True)
    
    all_files = png_files + txt_files
    
    for file_path in all_files:
        try:
            file_age = current_time - os.path.getmtime(file_path)
            
            if file_age > max_age_seconds:
                os.remove(file_path)
                deleted_count += 1
        except Exception as e:
            st.warning(f"Could not delete {os.path.basename(file_path)}: {str(e)}")
    
    # Optionally clean up empty directories
    try:
        for root, dirs, files in os.walk(directory, topdown=False):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if not os.listdir(dir_path):  # If directory is empty
                        os.rmdir(dir_path)
                except:
                    pass
    except:
        pass
    
    return deleted_count


def archive_data_on_server(remote_host, remote_dir, archive_dir):
    """Move plots and text files from remote directory to archive directory"""
    
    mkdir_command = f"ssh {remote_host} 'mkdir -p {archive_dir}'"
    
    try:
        subprocess.run(
            mkdir_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        
        move_command = (
            f"ssh {remote_host} "
            f"'mv {remote_dir}/scan_output* {remote_dir}/*.log {archive_dir}/ 2>/dev/null || true'"
        )
        
        result = subprocess.run(
            move_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        return True, "Files archived successfully"
        
    except subprocess.TimeoutExpired:
        return False, "Archive operation timed out"
    except Exception as e:
        return False, f"Archive error: {str(e)}"

def flag_data_on_server(remote_host, remote_dir, flag_dir):
    """Move plots and text files from remote directory to flagged directory"""
    mkdir_command = f"ssh {remote_host} 'mkdir -p {flag_dir}'"
    
    try:
        subprocess.run(
            mkdir_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        
        move_command = (
            f"ssh {remote_host} "
            f"'mv {remote_dir}/scan_output* {remote_dir}/*.log {flag_dir}/ 2>/dev/null || true'"
        )
        
        result = subprocess.run(
            move_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        return True, "Files flagged successfully"
        
    except subprocess.TimeoutExpired:
        return False, "Flag operation timed out"
    except Exception as e:
        return False, f"Flag error: {str(e)}"


def sync_from_spartan(remote_host, remote_dir, local_dir="synced_data/", serial_number=None):
    """Execute rsync command to sync files from scan_output directories AND HV_analysis directories"""
    try:
        # Sync from scan_output directories (existing functionality)
        if serial_number:
            source_path = f"{remote_dir}/scan_output_*/{serial_number}/"
        else:
            source_path = f"{remote_dir}/scan_output_*/"
        
        rsync_command = (
            f"rsync -avz --include='*/' "
            f"--include='scan_output_*/' "
            f"--include='*_charge.png' "
            f"--include='*_GAIN.txt' "
            f"--exclude='*' "
            f"{remote_host}:{source_path} {local_dir}"
        )
        
        result = subprocess.run(
            rsync_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        # ALSO sync HV analysis plots
        if serial_number:
            hv_source_path = f"{remote_dir}/HV_CHECK/HV_output_*/{serial_number}/"
        else:
            hv_source_path = f"{remote_dir}/HV_CHECK/HV_output_*/"
        
        rsync_hv_command = (
            f"rsync -avz --include='*/' "
            f"--include='HV_output_*/' "
            f"--include='*/data_HV_*/' "
            f"--include='*_charge.png' "
            f"--include='*_GAIN.txt' "
            f"--include='*_gain_vs_hv_loglog.png' "
            f"--include='*_HV_at_gain_*.txt' "
            f"--exclude='*' "
            f"{remote_host}:{hv_source_path} {local_dir}"
        )
        
        result_hv = subprocess.run(
            rsync_hv_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0 or result_hv.returncode == 0:
            sn_msg = f" (SN: {serial_number})" if serial_number else ""
            return True, f"Synced from scan_output_* and HV_analysis_*{sn_msg}"
        else:
            return False, f"Rsync failed"
        
    except Exception as e:
        return False, f"Sync error: {str(e)}"


def parse_theta_phi_from_path(filepath):
    """Extract theta and phi values from filepath"""
    match = re.search(r'data_theta(\d+)_phi(\d+)', filepath)
    if match:
        theta = int(match.group(1))
        phi = int(match.group(2))
        return theta, phi
    return None, None

def get_slot_from_theta_phi(theta, phi):
    """Convert theta/phi coordinates to grid slot number
    
    Slot 0: [0, 0]
    Slots 1-20: theta in [10, 20, 30, 40, 50], phi in [0, 90, 180, 270]
    """
    if theta == 0 and phi == 0:
        return 0
    
    # For non-zero positions
    if theta in [10, 20, 30, 40, 50] and phi in [0, 90, 180, 270]:
        row = (theta // 10) - 1  # 10->0, 20->1, 30->2, 40->3, 50->4
        col = phi // 90          # 0->0, 90->1, 180->2, 270->3
        return 1 + (row * 4) + col
    
    return None

def find_files_by_theta_phi(sync_data_dir, theta, phi, serial_number=None):
    """Find PNG and TXT files for specific theta/phi coordinates"""
    if serial_number:
        pattern = f"{sync_data_dir}/**/{serial_number}/*_theta{theta}_phi{phi}_charge.png"
    else:
        pattern = f"{sync_data_dir}/**/data_theta{theta}_phi{phi}/*_theta{theta}_phi{phi}_charge.png"
    
    png_files = glob.glob(pattern, recursive=True)
    
    if not png_files:
        return None, None
    
    png_file = max(png_files, key=os.path.getmtime)
    gain_file = png_file.replace('_charge.png', '_GAIN.txt')
    
    if not os.path.exists(gain_file):
        gain_file = None
    
    return png_file, gain_file

def find_files_by_hv(sync_data_dir, serial_number, hv_value):
    """Find PNG and TXT files for specific HV value"""
    # Pattern 1: Try the actual structure first
    pattern = f"{sync_data_dir}/**/{serial_number}/data_HV_{hv_value}/*_HV_{hv_value}_charge.png"
    png_files = glob.glob(pattern, recursive=True)
    
    # Pattern 2: Fallback pattern
    if not png_files:
        pattern = f"{sync_data_dir}/**/*{serial_number}*HV_{hv_value}*charge.png"
        png_files = glob.glob(pattern, recursive=True)
    
    if not png_files:
        return None, None
    
    png_file = max(png_files, key=os.path.getmtime)
    gain_file = png_file.replace('_charge.png', '_GAIN.txt')
    
    if not os.path.exists(gain_file):
        gain_file = None
    
    return png_file, gain_file

def get_gain_value_from_file(gain_file_path):
    """Extract gain value from gain result file"""
    if not gain_file_path or not os.path.exists(gain_file_path):
        return "Gain: N/A"
    
    try:
        with open(gain_file_path, 'r') as f:
            gain_str = f.read().strip()
            try:
                gain_val = float(gain_str)
                return f"Gain: {gain_val:.2e}"
            except ValueError:
                return f"Gain: {gain_str}"
    except Exception as e:
        return "Gain: Error"

def load_status():
    """Load executor status from file"""
    if os.path.exists(STATUS_FILE):
        try:
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_config(config):
    """Save configuration to file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def start_background_executor():
    """Start the background executor as a subprocess"""
    try:
        for file in [CONFIG_FILE, STATUS_FILE, EXECUTOR_PID_FILE]:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except Exception as e:
                    print(f"Warning: Could not remove {file}: {e}")
        
        process = subprocess.Popen(
            [sys.executable, "background_executor.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        with open(EXECUTOR_PID_FILE, 'w') as f:
            f.write(str(process.pid))
        
        return True, process.pid
    except Exception as e:
        return False, str(e)

def check_executor_running():
    """Check if background executor is running"""
    if not os.path.exists(EXECUTOR_PID_FILE):
        return False
    
    try:
        with open(EXECUTOR_PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        if os.path.exists(EXECUTOR_PID_FILE):
            os.remove(EXECUTOR_PID_FILE)
        return False

def stop_background_executor():
    """Stop the background executor"""
    if not os.path.exists(EXECUTOR_PID_FILE):
        return True, "Executor not running"
    
    try:
        with open(EXECUTOR_PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        
        if os.path.exists(EXECUTOR_PID_FILE):
            os.remove(EXECUTOR_PID_FILE)
        
        return True, "Executor stopped"
    except Exception as e:
        return False, str(e)

def get_color_from_gain(gain_file_path, normal_range=(0.999e7, 1.049e7)):
    """
    Determine color based on gain value
    Returns: 'green' for healthy, 'red' for poor, 'yellow' for no data
    """
    if not gain_file_path or not os.path.exists(gain_file_path):
        return 'yellow'
    
    try:
        with open(gain_file_path, 'r') as f:
            gain_str = f.read().strip()
            gain_val = float(gain_str)
            
            min_normal, max_normal = normal_range
            
            if min_normal <= gain_val <= max_normal:
                return 'green'
            else:
                return 'red'
    except (ValueError, Exception):
        return 'yellow'
    
def find_hv_summary_plot(sync_data_dir, serial_number):
    """Find the gain vs HV summary plot for a specific SN"""
    # Look for the loglog plot generated by plot_gain_hv.py
    pattern = f"{sync_data_dir}/**/{serial_number}_gain_vs_hv_loglog.png"
    plot_files = glob.glob(pattern, recursive=True)
    
    if not plot_files:
        # Try alternate pattern
        pattern = f"{sync_data_dir}/**/*{serial_number}*gain_vs_hv*.png"
        plot_files = glob.glob(pattern, recursive=True)
    
    if not plot_files:
        return None
    
    # Return most recent file
    return max(plot_files, key=os.path.getmtime)

def find_hv_value_file(sync_data_dir, serial_number):
    """Find the HV value text file for gain = 1e7"""
    pattern = f"{sync_data_dir}/**/{serial_number}_HV_at_gain_*.txt"
    txt_files = glob.glob(pattern, recursive=True)
    
    if not txt_files:
        return None
    
    # Return most recent file
    return max(txt_files, key=os.path.getmtime)


# Initialize session state
if "remote_host" not in st.session_state:
    st.session_state.remote_host = "earles@spartan.hpc.unimelb.edu.au"

if "remote_directory" not in st.session_state:
    st.session_state.remote_directory = "/data/gpfs/projects/punim1378/earles/Precal_GUI"

if "remote_command" not in st.session_state:
    st.session_state.remote_command = "sbatch ./RUN_LIVE_MONITORING_ALL_TEST.slurm {SN}"

if "hv_remote_host" not in st.session_state:
    st.session_state.hv_remote_host = "earles@spartan.hpc.unimelb.edu.au"

if "hv_remote_directory" not in st.session_state:
    st.session_state.hv_remote_directory = "/data/gpfs/projects/punim1378/earles/Precal_GUI"

if "hv_remote_command" not in st.session_state:
    st.session_state.hv_remote_command = "sbatch ./HV_CHECK/RUN_HV_CHECK_TEST.slurm {SN} {HVNOMLL} {HVNOML} {HVNOM} {HVNOMH} {HVNOMHH}"

if "archive_directory" not in st.session_state:
    st.session_state.archive_directory = "/data/gpfs/projects/punim1378/earles/Precal_GUI/archive"

if "flag_directory" not in st.session_state:
    st.session_state.flag_directory = "/data/gpfs/projects/punim1378/earles/Precal_GUI/FLAG"

if "hv_archive_directory" not in st.session_state:
    st.session_state.hv_archive_directory = "/data/gpfs/projects/punim1378/earles/Precal_GUI/HV_CHECK/archive"

if "hv_flag_directory" not in st.session_state:
    st.session_state.hv_flag_directory = "/data/gpfs/projects/punim1378/earles/Precal_GUI/HV_CHECK/FLAG"

if "cleanup_time_hours" not in st.session_state:
    st.session_state.cleanup_time_hours = 24

if "selected_plot_pmt1" not in st.session_state:
    st.session_state.selected_plot_pmt1 = None

if "selected_plot_pmt2" not in st.session_state:
    st.session_state.selected_plot_pmt2 = None

if "show_overlay" not in st.session_state:
    st.session_state.show_overlay = False

if "example_plot_path" not in st.session_state:
    st.session_state.example_plot_path = "example_data/GOOD_DATA_charge.png"

if "serial_number_pmt1" not in st.session_state:
    st.session_state.serial_number_pmt1 = ""

if "serial_number_pmt2" not in st.session_state:
    st.session_state.serial_number_pmt2 = ""

if "hv_value_pmt1" not in st.session_state:
    st.session_state.hv_value_pmt1 = ""

if "hv_value_pmt2" not in st.session_state:
    st.session_state.hv_value_pmt2 = ""

# Automatic cleanup on page load
cleanup_old_data("synced_data/", st.session_state.cleanup_time_hours)

# Check background executor status
status = load_status()
is_running = bool(status and status.get('running', False))
executor_alive = check_executor_running()

# Auto-refresh when background executor is running
if is_running:
    st_autorefresh(interval=5000, key="datarefresh")

# CSS for grid buttons
st.markdown("""
<style>
    .grid-button-green {
        background-color: #28a745;
        color: white;
        padding: 20px 10px;
        text-align: center;
        border-radius: 5px;
        font-weight: bold;
        font-size: 14px;
        cursor: pointer;
        border: 2px solid transparent;
        transition: all 0.3s;
        min-height: 100px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    .grid-button-yellow {
        background-color: #ffc107;
        color: #333;
        padding: 20px 10px;
        text-align: center;
        border-radius: 5px;
        font-weight: bold;
        font-size: 14px;
        cursor: pointer;
        border: 2px solid transparent;
        transition: all 0.3s;
        min-height: 100px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    .grid-button-red {
        background-color: #dc3545;
        color: white;
        padding: 20px 10px;
        text-align: center;
        border-radius: 5px;
        font-weight: bold;
        font-size: 14px;
        cursor: pointer;
        border: 2px solid transparent;
        transition: all 0.3s;
        min-height: 100px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    .grid-button-green:hover, .grid-button-yellow:hover, .grid-button-red:hover {
        border-color: #0066cc;
        opacity: 0.9;
    }
    .no-data-box {
        background-color: #ffc107;
        color: #333;
        padding: 20px 10px;
        text-align: center;
        border-radius: 5px;
        font-weight: bold;
        font-size: 14px;
        border: 1px solid #e0a800;
        min-height: 100px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
    }
    .coordinate-label {
        font-size: 12px;
        margin-top: 5px;
        opacity: 0.9;
        font-weight: bold;
    }
    .gain-label {
        font-size: 11px;
        margin-top: 3px;
        opacity: 0.95;
        font-weight: bold;
    }
    .pmt-section {
        border: 2px solid #ddd;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 20px;
    }
    .pmt1-border {
        border-color: #007bff;
    }
    .pmt2-border {
        border-color: #28a745;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# HELPER FUNCTION FOR HV GRID DISPLAY
# ============================================================================
def display_hv_grid(pmt_id, serial_number, hv_values):
    """Display HV scan grid for a specific PMT"""
    
    hv_offset_mapping = {
        0: -100,      
        1: -50,     
        2: 0,
        3: 50,   
        4: 100   
    }

    def get_hv_label(hv_slot, hv_values):
        offset = hv_offset_mapping[hv_slot]
        hv_value = hv_values[hv_slot]
        if offset == 0:
            return f"Nominal\n{hv_value}V"
        else:
            sign = "+" if offset > 0 else ""
            return f"{sign}{offset}V\n({hv_value}V)"

    # Single row - all 5 HV points left to right
    cols = st.columns(5)
    for hv_slot in range(5):  # 0, 1, 2, 3, 4 corresponding to -100, -50, 0, +50, +100
        with cols[hv_slot]:
            hv_label = get_hv_label(hv_slot, hv_values)
            hv_val = hv_values[hv_slot]
            
            png_file, gain_file = find_files_by_hv("synced_data", serial_number, hv_val)
            
            # Simple button with label
            if st.button(hv_label, key=f"view_hv_{pmt_id}_{hv_slot}", use_container_width=True, type="primary"):
                if png_file:
                    if pmt_id == "pmt1":
                        st.session_state.selected_plot_pmt1 = png_file
                        st.session_state.selected_gain_pmt1 = get_gain_value_from_file(gain_file)
                    else:
                        st.session_state.selected_plot_pmt2 = png_file
                        st.session_state.selected_gain_pmt2 = get_gain_value_from_file(gain_file)
                else:
                    st.warning(f"No data available for {hv_label.replace(chr(10), ' ')}")
                    
# ============================================================================
# HELPER FUNCTION FOR FULL SCAN GRID DISPLAY
# ============================================================================
def display_scan_grid(pmt_id, serial_number):
    """Display 21-point scan grid for a specific PMT"""
    
    def get_coordinate_label(slot):
        """Convert slot to [theta, phi] label"""
        if slot == 0:
            return "[0, 0]"
        else:
            row_num = ((slot - 1) // 4) + 1
            col_num = (slot - 1) % 4
            theta = row_num * 10
            phi = col_num * 90
            return f"[{theta}, {phi}]"

    def get_theta_phi_from_slot(slot):
        """Convert slot to actual theta/phi values"""
        if slot == 0:
            return 0, 0
        else:
            row_num = ((slot - 1) // 4) + 1
            col_num = (slot - 1) % 4
            theta = row_num * 10
            phi = col_num * 90
            return theta, phi

    slot = 0

    # First row - single [0,0] button centered
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        theta, phi = get_theta_phi_from_slot(slot)
        coord_label = get_coordinate_label(slot)
        
        png_file, gain_file = find_files_by_theta_phi("synced_data", theta, phi, serial_number)
        
        if png_file:
            gain_value = get_gain_value_from_file(gain_file)
            color = get_color_from_gain(gain_file)
            status_text = {
                'green': 'Healthy',
                'yellow': 'No Data',
                'red': 'Poor'
            }.get(color, 'No Data')
            
            st.markdown(
                f"""
                <div class="grid-button-{color}">
                    <div>{status_text}</div>
                    <div class="gain-label">{gain_value}</div>
                    <div class="coordinate-label">{coord_label}</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            
            if st.button("View", key=f"view_scan_{pmt_id}_{slot}", use_container_width=True):
                if pmt_id == "pmt1":
                    st.session_state.selected_plot_pmt1 = png_file
                    st.session_state.selected_gain_pmt1 = gain_value
                else:
                    st.session_state.selected_plot_pmt2 = png_file
                    st.session_state.selected_gain_pmt2 = gain_value
        else:
            st.markdown(
                f"""
                <div class="no-data-box">
                    <div>⚠ No Data</div>
                    <div class="coordinate-label">{coord_label}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

    slot += 1

    # Remaining rows - 4 columns each
    for row in range(5):
        cols = st.columns(4)
        for col in cols:
            theta, phi = get_theta_phi_from_slot(slot)
            coord_label = get_coordinate_label(slot)

            with col:
                png_file, gain_file = find_files_by_theta_phi("synced_data", theta, phi, serial_number)
                
                if png_file:
                    gain_value = get_gain_value_from_file(gain_file)
                    color = get_color_from_gain(gain_file)
                    status_text = {
                        'green': 'Healthy',
                        'yellow': 'No Data',
                        'red': 'Poor'
                    }.get(color, 'No Data')
                    
                    st.markdown(
                        f"""
                        <div class="grid-button-{color}">
                            <div>{status_text}</div>
                            <div class="gain-label">{gain_value}</div>
                            <div class="coordinate-label">{coord_label}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    
                    if st.button("View", key=f"view_scan_{pmt_id}_{slot}", use_container_width=True):
                        if pmt_id == "pmt1":
                            st.session_state.selected_plot_pmt1 = png_file
                            st.session_state.selected_gain_pmt1 = gain_value
                        else:
                            st.session_state.selected_plot_pmt2 = png_file
                            st.session_state.selected_gain_pmt2 = gain_value
                
                else:
                    st.markdown(
                        f"""
                        <div class="no-data-box">
                            <div>⚠ No Data</div>
                            <div class="coordinate-label">{coord_label}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

            slot += 1

# ============================================================================
# TAB 1: HV SCAN (5 points × 2 PMTs)
# ============================================================================
with tab1:
    st.write("High Voltage Check - Dual PMT Mode")
    
    # Server Configuration for HV Check
    with st.expander("🔧 HV Check Server Configuration"):
        col_hv_config1, col_hv_config2 = st.columns(2)
        
        with col_hv_config1:
            st.session_state.hv_remote_host = st.text_input(
                "HV Remote Host",
                value=st.session_state.hv_remote_host,
                key="hv_remote_host_config"
            )
            st.session_state.hv_remote_directory = st.text_input(
                "HV Remote Directory",
                value=st.session_state.hv_remote_directory,
                key="hv_remote_dir_config"
            )
        
        with col_hv_config2:
            st.session_state.hv_remote_command = st.text_input(
                "HV Command to Execute",
                value=st.session_state.hv_remote_command,
                key="hv_remote_cmd_config",
                help="Use placeholders: {SN}, {HVNOMLL}, {HVNOML}, {HVNOM}, {HVNOMH}, {HVNOMHH}"
            )
            st.caption("Available placeholders: {SN}, {HVNOMLL}, {HVNOML}, {HVNOM}, {HVNOMH}, {HVNOMHH}")
        
        col_hv_arch1, col_hv_arch2 = st.columns(2)
        with col_hv_arch1:
            st.session_state.hv_archive_directory = st.text_input(
                "HV Archive Directory",
                value=st.session_state.hv_archive_directory,
                key="hv_archive_dir_config"
            )
        
        with col_hv_arch2:
            st.session_state.hv_flag_directory = st.text_input(
                "HV Flag Directory",
                value=st.session_state.hv_flag_directory,
                key="hv_flag_dir_config"
            )
    
    st.divider()

    # PMT 1 Section
    st.markdown('<div class="pmt-section pmt1-border">', unsafe_allow_html=True)
    st.subheader("🔵 PMT 1 - HV Configuration")
    
    col_left_pmt1, col_right_pmt1 = st.columns([1, 1.5])
    
    with col_left_pmt1:
        # HV Input for PMT 1
        hv_value_input_pmt1 = st.text_input(
            "Enter Nominal HV Value (PMT 1):",
            value=st.session_state.hv_value_pmt1,
            placeholder="e.g. 1800",
            help="Nominal high voltage value (without 'V'). Scans will be done at ±100V and ±50V from this value.",
            key="hv_input_pmt1"
        )
        
        st.session_state.hv_value_pmt1 = hv_value_input_pmt1
        
        try:
            nominal_hv_pmt1 = int(st.session_state.hv_value_pmt1.replace('V', '').replace('v', '').strip()) if st.session_state.hv_value_pmt1 else None
        except:
            nominal_hv_pmt1 = None
        
        if nominal_hv_pmt1:
            st.success(f"✓ Nominal HV set: {nominal_hv_pmt1}V")
            
            hv_offsets = [-100, -50, 0, 50, 100]  # HV_CHECK around nominal value range
            hv_values_pmt1 = [nominal_hv_pmt1 + offset for offset in hv_offsets]
            st.session_state.hv_scan_values_pmt1 = hv_values_pmt1
            
            table_data = {
                "Point": ["Point 1", "Point 2", "Point 3 (Nominal)", "Point 4", "Point 5"],
                "Offset": ["-100V", "-50V", "0V", "+50V", "+100V"],
                "HV Value": [f"{hv}V" for hv in hv_values_pmt1]
            }
            df = pd.DataFrame(table_data)
            st.table(df)
        else:
            st.warning("⚠️ Please enter a nominal HV value")
            st.session_state.hv_scan_values_pmt1 = None
        
        st.divider()
        
        # Run button for PMT 1
        with stylable_container(
            "green_button_pmt1",
            css_styles="""
            button {
                background-color: #007bff;
                color: white;
                border-color: #007bff;
                height: 80px;
                font-size: 18px;
                font-weight: bold;
                white-space: pre-line;
                line-height: 1.3;
            }
            button:hover {
                border-color: #0056b3;
                opacity: 0.9;
            }
            """,
        ):
            button_disabled_pmt1 = (is_running or not executor_alive or 
                                   not st.session_state.serial_number_pmt1.strip() or 
                                   not nominal_hv_pmt1)
            
            if st.button("RUN HV SCAN (PMT 1)\nStart Auto-Execute (5 runs)", 
                         type="primary", 
                         use_container_width=True,
                         disabled=button_disabled_pmt1, 
                         key="start_auto_pmt1"):
                st.info("Archiving existing data on server before starting...")
                success, message = archive_data_on_server(
                    st.session_state.hv_remote_host,
                    st.session_state.hv_remote_directory,
                    st.session_state.hv_archive_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.warning(f"⚠️ Archive warning: {message}")
                
                if st.session_state.hv_scan_values_pmt1:
                    hv_command = st.session_state.hv_remote_command.format(
                        SN=st.session_state.serial_number_pmt1,
                        HVNOMLL=st.session_state.hv_scan_values_pmt1[0],
                        HVNOML=st.session_state.hv_scan_values_pmt1[1],
                        HVNOM=st.session_state.hv_scan_values_pmt1[2],
                        HVNOMH=st.session_state.hv_scan_values_pmt1[3],
                        HVNOMHH=st.session_state.hv_scan_values_pmt1[4]
                    )
                
                config = {
                    'running': True,
                    'remote_host': st.session_state.hv_remote_host,
                    'hv_remote_directory': st.session_state.hv_remote_directory,
                    'hv_remote_command': hv_command,
                    'serial_number': st.session_state.serial_number_pmt1,
                    'hv_value': st.session_state.hv_value_pmt1,
                    'hv_scan_values': st.session_state.hv_scan_values_pmt1,
                    'pmt_id': 'pmt1',
                    'total_runs': 5,
                    'interval_seconds': 5,
                    'job_ids': []
                }
                save_config(config)
                st.success("HV Scan started for PMT 1!")
                time.sleep(2)
                st.rerun()
        
        st.caption("This will run a 5-point HV scan for PMT 1")
        # Stop button for PMT 1
        with stylable_container(
            "stop_button_hv_pmt1",
            css_styles="""
            button {
                background-color: #ff8c00;
                color: white;
                border-color: #ff8c00;
                height: 60px;
                font-size: 16px;
                font-weight: bold;
            }
            button:hover {
                border-color: #0066cc;
                opacity: 0.9;
            }
            """,
        ):
            if st.button("Stop HV Scan (PMT 1)", type="primary", use_container_width=True, disabled=not is_running, key="stop_hv_scan_pmt1"):
                if os.path.exists(CONFIG_FILE):
                    config = load_status()
                    if config:
                        config["running"] = False
                        save_config(config)

                if os.path.exists(STATUS_FILE):
                    status = load_status()
                    if status:
                        status["running"] = False
                        status["message"] = "Stopped by user"
                        with open(STATUS_FILE, "w") as f:
                            json.dump(status, f, indent=2)

                try:
                    cancel_cmd = f"ssh {st.session_state.hv_remote_host} scancel -u earles"
                    subprocess.run(
                        cancel_cmd,
                        shell=True,
                        check=True,
                        timeout=15
                    )
                    st.success("HV Scan stopped and SLURM jobs cancelled")
                except subprocess.CalledProcessError as e:
                    st.warning("HV Scan stopped, but scancel failed")

                time.sleep(1)
                st.rerun()
        
        st.divider()
        
        if st.button("Manual Sync (PMT 1)", type="secondary", key="manual_sync_pmt1"):
            st.info("Syncing PMT 1 from server...")
            
            sn = st.session_state.serial_number_pmt1 if st.session_state.serial_number_pmt1.strip() else None
            success, msg = sync_from_spartan(st.session_state.hv_remote_host, st.session_state.hv_remote_directory, serial_number=sn)
            
            if success:
                st.success(f"✅ {msg}")
            else:
                st.warning(f"⚠️ {msg}")
        
        st.divider()
        
        # Archive/Flag section for PMT 1 HV
        st.write("**Data Management (PMT 1)**")
        col_arch_pmt1, col_flag_pmt1 = st.columns(2)
        
        with col_arch_pmt1:
            if st.button("📦 Archive Data (PMT 1)", type="secondary", use_container_width=True, key="archive_hv_pmt1"):
                st.info("Archiving PMT 1 HV data...")
                success, message = archive_data_on_server(
                    st.session_state.hv_remote_host,
                    st.session_state.hv_remote_directory,
                    st.session_state.hv_archive_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
        
        with col_flag_pmt1:
            if st.button("⚠️ Flag as Abnormal (PMT 1)", type="primary", use_container_width=True, key="flag_hv_pmt1"):
                st.info("Flagging PMT 1 HV data...")
                success, message = flag_data_on_server(
                    st.session_state.hv_remote_host,
                    st.session_state.hv_remote_directory,
                    st.session_state.hv_flag_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
    
    with col_right_pmt1:
        st.subheader("Recent Scan Data (PMT 1)")
        st.caption("Shows recent HV scan results for PMT 1")
        
        if hasattr(st.session_state, 'hv_scan_values_pmt1') and st.session_state.hv_scan_values_pmt1 is not None:
            display_hv_grid("pmt1", st.session_state.serial_number_pmt1, st.session_state.hv_scan_values_pmt1)
            st.divider()
            st.subheader("Required HV Determination (PMT 1)")
            
            # Find and display the summary plot
            hv_value_file = find_hv_value_file("synced_data", st.session_state.serial_number_pmt1)
            summary_plot = find_hv_summary_plot("synced_data", st.session_state.serial_number_pmt1)
            
            
            if summary_plot and os.path.exists(summary_plot):
                import base64
                with open(summary_plot, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode()

                if hv_value_file and os.path.exists(hv_value_file):
                    try:
                        with open(hv_value_file, 'r') as f:
                            hv_required = f.read().strip()
                        st.markdown(f"""
                        <div style="text-align: center; padding: 15px; background-color: #cce5ff; border-radius: 10px; margin: 15px 0;">
                            <h3 style="color: #004085; margin: 0; font-weight: bold;">Required HV: {hv_required} V</h3>
                        </div>
                        """, unsafe_allow_html=True)
                    except:
                        pass
                
                st.markdown(f"""
                    <div style="width: 100%;">
                        <img src="data:image/png;base64,{img_data}" style="width: 100%; display: block;">
                    </div>
                """, unsafe_allow_html=True)
                
                st.caption(f"Last updated: {os.path.basename(summary_plot)}")
                
            else:
                st.info("📊 Summary plot will appear here after HV scan completes")
                st.caption("Run the HV scan and wait for all 5 points to be collected")

        else:
            st.info("Enter a nominal HV value to see scan points")
        
        # Display selected plot for PMT 1 if available
        if st.session_state.selected_plot_pmt1:
            st.divider()
            if os.path.exists(st.session_state.selected_plot_pmt1):
                st.subheader("Selected Plot (PMT 1)")
                import base64
                with open(st.session_state.selected_plot_pmt1, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode()
                
                st.markdown(f"""
                    <div style="width: 100%;">
                        <img src="data:image/png;base64,{img_data}" style="width: 100%; display: block;">
                    </div>
                """, unsafe_allow_html=True)
                
                st.caption(os.path.basename(st.session_state.selected_plot_pmt1))
                if hasattr(st.session_state, 'selected_gain_pmt1'):
                    st.info(st.session_state.selected_gain_pmt1)
                
                if st.button("Hide Plot", key="hide_plot_pmt1_inline", use_container_width=True):
                    st.session_state.selected_plot_pmt1 = None
                    st.session_state.selected_gain_pmt1 = None
                    st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # PMT 2 Section
    st.markdown('<div class="pmt-section pmt2-border">', unsafe_allow_html=True)
    st.subheader("🟢 PMT 2 - HV Configuration")
    
    col_left_pmt2, col_right_pmt2 = st.columns([1, 1.5])
    
    with col_left_pmt2:
        # HV Input for PMT 2
        hv_value_input_pmt2 = st.text_input(
            "Enter Nominal HV Value (PMT 2):",
            value=st.session_state.hv_value_pmt2,
            placeholder="e.g. 1800",
            help="Nominal high voltage value (without 'V'). Scans will be done at ±100V and ±50V from this value.",
            key="hv_input_pmt2"
        )
        
        st.session_state.hv_value_pmt2 = hv_value_input_pmt2
        
        try:
            nominal_hv_pmt2 = int(st.session_state.hv_value_pmt2.replace('V', '').replace('v', '').strip()) if st.session_state.hv_value_pmt2 else None
        except:
            nominal_hv_pmt2 = None
        
        if nominal_hv_pmt2:
            st.success(f"✓ Nominal HV set: {nominal_hv_pmt2}V")
            
            hv_offsets = [-100, -50, 0, 50, 100]
            hv_values_pmt2 = [nominal_hv_pmt2 + offset for offset in hv_offsets]
            st.session_state.hv_scan_values_pmt2 = hv_values_pmt2
            
            table_data = {
                "Point": ["Point 1", "Point 2", "Point 3 (Nominal)", "Point 4", "Point 5"],
                "Offset": ["-100V", "-50V", "0V", "+50V", "+100V"],
                "HV Value": [f"{hv}V" for hv in hv_values_pmt2]
            }
            df = pd.DataFrame(table_data)
            st.table(df)
        else:
            st.warning("⚠️ Please enter a nominal HV value")
            st.session_state.hv_scan_values_pmt2 = None
        
        st.divider()
        
        # Run button for PMT 2
        with stylable_container(
            "green_button_pmt2",
            css_styles="""
            button {
                background-color: #28a745;
                color: white;
                border-color: #28a745;
                height: 80px;
                font-size: 18px;
                font-weight: bold;
                white-space: pre-line;
                line-height: 1.3;
            }
            button:hover {
                border-color: #1e7e34;
                opacity: 0.9;
            }
            """,
        ):
            button_disabled_pmt2 = (is_running or not executor_alive or 
                                   not st.session_state.serial_number_pmt2.strip() or 
                                   not nominal_hv_pmt2)
            
            if st.button("RUN HV SCAN (PMT 2)\nStart Auto-Execute (5 runs)", 
                         type="primary", 
                         use_container_width=True,
                         disabled=button_disabled_pmt2, 
                         key="start_auto_pmt2"):
                st.info("Archiving existing data on server before starting...")
                success, message = archive_data_on_server(
                    st.session_state.hv_remote_host,
                    st.session_state.hv_remote_directory,
                    st.session_state.hv_archive_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.warning(f"⚠️ Archive warning: {message}")
                
                if st.session_state.hv_scan_values_pmt2:
                    hv_command = st.session_state.hv_remote_command.format(
                        SN=st.session_state.serial_number_pmt2,
                        HVNOMLL=st.session_state.hv_scan_values_pmt2[0],
                        HVNOML=st.session_state.hv_scan_values_pmt2[1],
                        HVNOM=st.session_state.hv_scan_values_pmt2[2],
                        HVNOMH=st.session_state.hv_scan_values_pmt2[3],
                        HVNOMHH=st.session_state.hv_scan_values_pmt2[4]
                    )
                
                config = {
                    'running': True,
                    'remote_host': st.session_state.hv_remote_host,
                    'hv_remote_directory': st.session_state.hv_remote_directory,
                    'hv_remote_command': hv_command,
                    'serial_number': st.session_state.serial_number_pmt2,
                    'hv_value': st.session_state.hv_value_pmt2,
                    'hv_scan_values': st.session_state.hv_scan_values_pmt2,
                    'pmt_id': 'pmt2',
                    'total_runs': 5,
                    'interval_seconds': 5,
                    'job_ids': []
                }
                save_config(config)
                st.success("HV Scan started for PMT 2!")
                time.sleep(2)
                st.rerun()
        
        st.caption("This will run a 5-point HV scan for PMT 2")
        # Stop button for PMT 2
        with stylable_container(
            "stop_button_hv_pmt2",
            css_styles="""
            button {
                background-color: #ff8c00;
                color: white;
                border-color: #ff8c00;
                height: 60px;
                font-size: 16px;
                font-weight: bold;
            }
            button:hover {
                border-color: #0066cc;
                opacity: 0.9;
            }
            """,
        ):
            if st.button("Stop HV Scan (PMT 2)", type="primary", use_container_width=True, disabled=not is_running, key="stop_hv_scan_pmt2"):
                if os.path.exists(CONFIG_FILE):
                    config = load_status()
                    if config:
                        config["running"] = False
                        save_config(config)

                if os.path.exists(STATUS_FILE):
                    status = load_status()
                    if status:
                        status["running"] = False
                        status["message"] = "Stopped by user"
                        with open(STATUS_FILE, "w") as f:
                            json.dump(status, f, indent=2)

                try:
                    cancel_cmd = f"ssh {st.session_state.hv_remote_host} scancel -u earles"
                    subprocess.run(
                        cancel_cmd,
                        shell=True,
                        check=True,
                        timeout=15
                    )
                    st.success("HV Scan stopped and SLURM jobs cancelled")
                except subprocess.CalledProcessError as e:
                    st.warning("HV Scan stopped, but scancel failed")

                time.sleep(1)
                st.rerun()
        
        if st.button("Manual Sync (PMT 2)", type="secondary", key="manual_sync_pmt2"):
            st.info("Syncing PMT 2 from server...")
            
            sn = st.session_state.serial_number_pmt2 if st.session_state.serial_number_pmt2.strip() else None
            success, msg = sync_from_spartan(st.session_state.hv_remote_host, st.session_state.hv_remote_directory, serial_number=sn)
            
            if success:
                st.success(f"✅ {msg}")
            else:
                st.warning(f"⚠️ {msg}")
        
        st.divider()
        
        # Archive/Flag section for PMT 2 HV
        st.write("**Data Management (PMT 2)**")
        col_arch_pmt2, col_flag_pmt2 = st.columns(2)
        
        with col_arch_pmt2:
            if st.button("📦 Archive Data (PMT 2)", type="secondary", use_container_width=True, key="archive_hv_pmt2"):
                st.info("Archiving PMT 2 HV data...")
                success, message = archive_data_on_server(
                    st.session_state.hv_remote_host,
                    st.session_state.hv_remote_directory,
                    st.session_state.hv_archive_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
        
        with col_flag_pmt2:
            if st.button("⚠️ Flag as Abnormal (PMT 2)", type="primary", use_container_width=True, key="flag_hv_pmt2"):
                st.info("Flagging PMT 2 HV data...")
                success, message = flag_data_on_server(
                    st.session_state.hv_remote_host,
                    st.session_state.hv_remote_directory,
                    st.session_state.hv_flag_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
    
    with col_right_pmt2:
        st.subheader("Recent Scan Data (PMT 2)")
        st.caption("Shows recent HV scan results for PMT 2")
        
        if hasattr(st.session_state, 'hv_scan_values_pmt2') and st.session_state.hv_scan_values_pmt2 is not None:
            display_hv_grid("pmt2", st.session_state.serial_number_pmt2, st.session_state.hv_scan_values_pmt2)
            st.divider()
            st.subheader("Required HV Determination(PMT 2)")
            
            # Find and display the summary plot
            hv_value_file = find_hv_value_file("synced_data", st.session_state.serial_number_pmt2)
            summary_plot = find_hv_summary_plot("synced_data", st.session_state.serial_number_pmt2)
            
            
            if summary_plot and os.path.exists(summary_plot):
                import base64
                with open(summary_plot, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode()

                # Display HV value for gain = 1e7 if available
                if hv_value_file and os.path.exists(hv_value_file):
                    try:
                        with open(hv_value_file, 'r') as f:
                            hv_required = f.read().strip()
                        st.markdown(f"""
                        <div style="text-align: center; padding: 15px; background-color: #d4edda; border-radius: 10px; margin: 15px 0;">
                            <h3 style="color: #155724; margin: 0; font-weight: bold;">Required HV: {hv_required} V</h3>
                        </div>
                        """, unsafe_allow_html=True)
                    except:
                        pass
                
                st.markdown(f"""
                    <div style="width: 100%;">
                        <img src="data:image/png;base64,{img_data}" style="width: 100%; display: block;">
                    </div>
                """, unsafe_allow_html=True)
                
                st.caption(f"Last updated: {os.path.basename(summary_plot)}")
                
            else:
                st.info("📊 Summary plot will appear here after HV scan completes")
                st.caption("Run the HV scan and wait for all 5 points to be collected")

        else:
            st.info("Enter a nominal HV value to see scan points")
        
        # Display selected plot for PMT 2 if available
        if st.session_state.selected_plot_pmt2:
            st.divider()
            if os.path.exists(st.session_state.selected_plot_pmt2):
                st.subheader("Selected Plot (PMT 2)")
                import base64
                with open(st.session_state.selected_plot_pmt2, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode()
                
                st.markdown(f"""
                    <div style="width: 100%;">
                        <img src="data:image/png;base64,{img_data}" style="width: 100%; display: block;">
                    </div>
                """, unsafe_allow_html=True)
                
                st.caption(os.path.basename(st.session_state.selected_plot_pmt2))
                if hasattr(st.session_state, 'selected_gain_pmt2'):
                    st.info(st.session_state.selected_gain_pmt2)
                
                if st.button("Hide Plot", key="hide_plot_pmt2_inline", use_container_width=True):
                    st.session_state.selected_plot_pmt2 = None
                    st.session_state.selected_gain_pmt2 = None
                    st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Display selected plots side by side (REMOVE THIS ENTIRE SECTION BELOW)
    
    
# ============================================================================
# TAB 2: FULL SCAN (21 points × 2 PMTs)
# ============================================================================
with tab2:
    st.write("Full Scan - Dual PMT Mode")
    st.caption("Run complete 21-point scans for both PMTs")
    
    # Background Executor Status
    st.sidebar.header("Background Executor")
    if executor_alive:
        st.sidebar.success("✅ Running")
    else:
        st.sidebar.warning("⚠️ Not Running")

    col_exec1, col_exec2 = st.sidebar.columns(2)
    with col_exec1:
        if st.button("▶️ Start", disabled=executor_alive, use_container_width=True, key="start_exec_tab2"):
            success, result = start_background_executor()
            if success:
                st.success(f"✅ Executor started (PID: {result})")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ Failed to start: {result}")

    with col_exec2:
        if st.button("⏹️ Stop", disabled=not executor_alive, use_container_width=True, key="stop_exec_tab2"):
            success, msg = stop_background_executor()
            if success:
                st.success(f"✅ {msg}")
                time.sleep(1)
                st.rerun()
            else:
                st.error(f"❌ Failed: {msg}")

    if st.sidebar.button("Reset All", type="secondary", use_container_width=True, key="reset_tab2"):
        stop_background_executor()
        
        for file in [CONFIG_FILE, STATUS_FILE, EXECUTOR_PID_FILE]:
            if os.path.exists(file):
                os.remove(file)
        
        st.sidebar.success("Reset complete!")
        time.sleep(1)
        st.rerun()

    st.sidebar.divider()

    # Server Configuration for Data Monitoring
    with st.expander("🔧 Data Monitoring Server Configuration"):
        col_dm_config1, col_dm_config2 = st.columns(2)
        
        with col_dm_config1:
            st.session_state.remote_host = st.text_input(
                "Remote Host",
                value=st.session_state.remote_host,
                key="remote_host_tab2"
            )
            st.session_state.remote_directory = st.text_input(
                "Remote Directory",
                value=st.session_state.remote_directory,
                key="remote_dir_tab2"
            )
        
        with col_dm_config2:
            st.session_state.remote_command = st.text_input(
                "Command to Execute",
                value=st.session_state.remote_command,
                key="remote_cmd_tab2",
                help="Use placeholder: {SN}"
            )
            st.caption("Available placeholder: {SN}")
        
        col_dm_arch1, col_dm_arch2 = st.columns(2)
        with col_dm_arch1:
            st.session_state.archive_directory = st.text_input(
                "Archive Directory",
                value=st.session_state.archive_directory,
                key="archive_dir_tab2"
            )
        
        with col_dm_arch2:
            st.session_state.flag_directory = st.text_input(
                "Flag Directory",
                value=st.session_state.flag_directory,
                key="flag_dir_tab2"
            )

    with st.sidebar.expander("Data Cleanup"):
        cleanup_hours = st.number_input(
            "Delete data files older than (hours)",
            min_value=1,
            max_value=720,
            value=st.session_state.cleanup_time_hours,
            step=1,
            key="cleanup_hours_tab2"
        )
        st.session_state.cleanup_time_hours = cleanup_hours
        
        if st.button("Clear Old Data Now", key="clear_old_tab2"):
            deleted = cleanup_old_data("synced_data/", st.session_state.cleanup_time_hours)
            if deleted > 0:
                st.success(f"Deleted {deleted} old data file(s)")
            else:
                st.info("No old files to delete")
        
        if st.button("Clear ALL Data Now", type="primary", key="clear_all_tab2"):
            if os.path.exists("synced_data/"):
                count = 0
                
                all_png_files = glob.glob("synced_data/**/*.png", recursive=True)
                all_txt_files = glob.glob("synced_data/**/*.txt", recursive=True)
                
                for f in all_png_files:
                    try:
                        os.remove(f)
                        count += 1
                    except Exception as e:
                        st.error(f"Error deleting {f}: {str(e)}")
                
                for f in all_txt_files:
                    try:
                        os.remove(f)
                        count += 1
                    except Exception as e:
                        st.error(f"Error deleting {f}: {str(e)}")
                
                try:
                    for root, dirs, files in os.walk("synced_data/", topdown=False):
                        for dir_name in dirs:
                            dir_path = os.path.join(root, dir_name)
                            try:
                                if not os.listdir(dir_path):
                                    os.rmdir(dir_path)
                            except:
                                pass
                except:
                    pass
                
                st.success(f"Deleted all {count} file(s)")
            else:
                st.warning("Data directory doesn't exist")

    if is_running:
        st.info(f"Background executor running: {status.get('message', 'Processing...')}")
        if status.get('total'):
            progress = status.get('completed', 0) / status['total']
            st.progress(progress)
            st.write(f"Completed: {status.get('completed', 0)}/{status['total']}")

    st.divider()

    # PMT 1 Section
    st.markdown('<div class="pmt-section pmt1-border">', unsafe_allow_html=True)
    st.subheader("🔵 PMT 1 - Full Scan Configuration")
    
    col_left_pmt1_scan, col_right_pmt1_scan = st.columns([1, 1.5])
    
    with col_left_pmt1_scan:
        st.write(f"**Serial Number:** {st.session_state.serial_number_pmt1 or 'Not set'}")
        
        if not st.session_state.serial_number_pmt1.strip():
            st.warning("⚠️ Please set serial number at the top of the page")
        
        st.divider()
        
        with stylable_container(
            "scan_button_pmt1",
            css_styles="""
            button {
                background-color: #007bff;
                color: white;
                border-color: #007bff;
                height: 80px;
                font-size: 18px;
                font-weight: bold;
                white-space: pre-line;
                line-height: 1.3;
            }
            button:hover {
                border-color: #0056b3;
                opacity: 0.9;
            }
            """,
        ):
            button_disabled_scan_pmt1 = (is_running or not executor_alive or 
                                        not st.session_state.serial_number_pmt1.strip())
            
            if st.button("RUN FULL SCAN (PMT 1)\nStart Auto-Execute (21 runs)", 
                         type="primary", 
                         use_container_width=True,
                         disabled=button_disabled_scan_pmt1, 
                         key="start_scan_pmt1"):
                st.info("Archiving existing data on server before starting...")
                success, message = archive_data_on_server(
                    st.session_state.remote_host,
                    st.session_state.remote_directory,
                    st.session_state.archive_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.warning(f"⚠️ Archive warning: {message}")
                
                # Format command with serial number
                formatted_command = st.session_state.remote_command.format(
                    SN=st.session_state.serial_number_pmt1
                )
                
                config = {
                    'running': True,
                    'remote_host': st.session_state.remote_host,
                    'remote_directory': st.session_state.remote_directory,
                    'remote_command': formatted_command,
                    'serial_number': st.session_state.serial_number_pmt1,
                    'pmt_id': 'pmt1',
                    'total_runs': 21,
                    'interval_seconds': 5,
                    'job_ids': []
                }
                save_config(config)
                st.success("Full scan started for PMT 1!")
                time.sleep(2)
                st.rerun()
        
        st.caption("This will run a complete 21-point scan for PMT 1")
        
        with stylable_container(
            "stop_button_pmt1",
            css_styles="""
            button {
                background-color: #ff8c00;
                color: white;
                border-color: #ff8c00;
                height: 60px;
                font-size: 16px;
                font-weight: bold;
            }
            button:hover {
                border-color: #0066cc;
                opacity: 0.9;
            }
            """,
        ):
            if st.button("Stop Scan (PMT 1)", type="primary", use_container_width=True, disabled=not is_running, key="stop_scan_pmt1"):
                if os.path.exists(CONFIG_FILE):
                    config = load_status()
                    if config:
                        config["running"] = False
                        save_config(config)

                if os.path.exists(STATUS_FILE):
                    status = load_status()
                    if status:
                        status["running"] = False
                        status["message"] = "Stopped by user"
                        with open(STATUS_FILE, "w") as f:
                            json.dump(status, f, indent=2)

                try:
                    cancel_cmd = f"ssh {st.session_state.remote_host} scancel -u earles"
                    subprocess.run(
                        cancel_cmd,
                        shell=True,
                        check=True,
                        timeout=15
                    )
                    st.success("Scan stopped and SLURM jobs cancelled")
                except subprocess.CalledProcessError as e:
                    st.warning("Scan stopped, but scancel failed")

                time.sleep(1)
                st.rerun()
        
        st.divider()
        
        if st.button("Manual Sync (PMT 1 Scan)", type="secondary", key="manual_sync_scan_pmt1"):
            st.info("Syncing PMT 1 scan data from server...")
            
            sn = st.session_state.serial_number_pmt1 if st.session_state.serial_number_pmt1.strip() else None
            success, msg = sync_from_spartan(st.session_state.remote_host, st.session_state.remote_directory, serial_number=sn)
            
            if success:
                st.success(f"✅ {msg}")
            else:
                st.warning(f"⚠️ {msg}")
        
        st.divider()
        
        # Archive/Flag section for PMT 1 Scan
        st.write("**Data Management (PMT 1)**")
        col_arch_scan_pmt1, col_flag_scan_pmt1 = st.columns(2)
        
        with col_arch_scan_pmt1:
            if st.button("📦 Archive Data (PMT 1)", type="secondary", use_container_width=True, key="archive_scan_pmt1"):
                st.info("Archiving PMT 1 scan data...")
                success, message = archive_data_on_server(
                    st.session_state.remote_host,
                    st.session_state.remote_directory,
                    st.session_state.archive_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
        
        with col_flag_scan_pmt1:
            if st.button("⚠️ Flag as Abnormal (PMT 1)", type="primary", use_container_width=True, key="flag_scan_pmt1"):
                st.info("Flagging PMT 1 scan data...")
                success, message = flag_data_on_server(
                    st.session_state.remote_host,
                    st.session_state.remote_directory,
                    st.session_state.flag_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
    
    with col_right_pmt1_scan:
        st.subheader("Recent Scan Data (PMT 1)")
        st.caption("Shows recent 21-point scan results for PMT 1")
        
        if st.session_state.serial_number_pmt1.strip():
            display_scan_grid("pmt1", st.session_state.serial_number_pmt1)
        else:
            st.info("Set serial number to view scan data")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.divider()
    
    # PMT 2 Section
    st.markdown('<div class="pmt-section pmt2-border">', unsafe_allow_html=True)
    st.subheader("🟢 PMT 2 - Full Scan Configuration")
    
    col_left_pmt2_scan, col_right_pmt2_scan = st.columns([1, 1.5])
    
    with col_left_pmt2_scan:
        st.write(f"**Serial Number:** {st.session_state.serial_number_pmt2 or 'Not set'}")
        
        if not st.session_state.serial_number_pmt2.strip():
            st.warning("⚠️ Please set serial number at the top of the page")
        
        st.divider()
        
        with stylable_container(
            "scan_button_pmt2",
            css_styles="""
            button {
                background-color: #28a745;
                color: white;
                border-color: #28a745;
                height: 80px;
                font-size: 18px;
                font-weight: bold;
                white-space: pre-line;
                line-height: 1.3;
            }
            button:hover {
                border-color: #1e7e34;
                opacity: 0.9;
            }
            """,
        ):
            button_disabled_scan_pmt2 = (is_running or not executor_alive or 
                                        not st.session_state.serial_number_pmt2.strip())
            
            if st.button("RUN FULL SCAN (PMT 2)\nStart Auto-Execute (21 runs)", 
                         type="primary", 
                         use_container_width=True,
                         disabled=button_disabled_scan_pmt2, 
                         key="start_scan_pmt2"):
                st.info("Archiving existing data on server before starting...")
                success, message = archive_data_on_server(
                    st.session_state.remote_host,
                    st.session_state.remote_directory,
                    st.session_state.archive_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.warning(f"⚠️ Archive warning: {message}")
                
                # Format command with serial number
                formatted_command = st.session_state.remote_command.format(
                    SN=st.session_state.serial_number_pmt2
                )
                
                config = {
                    'running': True,
                    'remote_host': st.session_state.remote_host,
                    'remote_directory': st.session_state.remote_directory,
                    'remote_command': formatted_command,
                    'serial_number': st.session_state.serial_number_pmt2,
                    'pmt_id': 'pmt2',
                    'total_runs': 21,
                    'interval_seconds': 5,
                    'job_ids': []
                }
                save_config(config)
                st.success("Full scan started for PMT 2!")
                time.sleep(2)
                st.rerun()
        
        st.caption("This will run a complete 21-point scan for PMT 2")
        
        with stylable_container(
            "stop_button_pmt2",
            css_styles="""
            button {
                background-color: #ff8c00;
                color: white;
                border-color: #ff8c00;
                height: 60px;
                font-size: 16px;
                font-weight: bold;
            }
            button:hover {
                border-color: #0066cc;
                opacity: 0.9;
            }
            """,
        ):
            if st.button("Stop Scan (PMT 2)", type="primary", use_container_width=True, disabled=not is_running, key="stop_scan_pmt2"):
                if os.path.exists(CONFIG_FILE):
                    config = load_status()
                    if config:
                        config["running"] = False
                        save_config(config)

                if os.path.exists(STATUS_FILE):
                    status = load_status()
                    if status:
                        status["running"] = False
                        status["message"] = "Stopped by user"
                        with open(STATUS_FILE, "w") as f:
                            json.dump(status, f, indent=2)

                try:
                    cancel_cmd = f"ssh {st.session_state.remote_host} scancel -u earles"
                    subprocess.run(
                        cancel_cmd,
                        shell=True,
                        check=True,
                        timeout=15
                    )
                    st.success("Scan stopped and SLURM jobs cancelled")
                except subprocess.CalledProcessError as e:
                    st.warning("Scan stopped, but scancel failed")

                time.sleep(1)
                st.rerun()
        
        st.divider()
        
        if st.button("Manual Sync (PMT 2 Scan)", type="secondary", key="manual_sync_scan_pmt2"):
            st.info("Syncing PMT 2 scan data from server...")
            
            sn = st.session_state.serial_number_pmt2 if st.session_state.serial_number_pmt2.strip() else None
            success, msg = sync_from_spartan(st.session_state.remote_host, st.session_state.remote_directory, serial_number=sn)
            
            if success:
                st.success(f"✅ {msg}")
            else:
                st.warning(f"⚠️ {msg}")
        
        st.divider()
        
        # Archive/Flag section for PMT 2 Scan
        st.write("**Data Management (PMT 2)**")
        col_arch_scan_pmt2, col_flag_scan_pmt2 = st.columns(2)
        
        with col_arch_scan_pmt2:
            if st.button("📦 Archive Data (PMT 2)", type="secondary", use_container_width=True, key="archive_scan_pmt2"):
                st.info("Archiving PMT 2 scan data...")
                success, message = archive_data_on_server(
                    st.session_state.remote_host,
                    st.session_state.remote_directory,
                    st.session_state.archive_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
        
        with col_flag_scan_pmt2:
            if st.button("⚠️ Flag as Abnormal (PMT 2)", type="primary", use_container_width=True, key="flag_scan_pmt2"):
                st.info("Flagging PMT 2 scan data...")
                success, message = flag_data_on_server(
                    st.session_state.remote_host,
                    st.session_state.remote_directory,
                    st.session_state.flag_directory
                )
                
                if success:
                    st.success(f"✅ {message}")
                else:
                    st.error(f"❌ {message}")
    
    with col_right_pmt2_scan:
        st.subheader("Recent Scan Data (PMT 2)")
        st.caption("Shows recent 21-point scan results for PMT 2")
        
        if st.session_state.serial_number_pmt2.strip():
            display_scan_grid("pmt2", st.session_state.serial_number_pmt2)
        else:
            st.info("Set serial number to view scan data")
    
    st.markdown('</div>', unsafe_allow_html=True)
    
    # Display selected plots side by side
    if st.session_state.selected_plot_pmt1 or st.session_state.selected_plot_pmt2:
        st.divider()
        st.subheader("Selected Plots")
        
        cols = st.columns(2)
        
        # PMT 1 plot
        with cols[0]:
            if st.session_state.selected_plot_pmt1:
                if os.path.exists(st.session_state.selected_plot_pmt1):
                    st.write("🔵 PMT 1")
                    import base64
                    with open(st.session_state.selected_plot_pmt1, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode()
                    
                    st.markdown(f"""
                        <div style="width: 100%;">
                            <img src="data:image/png;base64,{img_data}" style="width: 100%; display: block;">
                        </div>
                    """, unsafe_allow_html=True)
                    
                    st.caption(os.path.basename(st.session_state.selected_plot_pmt1))
                    if hasattr(st.session_state, 'selected_gain_pmt1'):
                        st.info(st.session_state.selected_gain_pmt1)
                    
                    if st.button("Hide Plot (PMT 1)", key="hide_plot_pmt1_tab2"):
                        st.session_state.selected_plot_pmt1 = None
                        st.session_state.selected_gain_pmt1 = None
                        st.rerun()
        
        # PMT 2 plot
        with cols[1]:
            if st.session_state.selected_plot_pmt2:
                if os.path.exists(st.session_state.selected_plot_pmt2):
                    st.write("🟢 PMT 2")
                    import base64
                    with open(st.session_state.selected_plot_pmt2, "rb") as f:
                        img_data = base64.b64encode(f.read()).decode()
                    
                    st.markdown(f"""
                        <div style="width: 100%;">
                            <img src="data:image/png;base64,{img_data}" style="width: 100%; display: block;">
                        </div>
                    """, unsafe_allow_html=True)
                    
                    st.caption(os.path.basename(st.session_state.selected_plot_pmt2))
                    if hasattr(st.session_state, 'selected_gain_pmt2'):
                        st.info(st.session_state.selected_gain_pmt2)
                    
                    if st.button("Hide Plot (PMT 2)", key="hide_plot_pmt2_tab2"):
                        st.session_state.selected_plot_pmt2 = None
                        st.session_state.selected_gain_pmt2 = None
                        st.rerun()