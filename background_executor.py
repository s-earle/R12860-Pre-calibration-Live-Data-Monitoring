#!/usr/bin/env python3
"""
Background executor script for auto-running commands on Spartan HPC
This script keeps running and waits for commands
"""

import subprocess
import time
import json
import os
import glob
from datetime import datetime

CONFIG_FILE = "executor_config.json"
STATUS_FILE = "executor_status.json"

def load_config():
    """Load configuration from file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return None
    return None

def save_status(status_data):
    """Save current status to file"""
    with open(STATUS_FILE, 'w') as f:
        json.dump(status_data, f, indent=2)

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
            hv_source_path = f"{remote_dir}/HV_analysis_*/{serial_number}/"
        else:
            hv_source_path = f"{remote_dir}/HV_analysis_*/"
        
        rsync_hv_command = (
            f"rsync -avz --include='*/' "
            f"--include='HV_analysis_*/' "
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


def execute_command(remote_host, remote_dir, remote_command, serial_number=None):
    """Execute command on remote server"""
    # Replace {SN} placeholder with actual serial number
    if serial_number and '{SN}' in remote_command:
        actual_command = remote_command.replace('{SN}', serial_number)
    else:
        actual_command = remote_command
    
    ssh_command = (
        f"ssh {remote_host} "
        f"'cd {remote_dir} && {actual_command}'"
    )
    
    try:
        result = subprocess.run(
            ssh_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        job_id = None
        if result.returncode == 0 and "Submitted batch job" in result.stdout:
            job_id = result.stdout.strip().split()[-1]
        
        return result.returncode == 0, result.stdout, result.stderr, job_id  # Added job_id
    except Exception as e:
        return False, "", str(e), None  # Added None for job_id

def count_data_points(local_dir="synced_data/"):
    """Count how many data points have been synced"""
    if not os.path.exists(local_dir):
        return 0
    
    # Count unique theta/phi combinations from PNG files
    png_files = glob.glob(f"{local_dir}/**/*_charge.png", recursive=True)
    
    # Extract unique theta/phi pairs
    unique_points = set()
    for f in png_files:
        # Extract theta and phi from filename
        import re
        match = re.search(r'theta(\d+)_phi(\d+)', f)
        if match:
            theta = int(match.group(1))
            phi = int(match.group(2))
            unique_points.add((theta, phi))
    
    return len(unique_points)

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Background executor started")
    print("Waiting for commands...")
    
    # Initialize status as idle
    save_status({
        'running': False,
        'completed': 0,
        'total': 0,
        'message': 'Executor ready, waiting for commands'
    })
    
    while True:
        try:
            config = load_config()
            
            if config and config.get('running'):
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Starting live monitoring")
                
                # Use hv_remote_directory if present, otherwise use remote_directory
                remote_dir = config.get('hv_remote_directory') or config.get('remote_directory')
                
                # Use hv_remote_command if present, otherwise use remote_command
                remote_command = config.get('hv_remote_command') or config.get('remote_command')
                
                save_status({
                    'running': True,
                    'completed': 0,
                    'total': config['total_runs'],
                    'message': 'Starting SLURM job on server'
                })
                
                # Execute the SLURM job ONCE - it will handle all points
                print(f"  Submitting SLURM job to {remote_dir}...")
                print(f"  Command: {remote_command}")
                exec_success, stdout, stderr, job_id = execute_command(
                    config['remote_host'],
                    remote_dir,
                    remote_command,  # CHANGED: Use the variable
                    serial_number=config.get('serial_number')
                )
                
                if exec_success:
                    print(f"✓ SLURM job submitted successfully")
                    if stdout:
                        print(f"  Output: {stdout.strip()}")

                    if job_id:
                        config['job_ids'] = config.get('job_ids', [])
                        config['job_ids'].append(job_id)
                        with open(CONFIG_FILE, 'w') as f:
                            json.dump(config, f, indent=2)
                        print(f"  Saved job ID: {job_id}")
                        
                else:
                    print(f"✗ SLURM job submission FAILED")
                    if stderr:
                        print(f"  Error: {stderr}")
                    if stdout:
                        print(f"  Output: {stdout}")
                
                # Monitor for new data points appearing
                previous_count = 0
                sync_interval = 30  # Check for new data every 30 seconds
                max_wait_cycles = 720  # Maximum wait time: 720 * 30s = 6 hours
                wait_cycles = 0
                
                while True:
                    # Check if we should stop
                    config = load_config()
                    if not config or not config.get('running'):
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Monitoring stopped by user")
                        save_status({
                            'running': False,
                            'completed': previous_count,
                            'total': config.get('total_runs', 0) if config else 0,
                            'message': 'Stopped by user - Ready for new commands'
                        })
                        break
                    
                    # Use hv_remote_directory if present, otherwise use remote_directory
                    remote_dir = config.get('hv_remote_directory') or config.get('remote_directory')
                    
                    # Sync files
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Syncing from {remote_dir}...")
                    sync_success, sync_msg = sync_from_spartan(
                        config['remote_host'],
                        remote_dir,
                        serial_number=config.get('serial_number')
                    )
                    print(f"  {sync_msg}")
                    
                    # Count data points
                    current_count = count_data_points()
                    
                    # Check if new data appeared
                    if current_count > previous_count:
                        print(f"  ✓ New data detected! ({previous_count} → {current_count})")
                        previous_count = current_count
                        wait_cycles = 0  # Reset timeout counter
                        
                        save_status({
                            'running': True,
                            'completed': current_count,
                            'total': config['total_runs'],
                            'message': f'Synced {current_count}/{config["total_runs"]} data points',
                            'last_success': sync_success
                        })
                        
                        # Check if all data points collected
                        if current_count >= config['total_runs']:
                            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✓ All {config['total_runs']} data points collected!")
                            save_status({
                                'running': False,
                                'completed': config['total_runs'],
                                'total': config['total_runs'],
                                'message': 'Monitoring complete - All data collected'
                            })
                            
                            # Mark as not running in config
                            if config:
                                config['running'] = False
                                with open(CONFIG_FILE, 'w') as f:
                                    json.dump(config, f, indent=2)
                            break
                    else:
                        print(f"  Waiting for new data... ({current_count}/{config['total_runs']} points collected)")
                        wait_cycles += 1
                        
                        # Check for timeout
                        if wait_cycles >= max_wait_cycles:
                            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ⚠ Timeout: No new data after {max_wait_cycles * sync_interval}s")
                            save_status({
                                'running': False,
                                'completed': current_count,
                                'total': config['total_runs'],
                                'message': f'Timeout - Only {current_count}/{config["total_runs"]} points collected'
                            })
                            
                            if config:
                                config['running'] = False
                                with open(CONFIG_FILE, 'w') as f:
                                    json.dump(config, f, indent=2)
                            break
                        
                        save_status({
                            'running': True,
                            'completed': current_count,
                            'total': config['total_runs'],
                            'message': f'Waiting for data... ({current_count}/{config["total_runs"]})',
                            'last_success': sync_success
                        })
                    
                    # Wait before next sync
                    print(f"  Waiting {sync_interval} seconds before next sync...")
                    for i in range(sync_interval):
                        # Check for cancellation during wait
                        config = load_config()
                        if not config or not config.get('running'):
                            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Cancelled during wait")
                            save_status({
                                'running': False,
                                'completed': current_count,
                                'total': config.get('total_runs', 0) if config else 0,
                                'message': 'Stopped by user - Ready for new commands'
                            })
                            break
                        time.sleep(1)
                    else:
                        continue
                    break
            
            # Wait before checking again
            time.sleep(2)
            
        except KeyboardInterrupt:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Executor shutting down...")
            save_status({
                'running': False,
                'completed': 0,
                'total': 0,
                'message': 'Executor stopped'
            })
            break
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Error: {str(e)}")
            import traceback
            traceback.print_exc()
            time.sleep(5)

if __name__ == "__main__":
    main()