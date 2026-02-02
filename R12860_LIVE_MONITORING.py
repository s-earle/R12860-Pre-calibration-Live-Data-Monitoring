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

SYNC_DATA_DIR = "synced_data/"
os.makedirs(SYNC_DATA_DIR, exist_ok=True)

st.set_page_config(page_title="H-K R12860 Precalibration Live Data Monitoring", page_icon="🔄", layout="wide")


st.title("H-K R12860 Precalibration Live Data Monitoring")

st.write("Sync with server cluster")

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
            # f"'mv {remote_dir}/*.log {archive_dir}/ 2>/dev/null || true'"
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
    # Create flag directory if it doesn't exist
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
            # f"'mv {remote_dir}/*.log {flag_dir}/ 2>/dev/null || true'"
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




# *---- Performing sync: --------------------------------------------------------------------------*
# |     Here we look to a remote server (currently Spartan at unimelb) and sync the data outputs   |
# |     from a specific directory. The code is written to use a directory I (S.Earle) made         |
# |     however this can be changed in the GUI or changed here in the backend code.                |
# |     We could as easily use sukap or just local                                                 |
# *------------------------------------------------------------------------------------------------*
def sync_from_spartan(remote_host, remote_dir, local_dir="synced_data/", serial_number=None):
    """Execute rsync command to sync files from scan_output directories"""
    try:
        # If serial number provided, sync only that SN's directory from all scan_output dirs
        if serial_number:
            source_path = f"{remote_dir}/scan_output_*/{serial_number}/"
        else:
            source_path = f"{remote_dir}/scan_output_*/"
        
        # Sync all files from scan_output directories
        # Updated to match new filenames: *_charge.png and *_GAIN.txt
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
        
        if result.returncode == 0:
            sn_msg = f" (SN: {serial_number})" if serial_number else ""
            return True, f"Synced from scan_output_*{sn_msg}"
        else:
            return False, f"Rsync failed with code {result.returncode}"
        
    except Exception as e:
        return False, f"Sync error: {str(e)}"


def parse_theta_phi_from_path(filepath):
    """Extract theta and phi values from filepath"""
    # Match pattern: data_theta{theta}_phi{phi}
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

def find_files_by_theta_phi(sync_data_dir, theta, phi):
    """Find PNG and TXT files for specific theta/phi coordinates"""
    # Search pattern for the specific coordinates - updated for new naming
    pattern = f"{sync_data_dir}/**/data_theta{theta}_phi{phi}/*_theta{theta}_phi{phi}_charge.png"
    png_files = glob.glob(pattern, recursive=True)
    
    if not png_files:
        return None, None
    
    # Get the most recent file
    png_file = max(png_files, key=os.path.getmtime)
    
    # Replace _charge.png with _GAIN.txt
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

