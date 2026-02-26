#!/usr/bin/env python3
"""
Background executor script for auto-running commands on Spartan HPC.
Stays alive until the main Streamlit app stops sending heartbeats.
Picks up any config written with running=True and submits + monitors it.
"""

import subprocess
import time
import json
import os
import glob
import re
from datetime import datetime
import sys

CONFIG_FILE  = sys.argv[1] if len(sys.argv) > 1 else "executor_config.json"
STATUS_FILE  = sys.argv[2] if len(sys.argv) > 2 else "executor_status.json"

HEARTBEAT_FILE    = "app_heartbeat.json"
HEARTBEAT_TIMEOUT = 15   # seconds — app refreshes every 5 s, so 15 s is safe


# ── Helpers ──────────────────────────────────────────────────────────────────

def is_app_alive():
    if not os.path.exists(HEARTBEAT_FILE):
        return False
    try:
        return (time.time() - os.path.getmtime(HEARTBEAT_FILE)) < HEARTBEAT_TIMEOUT
    except Exception:
        return False


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def save_status(data):
    try:
        with open(STATUS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def get_remote_dir(config):
    """Return whichever remote directory key is present in this config."""
    return (config.get('hv_remote_directory')
            or config.get('scan_remote_directory')
            or config.get('remote_directory')
            or '')


def get_remote_command(config):
    """Return whichever remote command key is present in this config."""
    return (config.get('hv_remote_command')
            or config.get('scan_remote_command')
            or config.get('remote_command')
            or '')


def execute_command(remote_host, remote_dir, remote_command):
    """SSH to remote_host, cd to remote_dir and run remote_command."""
    ssh_cmd = f"ssh {remote_host} 'cd {remote_dir} && {remote_command}'"
    print(f"  SSH: {ssh_cmd}")
    try:
        result = subprocess.run(
            ssh_cmd, shell=True, capture_output=True, text=True, timeout=120
        )
        job_id = None
        if result.returncode == 0 and "Submitted batch job" in result.stdout:
            job_id = result.stdout.strip().split()[-1]
        return result.returncode == 0, result.stdout, result.stderr, job_id
    except subprocess.TimeoutExpired:
        return False, "", "SSH command timed out", None
    except Exception as e:
        return False, "", str(e), None


def count_data_points(local_dir="synced_data/"):
    """Count unique scan/HV data points present locally."""
    if not os.path.exists(local_dir):
        return 0
    png_files = glob.glob(f"{local_dir}/**/*_charge.png", recursive=True)
    unique = set()
    for f in png_files:
        m = re.search(r'theta(\d+)_phi(\d+)', f)
        if m:
            unique.add(('scan', m.group(1), m.group(2)))
            continue
        m = re.search(r'HV_(\d+)_charge', f)
        if m:
            unique.add(('hv', m.group(1)))
    return len(unique)


def sync_from_remote(config):
    """Rsync scan_output_* and HV_output_* from remote to local."""
    remote_host = config['remote_host']
    remote_dir  = get_remote_dir(config)
    sn          = config.get('serial_number')
    local_dir   = "synced_data/"

    # Scan data
    src = f"{remote_dir}/scan_output_*/{sn}" if sn else f"{remote_dir}/scan_output_*/"
    cmd = (f"rsync -avz --include='*/' --include='*_charge.png' "
           f"--include='*_GAIN.txt' --exclude='*' "
           f"{remote_host}:{src} {local_dir}")
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)

    # HV data
    src_hv = f"{remote_dir}/HV_output_*/{sn}/" if sn else f"{remote_dir}/HV_output_*/"
    cmd_hv = (f"rsync -avz --include='*/' --include='HV_output_*/' "
              f"--include='*/data_HV_*/' --include='*_charge.png' "
              f"--include='*_GAIN.txt' --include='*_gain_vs_hv_loglog.png' "
              f"--include='*_HV_at_gain_*.txt' --exclude='*' "
              f"{remote_host}:{src_hv} {local_dir}")
    r_hv = subprocess.run(cmd_hv, shell=True, capture_output=True, text=True, timeout=120)

    ok  = (r.returncode == 0 or r_hv.returncode == 0)
    msg = "Sync OK" if ok else f"scan rc={r.returncode} hv rc={r_hv.returncode}"
    return ok, msg


