#!/bin/bash
#SBATCH --job-name=run_pmt_scan_
#SBATCH --output=batch_log/run_pmt_scan_%j.log
#SBATCH --time=06:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G

module -q load GCC/11.3.0 OpenMPI/4.1.4
module -q load ROOT/6.26.10
module -q unload SciPy-bundle/2022.05

# SCRIPT_DIR="$(dirname "$(realpath "$0")")"
SCRIPT_DIR="${SLURM_SUBMIT_DIR}"
source "${SCRIPT_DIR}/../../pyrate/pyrate_venv/bin/activate"

echo "It worked"
