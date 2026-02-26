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

# Get serial number from command line argument
SN=$1
if [ -z "$SN" ]; then
    echo "ERROR: No serial number provided"
    echo "Usage: sbatch RUN.slurm <SERIAL_NUMBER>"
    exit 1
fi
export TZ='Asia/Tokyo'
date_today=$(date +%Y%m%d)
datetime=$(date +%Y%m%d_%H%M%S)

TEMPLATE_FILE="${SCRIPT_DIR}/config/R12860_scan_data_process.yaml"
# TEMPLATE_FILE="${SCRIPT_DIR}/config/R12860_scan_template.yaml"
YAML_OUTPUT_DIR="${SCRIPT_DIR}/config/pyrate_configs/${SN}"
# YAML_OUTPUT_DIR="${SCRIPT_DIR}/config/temp_yaml_configs/${SN}"
mkdir -p "$YAML_OUTPUT_DIR"

ROOT_PARENT_DIR="${SCRIPT_DIR}/ROOT_SCAN_DATA_saves/pyrate_output_${datetime}/${SN}"
mkdir -p "$ROOT_PARENT_DIR"

WAVEDUMP_BASE="${SCRIPT_DIR}/../../WaveDumpSaves"
PROCESSED_LOG="${SCRIPT_DIR}/processed_files_${datetime}_${SN}.log"
touch "$PROCESSED_LOG"

echo "Starting live processing for Serial Number: $SN"
echo "Script directory: $SCRIPT_DIR"
echo "Template file: $TEMPLATE_FILE"
echo "Start time: $(date)"

# Define coordinate arrays
THETA_VALUES=(0 10 10 10 10 20 20 20 20 30 30 30 30 40 40 40 40 50 50 50 50)
PHI_VALUES=(0 0 90 180 270 0 90 180 270 0 90 180 270 0 90 180 270 0 90 180 270)

TOTAL_POINTS=21
WAIT_INTERVAL=30

echo "Monitoring for TXT files with SN: $SN"
echo "Will check every ${WAIT_INTERVAL} seconds"
echo "----------------------------------------"