def sleep_interruptible(seconds):
    """
    Sleep second-by-second, returning False early if:
      - heartbeat is lost (app closed)
      - config running flag flipped to False (user stopped)
    Returns True if the full sleep completed normally.
    """
    for _ in range(seconds):
        if not is_app_alive():
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Heartbeat lost during sleep.")
            return False
        cfg = load_config()
        if not cfg or not cfg.get('running'):
            return False
        time.sleep(1)
    return True


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
          f"Background executor started  config={CONFIG_FILE}")
    print(f"  Heartbeat timeout: {HEARTBEAT_TIMEOUT}s")

    save_status({'running': False, 'completed': 0, 'total': 0,
                 'message': 'Executor ready, waiting for commands'})

    while True:
        try:
            # ── Heartbeat check ──────────────────────────────────────────────
            if not is_app_alive():
                print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                      f"No heartbeat — app has exited. Stopping.")
                save_status({'running': False, 'completed': 0, 'total': 0,
                             'message': 'Executor stopped: main app exited'})
                break

            config = load_config()

            # ── Idle — no job yet ─────────────────────────────────────────────
            if not (config and config.get('running')):
                time.sleep(2)
                continue

            # ── Job received ──────────────────────────────────────────────────
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Job received")

            remote_dir = get_remote_dir(config)
            remote_cmd = get_remote_command(config)
            total_runs = config.get('total_runs', 21)

            print(f"  remote_dir : {remote_dir}")
            print(f"  remote_cmd : {remote_cmd}")
            print(f"  total_runs : {total_runs}")

            # Guard against misconfigured job
            if not remote_dir or not remote_cmd:
                print("  ERROR: remote_dir or remote_cmd is empty — check config keys")
                save_status({'running': False, 'completed': 0, 'total': total_runs,
                             'message': 'ERROR: missing remote_dir or remote_cmd in config'})
                config['running'] = False
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(config, f, indent=2)
                time.sleep(2)
                continue

            save_status({'running': True, 'completed': 0, 'total': total_runs,
                         'message': 'Submitting SLURM job…'})

            # ── Submit SLURM job ──────────────────────────────────────────────
            ok, stdout, stderr, job_id = execute_command(
                config['remote_host'], remote_dir, remote_cmd
            )

            if ok:
                print(f"  ✓ Job submitted  job_id={job_id}")
                if job_id:
                    config.setdefault('job_ids', []).append(job_id)
                    with open(CONFIG_FILE, 'w') as f:
                        json.dump(config, f, indent=2)
                save_status({'running': True, 'completed': 0, 'total': total_runs,
                             'message': f'Job submitted (id={job_id}), waiting for data…'})
            else:
                print(f"  ✗ Job submission FAILED")
                print(f"    stdout: {stdout.strip()}")
                print(f"    stderr: {stderr.strip()}")
                save_status({'running': True, 'completed': 0, 'total': total_runs,
                             'message': f'Job submission failed: {stderr.strip()[:120]}'})
                # Still enter monitoring — sbatch sometimes prints to stderr on success

            # ── Monitoring loop ───────────────────────────────────────────────
            # Baseline: snapshot existing local files so we only count NEW arrivals
            baseline    = count_data_points()
            sync_interval = 30
            max_cycles  = 720   # 720 × 30 s = 6 hours max
            wait_cycles = 0
            new_pts     = 0

            print(f"  Baseline local count: {baseline}  (only new arrivals counted)")

            while True:
                # Heartbeat check
                if not is_app_alive():
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                          f"Heartbeat lost during monitoring.")
                    save_status({'running': False, 'completed': new_pts,
                                 'total': total_runs,
                                 'message': 'Stopped: main app exited'})
                    return  # exit the process entirely

                # User-stop check
                config = load_config()
                if not config or not config.get('running'):
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Stopped by user.")
                    save_status({'running': False, 'completed': new_pts,
                                 'total': total_runs,
                                 'message': 'Stopped by user — ready for new commands'})
                    break   # back to outer idle loop

                # Sync
                remote_dir = get_remote_dir(config)
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Syncing from {remote_dir}…")
                sync_ok, sync_msg = sync_from_remote(config)
                print(f"  {sync_msg}")

                current = count_data_points()
                new_pts = current - baseline

                if new_pts > 0:
                    wait_cycles = 0
                    print(f"  ✓ {new_pts}/{total_runs} new points collected")
                    save_status({'running': True, 'completed': new_pts,
                                 'total': total_runs,
                                 'message': f'Collected {new_pts}/{total_runs} points'})

                    if new_pts >= total_runs:
                        print(f"  ✓ All {total_runs} points collected — done!")
                        sync_from_remote(config)  # final sync
                        save_status({'running': False, 'completed': total_runs,
                                     'total': total_runs,
                                     'message': 'Complete — all data collected'})
                        config['running'] = False
                        with open(CONFIG_FILE, 'w') as f:
                            json.dump(config, f, indent=2)
                        break   # back to outer idle loop
                else:
                    wait_cycles += 1
                    print(f"  No new data yet "
                          f"(cycle {wait_cycles}/{max_cycles}, baseline={baseline}, current={current})")
                    save_status({'running': True, 'completed': 0,
                                 'total': total_runs,
                                 'message': f'Waiting for data… (cycle {wait_cycles}/{max_cycles})'})

                    if wait_cycles >= max_cycles:
                        print(f"  ⚠ Timeout after {max_cycles * sync_interval}s")
                        save_status({'running': False, 'completed': new_pts,
                                     'total': total_runs,
                                     'message': f'Timeout — only {new_pts}/{total_runs} points'})
                        config['running'] = False
                        with open(CONFIG_FILE, 'w') as f:
                            json.dump(config, f, indent=2)
                        break

                # Interruptible sleep
                print(f"  Sleeping {sync_interval}s before next sync…")
                if not sleep_interruptible(sync_interval):
                    save_status({'running': False, 'completed': new_pts,
                                 'total': total_runs,
                                 'message': 'Stopped: app exited or user cancelled'})
                    if not is_app_alive():
                        return  # app died — exit process
                    break       # user stopped — go idle

        except KeyboardInterrupt:
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] KeyboardInterrupt — exiting.")
            save_status({'running': False, 'completed': 0, 'total': 0,
                         'message': 'Executor stopped'})
            break
        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Unhandled error: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)


if __name__ == "__main__":
    main()