# *---- Background executor: ----------------------------------------------------------------------*
# |     This allows the GUI to be interfaced with meanwhile automating the data processing and     |
# |     sync functions.                                                                            |
# *------------------------------------------------------------------------------------------------*
def start_background_executor():
    """Start the background executor as a subprocess"""
    try:
        # Clean up old status files before starting
        for file in [CONFIG_FILE, STATUS_FILE, EXECUTOR_PID_FILE]:
            if os.path.exists(file):
                try:
                    os.remove(file)
                except Exception as e:
                    print(f"Warning: Could not remove {file}: {e}")
        
        # Start the background executor
        process = subprocess.Popen(
            [sys.executable, "background_executor.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        
        # Save the PID
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
        
        # Check if process is still running
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        # Process doesn't exist or invalid PID
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
        
        # Terminate the process
        os.kill(pid, signal.SIGTERM)
        time.sleep(0.5)
        
        # Clear PID file -- this needs to occur otherwise the next run will not produce new files
        if os.path.exists(EXECUTOR_PID_FILE):
            os.remove(EXECUTOR_PID_FILE)
        
        return True, "Executor stopped"
    except Exception as e:
        return False, str(e)

def get_gain_value(plot_path):
    """Extract gain value from corresponding text file"""
    base_name = os.path.splitext(plot_path)[0]
    txt_path = base_name + 'gain*.txt'
    
    if not os.path.exists(txt_path):
        dir_path = os.path.dirname(plot_path)
        txt_path = os.path.join(dir_path, 'gain_result*.txt')
    
    if not os.path.exists(txt_path):
        txt_path = plot_path.replace('.png', '.txt')
    
    try:
        if os.path.exists(txt_path):
            with open(txt_path, 'r') as f:
                gain_str = f.read().strip()
                # Try to format the gain value nicely
                try:
                    gain_val = float(gain_str)
                    return f"Gain: {gain_val:.2e}"
                except ValueError:
                    return f"Gain: {gain_str}"
        else:
            return "Gain: N/A"
    except Exception as e:
        return "Gain: Error"
    
# *---- Remote functions: -------------------------------------------------------------------------*
# |     Here we can change the remote server, and directory, and command that is executed on the   |
# |     server.                                                                                    |
# *------------------------------------------------------------------------------------------------*
if "remote_host" not in st.session_state:
    st.session_state.remote_host = "earles@spartan.hpc.unimelb.edu.au"

if "remote_directory" not in st.session_state:
    st.session_state.remote_directory = "/data/gpfs/projects/punim1378/earles/Precal_GUI"

if "remote_command" not in st.session_state:
    st.session_state.remote_command = "sbatch ./RUN_LIVE_MONITORING_ALL_TEST.slurm {SN}" # SERVER BATCH SCRIPT. This is the executing file on server. We can write anyone we want and then insert it here OR change it on the GUI. 

if "archive_directory" not in st.session_state:
    st.session_state.archive_directory = "/data/gpfs/projects/punim1378/earles/Precal_GUI/archive"

if "flag_directory" not in st.session_state:
    st.session_state.flag_directory = "/data/gpfs/projects/punim1378/earles/Precal_GUI/FLAG"

if "cleanup_time_hours" not in st.session_state:
    st.session_state.cleanup_time_hours = 24

if "selected_plot" not in st.session_state:
    st.session_state.selected_plot = None

if "show_overlay" not in st.session_state:
    st.session_state.show_overlay = False

if "example_plot_path" not in st.session_state:
    st.session_state.example_plot_path = "example_data/GOOD_DATA_charge.png"

if 'submitted_job_ids' not in st.session_state:
    st.session_state.submitted_job_ids = []

# Automatic cleanup on page load
cleanup_old_data("synced_data/", st.session_state.cleanup_time_hours)

# Check background executor status
status = load_status()
is_running = bool(status and status.get('running', False))
executor_alive = check_executor_running()

# Auto-refresh when background executor is running
if is_running:
    # Refresh every 5 seconds (5000 milliseconds)
    st_autorefresh(interval=5000, key="datarefresh") # We will want to change this to a longer period, aligning with the full scanning time

# Background Executor Status
st.sidebar.header("STEP 1: Background Executor")
if executor_alive:
    st.sidebar.success("✅ Running")
else:
    st.sidebar.warning("⚠️ Not Running")

col_exec1, col_exec2 = st.sidebar.columns(2)
with col_exec1:
    if st.button("▶️ Start", disabled=executor_alive, use_container_width=True):
        success, result = start_background_executor()
        if success:
            st.success(f"✅ Executor started (PID: {result})")
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"❌ Failed to start: {result}")

with col_exec2:
    if st.button("⏹️ Stop", disabled=not executor_alive, use_container_width=True):
        success, msg = stop_background_executor()
        if success:
            st.success(f"✅ {msg}")
            time.sleep(1)
            st.rerun()
        else:
            st.error(f"❌ Failed: {msg}")

if st.sidebar.button("Reset All", type="secondary", use_container_width=True):
    # Stop executor
    stop_background_executor()
    
    # Clean up all status files
    for file in [CONFIG_FILE, STATUS_FILE, EXECUTOR_PID_FILE]:
        if os.path.exists(file):
            os.remove(file)
    
    st.sidebar.success("Reset complete!")
    time.sleep(1)
    st.rerun()

st.sidebar.divider()

with st.expander("STEP 2: Check Remote Server Configuration"):
    st.session_state.remote_host = st.text_input(
        "Remote Host",
        value=st.session_state.remote_host
    )
    st.session_state.remote_directory = st.text_input(
        "Remote Directory",
        value=st.session_state.remote_directory
    )
    st.session_state.remote_command = st.text_input(
        "Command to Execute",
        value=st.session_state.remote_command
    )


with st.expander("STEP 3: Local Data-Cleanup -- Execute before starting Scan"):
    cleanup_hours = st.number_input(
        "Delete data files older than (hours)",
        min_value=1,
        max_value=720,
        value=st.session_state.cleanup_time_hours,
        step=1,
        help="Data files on local machine older than this will be automatically deleted when user clicks 'Clear Old Data Now' "
    )
    st.session_state.cleanup_time_hours = cleanup_hours
    
    if st.button("Clear Old Data Now"):
        deleted = cleanup_old_data("synced_data/", st.session_state.cleanup_time_hours)
        if deleted > 0:
            st.success(f"Deleted {deleted} old data file(s)")
        else:
            st.info("No old files to delete")
    
    if st.button("Clear ALL Data Now", type="primary"):
        if os.path.exists("synced_data/"):
            count = 0
            
            all_png_files = glob.glob("synced_data/**/*.png", recursive=True)
            all_txt_files = glob.glob("synced_data/**/*.txt", recursive=True)
            
            # Delete PNG files
            for f in all_png_files:
                try:
                    os.remove(f)
                    count += 1
                except Exception as e:
                    st.error(f"Error deleting {f}: {str(e)}")
            
            # Delete TXT files
            for f in all_txt_files:
                try:
                    os.remove(f)
                    count += 1
                except Exception as e:
                    st.error(f"Error deleting {f}: {str(e)}")
            
            # remove empty directories
            try:
                for root, dirs, files in os.walk("synced_data/", topdown=False):
                    for dir_name in dirs:
                        dir_path = os.path.join(root, dir_name)
                        try:
                            if not os.listdir(dir_path):  # If directory is empty
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

left_col, right_col = st.columns([1, 1.5])

with right_col:
    col_grid_title, col_compare_btn = st.columns([3, 1])
    
    with col_grid_title:
        st.subheader("Recent Scan Data")
    
    with col_compare_btn:
        example_exists = (st.session_state.example_plot_path and 
                         os.path.exists(st.session_state.example_plot_path))
        
        if st.button(
            "Compare: ON" if st.session_state.show_overlay else "Compare: OFF",
            key="toggle_compare_mode",
            use_container_width=True,
            disabled=not example_exists,
            type="primary" if st.session_state.show_overlay else "secondary"
        ):
            st.session_state.show_overlay = not st.session_state.show_overlay
            st.rerun()
    
    st.caption("Shows recent scan results. Data will lag slightly behind acquisition.")

    def get_color_from_gain(gain_file_path, normal_range=(0.999e7, 1.049e7)):
        """
        Determine color based on gain value
        Returns: 'green' for healthy, 'red' for poor, 'yellow' for no data
        """
        if not gain_file_path or not os.path.exists(gain_file_path):
            return 'yellow'  # No data
        
        try:
            with open(gain_file_path, 'r') as f:
                gain_str = f.read().strip()
                gain_val = float(gain_str)
                
                # Define your thresholds here
                min_normal, max_normal = normal_range
                
                if min_normal <= gain_val <= max_normal:
                    return 'green'  # Healthy
                else:
                    return 'red'  # Poor
        except (ValueError, Exception):
            return 'yellow'  # Can't parse = no data


    sync_data_dir = "synced_data"
    N_COLS = 4
    N_ROWS = 5
    MAX_PLOTS = N_COLS * N_ROWS + 1

    if os.path.exists(sync_data_dir):
        png_files = [
            os.path.join(sync_data_dir, f)
            for f in os.listdir(sync_data_dir)
            if f.endswith(".png")
        ]
    else:
        png_files = []

    if not os.path.exists(sync_data_dir):
        st.warning(f"Directory does not exist: {sync_data_dir}")

    png_files = sorted(png_files, key=os.path.getmtime, reverse=True)
    png_files = png_files[:MAX_PLOTS]

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
    </style>
    """, unsafe_allow_html=True)

    slot = 0

    # First row - single [0,0] button centered
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        theta, phi = get_theta_phi_from_slot(slot)
        coord_label = get_coordinate_label(slot)
        
        png_file, gain_file = find_files_by_theta_phi("synced_data", theta, phi)
        
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
            
            if st.button("View", key=f"view_{slot}", use_container_width=True):
                st.session_state.selected_plot = png_file
                st.session_state.selected_gain = gain_value
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
                png_file, gain_file = find_files_by_theta_phi("synced_data", theta, phi)
                
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
                    
                    if st.button("View", key=f"view_{slot}", use_container_width=True):
                        st.session_state.selected_plot = png_file
                        st.session_state.selected_gain = gain_value
                
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


if st.session_state.selected_plot:
    if not os.path.exists(st.session_state.selected_plot):
        st.session_state.selected_plot = None
        st.session_state.selected_gain = None
        st.rerun()
    else:
        st.divider()
        col_plot, col_hide = st.columns([4, 1])
        
        with col_plot:
            if st.session_state.show_overlay:
                st.subheader("Selected Data (with Reference Overlay)")
            else:
                st.subheader("Selected Data")
        
        with col_hide:
            if st.button("Hide Plot", key="hide_plot"):
                st.session_state.selected_plot = None
                st.session_state.selected_gain = None
                st.rerun()
        
        example_exists = (st.session_state.example_plot_path and 
                         os.path.exists(st.session_state.example_plot_path))
        
        if st.session_state.show_overlay and example_exists:
            import base64
            
            # Read and encode both images
            with open(st.session_state.selected_plot, "rb") as f:
                base_img = base64.b64encode(f.read()).decode()
            
            with open(st.session_state.example_plot_path, "rb") as f:
                overlay_img = base64.b64encode(f.read()).decode()

            st.markdown(f"""
                <div style="position: relative; width: 100%;">
                    <img src="data:image/png;base64,{base_img}" style="width: 100%; display: block;">
                    <img src="data:image/png;base64,{overlay_img}" 
                         style="position: absolute; top: 0; left: 0; width: 100%; opacity: 0.5;">
                </div>
            """, unsafe_allow_html=True)
            
            st.caption(f"{os.path.basename(st.session_state.selected_plot)} + Reference Overlay")
        else:
            import base64
            with open(st.session_state.selected_plot, "rb") as f:
                img_data = base64.b64encode(f.read()).decode()
            
            st.markdown(f"""
                <div style="width: 100%;">
                    <img src="data:image/png;base64,{img_data}" style="width: 100%; display: block;">
                </div>
            """, unsafe_allow_html=True)
            
            st.caption(os.path.basename(st.session_state.selected_plot))
        
        if st.session_state.selected_gain:
            st.info(st.session_state.selected_gain)

with left_col:
    st.subheader("STEP 4: Enter Serial Number")

    if "serial_number" not in st.session_state:
        st.session_state.serial_number = ""

    serial_number_input = st.text_input(
        "Enter PMT Serial Number:",
        value=st.session_state.serial_number,
        placeholder="e.g., SN12345",
        help="This serial number will be used to locate the correct data files on the server",
        key="sn_input"
    )

    st.session_state.serial_number = serial_number_input

    if st.session_state.serial_number.strip():
        st.success(f"✓ Serial Number set: {st.session_state.serial_number}")
    else:
        st.warning("⚠️ Please enter a serial number before starting auto-execute")

    st.divider()

    with stylable_container(
        "orange_button",
        css_styles="""
        button {
            background-color: #228B22;
            color: white;
            border-color: #228B22;
            height: 80px;
            font-size: 18px;
            font-weight: bold;
            white-space: pre-line;
            line-height: 1.3;
        }
        button:hover {
            border-color: #0066cc;
            opacity: 0.9;
        }
        """,
    ):
        button_disabled = is_running or not executor_alive or not st.session_state.serial_number.strip()
        
        if st.button("STEP 5: RUN LIVE MONITORING\nStart Auto-Execute (21 runs)", 
                     type="primary", 
                     use_container_width=True,
                     disabled=button_disabled, 
                     key="start_auto"):
            # First, archive existing data on server
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
            
            # Then start auto-execute
            config = {
                'running': True,
                'remote_host': st.session_state.remote_host,
                'remote_directory': st.session_state.remote_directory,
                'remote_command': st.session_state.remote_command,
                'serial_number': st.session_state.serial_number,  # Add serial number to config
                'total_runs': 21,
                'interval_seconds': 10,   #### syncing interval
                'job_ids': []
            }
            save_config(config)
            st.success("Auto-execute started!")
            time.sleep(2)
            st.rerun()

    st.caption(
        "This will first archive any existing data on the server, then automatically process data on the server and sync with that data."
    )

    with stylable_container(
        "orange_button_stop",
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
        if st.button("Stop Auto-Execute", type="primary", use_container_width=True, disabled=not is_running, key="stop_auto"):

            # Stop auto-execute locally
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

            # Cancel SLURM jobs
            try:
                cancel_cmd = f"ssh {st.session_state.remote_host} scancel -u earles"
                subprocess.run(
                    cancel_cmd,
                    shell=True,
                    check=True,
                    timeout=15
                )
                st.success("Auto-execute stopped and SLURM jobs cancelled")

            except subprocess.CalledProcessError as e:
                st.warning("Auto-execute stopped, but scancel failed")

            time.sleep(1)
            st.rerun()
    st.divider()
    
    if st.button("Execute on Server Once", type="secondary", disabled=is_running or not executor_alive):
        st.info("Executing command on Server...")
        
        ssh_command = (
            f"ssh {st.session_state.remote_host} "
            f"'cd {st.session_state.remote_directory} && {st.session_state.remote_command}'"
        )
        
        try:
            result = subprocess.run(
                ssh_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                st.success("Command executed successfully!")
            else:
                st.warning("Command completed with errors")
            
            if result.stdout:
                st.code(result.stdout, language="bash")
                
        except subprocess.TimeoutExpired:
            st.error("❌ Command timed out")
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")

    if is_running:
        st.info("Auto-refreshing every 5 seconds!")
        if st.button("Refresh Now"):
            st.rerun()

    if st.button("Manual Sync", type="secondary"):
        st.info("Syncing from server...")
        
        sn = st.session_state.serial_number if st.session_state.serial_number.strip() else None
        success, msg = sync_from_spartan(st.session_state.remote_host, st.session_state.remote_directory, serial_number=sn)
        
        if success:
            st.success(f"✅ {msg}")
        else:
            st.warning(f"⚠️ {msg}")


st.divider()


with stylable_container(
    "red_button",
    css_styles="""
    button {
        background-color: #dc3545;
        color: white;
        border-color: #dc3545;
        height: 60px;
        font-size: 18px;
        font-weight: bold;
    }
    button:hover {
        border-color: #0066cc;
        opacity: 0.9;
    }
    """,
):
    if st.button("⚠️ STEP 6: Flag Data as ABNORMAL", type="primary", use_container_width=True, key="flag_data"):
        st.info("Flagging data on server...")
        success, message = flag_data_on_server(
            st.session_state.remote_host,
            st.session_state.remote_directory,
            st.session_state.flag_directory
        )
        
        if success:
            st.success(f"✅ {message}")
        else:
            st.error(f"❌ {message}")

st.caption("Use this button to flag abnormal data files and move them to the flag directory on the server.")

with st.expander("Configure Archive and Flag Directories"):
    st.session_state.archive_directory = st.text_input(
        "Archive Directory on Server:",
        value=st.session_state.archive_directory,
        help="Remote directory where normal data files will be moved to"
    )
    
    st.session_state.flag_directory = st.text_input(
        "Flag Directory on Server:",
        value=st.session_state.flag_directory,
        help="Remote directory where abnormal/flagged data files will be moved to"
    )
    
    if st.button("Archive Server Data (Manual)", type="secondary", use_container_width=True):
        st.info("Archiving data on server...")
        success, message = archive_data_on_server(
            st.session_state.remote_host,
            st.session_state.remote_directory,
            st.session_state.archive_directory
        )
        
        if success:
            st.success(f"✅ {message}")
        else:
            st.error(f"❌ {message}")
    
    st.caption("Archive happens automatically when starting Auto-Execute. Use manual archive only if needed.")
    
st.divider()
st.subheader("Data Files in Local Directory")

sync_data_dir = "synced_data/"
if os.path.exists(sync_data_dir):
    # Find all PNG files recursively
    png_files = glob.glob(f"{sync_data_dir}/**/live_data_*.png", recursive=True)
    
    if png_files:
        # Sort by modification time
        png_files = sorted(png_files, key=os.path.getmtime, reverse=True)
        
        st.write(f"Found {len(png_files)} data file(s):")
        
        # Group by theta/phi
        for f in png_files[:20]:  # Show most recent 20
            theta, phi = parse_theta_phi_from_path(f)
            rel_path = os.path.relpath(f, sync_data_dir)
            st.text(f"[θ={theta}, φ={phi}] {rel_path}")
    else:
        st.info("No files found in the data directory yet.")
else:
    st.warning(f"Directory does not exist: {sync_data_dir}")