for i in $(seq 0 $((TOTAL_POINTS - 1))); do
    THETA=${THETA_VALUES[$i]}
    PHI=${PHI_VALUES[$i]}
    ROOT_OUT_DIR="$ROOT_PARENT_DIR/scan_${datetime}_${SN}_theta${THETA}_phi${PHI}"
    # ROOT_OUT_NAME="scan_${date_today}_${SN}_theta${THETA}_phi${PHI}"
    echo ""
    echo "=== Scan Point $((i + 1))/$TOTAL_POINTS: theta=${THETA}, phi=${PHI} ==="
    
    PROCESSED=false
    
    while [ "$PROCESSED" = false ]; do
        # RUN_DIR=$(find "${WAVEDUMP_BASE}"/wavedump_output_*/${SN}/wavesave_theta${THETA}_phi${PHI} -type d -maxdepth 0 2>/dev/null | head -n 1)
        RUN_DIR=""
        for output_dir in $(ls -dt "${WAVEDUMP_BASE}"/wavedump_output_* 2>/dev/null); do
            candidate="${output_dir}/${SN}/wavesave_theta${THETA}_phi${PHI}"
            if [ -d "${candidate}" ]; then
                RUN_DIR="${candidate}"
                break
            fi
        done
        if [ -n "$RUN_DIR" ]; then
            CH0_EXISTS=false
            CH1_EXISTS=false
            CH2_EXISTS=false
            CH3_EXISTS=false
            # CH4_EXISTS=false
            
            ls "$RUN_DIR"/wave0*.txt >/dev/null 2>&1 && CH0_EXISTS=true
            ls "$RUN_DIR"/wave1*.txt >/dev/null 2>&1 && CH1_EXISTS=true
            ls "$RUN_DIR"/wave2*.txt >/dev/null 2>&1 && CH2_EXISTS=true
            ls "$RUN_DIR"/wave3*.txt >/dev/null 2>&1 && CH3_EXISTS=true
            # ls "$RUN_DIR"/wave4*.txt >/dev/null 2>&1 && CH4_EXISTS=true
            
            CH2_OR_CH3_EXISTS=false
            if [ "$CH2_EXISTS" = true ] || [ "$CH3_EXISTS" = true ]; then
                CH2_OR_CH3_EXISTS=true
            fi
            
            CHANNELS=""
            [ "$CH0_EXISTS" = true ] && CHANNELS="${CHANNELS}0, "
            [ "$CH1_EXISTS" = true ] && CHANNELS="${CHANNELS}1, "
            [ "$CH2_EXISTS" = true ] && CHANNELS="${CHANNELS}2, "
            [ "$CH3_EXISTS" = true ] && CHANNELS="${CHANNELS}3, "
            # [ "$CH4_EXISTS" = true ] && CHANNELS="${CHANNELS}4, "
            CHANNELS="${CHANNELS%, }"

            PMT_CHANNEL=""
            if [ "$CH2_EXISTS" = true ]; then
                PMT_CHANNEL="2"
            elif [ "$CH3_EXISTS" = true ]; then
                PMT_CHANNEL="3"
            fi

            if [ "$CH0_EXISTS" = true ] && [ "$CH1_EXISTS" = true ] && [ "$CH2_OR_CH3_EXISTS" = true ]; then # && [ "$CH4_EXISTS" = true ]; then
                if grep -q "$RUN_DIR" "$PROCESSED_LOG"; then
                    echo "  [$(date +%H:%M:%S)] Directory already processed: $RUN_DIR"
                    PROCESSED=true
                else
                    TXT_COUNT=$(ls "$RUN_DIR"/wave*.txt 2>/dev/null | wc -l)
                    CHANNEL_INFO="ch0, ch1"
                    [ "$CH2_EXISTS" = true ] && CHANNEL_INFO="${CHANNEL_INFO}, ch2"
                    [ "$CH3_EXISTS" = true ] && CHANNEL_INFO="${CHANNEL_INFO}, ch3"
                    
                    echo "  [$(date +%H:%M:%S)] Found directory with $TXT_COUNT txt files ($CHANNEL_INFO): $RUN_DIR"
                    
                    GENERATED_YAML="${YAML_OUTPUT_DIR}/config_${SN}_theta${THETA}_phi${PHI}.yaml"
                    
                    sed -e "s|<CHANNELS>|${CHANNELS}|g" \
                        -e "s|<PMT_CHANNEL>|${PMT_CHANNEL}|g" \
                        -e "s|<run_path>|${RUN_DIR}|g" \
                        -e "s|{SN}|${SN}|g" \
                        -e "s|{THETA}|${THETA}|g" \
                        -e "s|{PHI}|${PHI}|g" \
                        -e "s|<out_name>|${ROOT_OUT_DIR}|g" \
                        "$TEMPLATE_FILE" > "$GENERATED_YAML"

                    if [ $? -eq 0 ]; then
                        echo "  YAML generated: $GENERATED_YAML"
                        echo "  Processing TXT files to ROOT with pyrate..."
                        
                        # mkdir -p "$ROOT_OUT_DIR"
                        pyrate -c "$GENERATED_YAML"
                        
                        if [ $? -eq 0 ]; then
                            echo "  ✓ ROOT file generation completed successfully"
                            echo "  Waiting for ROOT file to be ready..."
                            ROOT_FILE_PATTERN="${ROOT_OUT_DIR}.root"
                            ROOT_READY=false
                            
                            while [ "$ROOT_READY" = false ]; do
                                ROOT_FILE=$(ls -t $ROOT_FILE_PATTERN 2>/dev/null | head -n 1)
                                if [ -n "$ROOT_FILE" ]; then
                                    INITIAL_SIZE=$(stat -c%s "$ROOT_FILE" 2>/dev/null)
                                    sleep 2
                                    FINAL_SIZE=$(stat -c%s "$ROOT_FILE" 2>/dev/null)
                                    
                                    if [ "$INITIAL_SIZE" = "$FINAL_SIZE" ] && [ "$FINAL_SIZE" -gt 0 ]; then
                                        echo "  ✓ ROOT file ready: $(basename $ROOT_FILE)"
                                        ROOT_READY=true
                                    else
                                        echo "  ROOT file still being written..."
                                        sleep 5
                                    fi
                                else
                                    echo "  Waiting for ROOT file..."
                                    sleep $WAIT_INTERVAL
                                fi
                            done
                            
                            echo "  Running Python analysis script..."
                            python3 "${SCRIPT_DIR}/live_monitoring_data_analysis.py" "$SN" "$THETA" "$PHI"
                            
                            if [ $? -eq 0 ]; then
                                echo "  ✓ Python analysis completed successfully"
                                echo "$RUN_DIR" >> "$PROCESSED_LOG"
                                PROCESSED=true
                            else
                                echo "  ✗ Python analysis failed, will retry entire process"
                                sleep $WAIT_INTERVAL
                            fi
                        else
                            echo "  ✗ Pyrate processing failed, will retry"
                            sleep $WAIT_INTERVAL
                        fi
                    else
                        echo "  ✗ YAML generation failed, will retry"
                        sleep $WAIT_INTERVAL
                    fi
                fi
            else
                MISSING=""
                [ "$CH0_EXISTS" = false ] && MISSING="${MISSING}ch0 "
                [ "$CH1_EXISTS" = false ] && MISSING="${MISSING}ch1 "
                [ "$CH2_OR_CH3_EXISTS" = false ] && MISSING="${MISSING}(ch2 or ch3) "
                # [ "$CH4_EXISTS" = false ] && MISSING="${MISSING}ch4 "
                echo "  [$(date +%H:%M:%S)] Waiting for required files. Missing: $MISSING(theta=${THETA}, phi=${PHI})"
                sleep $WAIT_INTERVAL
            fi
        else
            echo "  [$(date +%H:%M:%S)] Waiting for directory... (theta=${THETA}, phi=${PHI})"
            sleep $WAIT_INTERVAL
        fi
    done
    
    echo "  Point $((i + 1))/$TOTAL_POINTS complete"
done

echo ""
echo "========================================="
echo "All scan points processed!"
echo "End time: $(date)"
echo "Serial Number: $SN"
echo "========================================="

rm -f "$PROCESSED_LOG"
```
