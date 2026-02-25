#!/bin/bash
#SBATCH --job-name=live_precal_scan
#SBATCH --time=06:00:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G

module -q load GCC/11.3.0 OpenMPI/4.1.4
module -q load ROOT/6.26.10
module -q unload SciPy-bundle/2022.05
source /data/gpfs/projects/punim1378/earles/pyrate/pyrate_venv/bin/activate

# Get serial number from command line argument
SN=$1
if [ -z "$SN" ]; then
    echo "ERROR: No serial number provided"
    echo "Usage: sbatch RUN.slurm <SERIAL_NUMBER>"
    exit 1
fi

HVNOMLL=$2
if [ -z "$HVNOMLL" ]; then
    echo "ERROR: No serial number provided"
    echo "Usage: sbatch RUN.slurm <SERIAL_NUMBER>"
    exit 1
fi

HVNOML=$3
if [ -z "$HVNOML" ]; then
    echo "ERROR: No serial number provided"
    echo "Usage: sbatch RUN.slurm <SERIAL_NUMBER>"
    exit 1
fi

HVNOM=$4
if [ -z "$HVNOM" ]; then
    echo "ERROR: No serial number provided"
    echo "Usage: sbatch RUN.slurm <SERIAL_NUMBER>"
    exit 1
fi

HVNOMH=$5
if [ -z "$HVNOMH" ]; then
    echo "ERROR: No serial number provided"
    echo "Usage: sbatch RUN.slurm <SERIAL_NUMBER>"
    exit 1
fi

HVNOMHH=$1
if [ -z "$HVNOMHH" ]; then
    echo "ERROR: No serial number provided"
    echo "Usage: sbatch RUN.slurm <SERIAL_NUMBER>"
    exit 1
fi

# Define template file path
TEMPLATE_FILE="/data/gpfs/projects/punim1378/earles/Precal_GUI/config/R12860_full_live_monitor_speed_template.yaml"
# Define output directory for generated YAML files
YAML_OUTPUT_DIR="/data/gpfs/projects/punim1378/earles/Precal_GUI/config/test_yamls/${SN}"
mkdir -p "$YAML_OUTPUT_DIR"

echo "Starting live processing for Serial Number: $SN"
echo "Template file: $TEMPLATE_FILE"
echo "Start time: $(date)"

THETA_VALUES=(0 10 10 10 10 20 20 20 20 30 30 30 30 40 40 40 40 50 50 50 50)

TOTAL_POINTS=21
WAIT_INTERVAL=30

PROCESSED_LOG="/data/gpfs/projects/punim1378/earles/Precal_GUI/processed_files_${SN}.log"
touch "$PROCESSED_LOG"

echo "Monitoring for TXT files with SN: $SN"
echo "Will check every ${WAIT_INTERVAL} seconds"
echo "----------------------------------------"

for i in $(seq 0 $((TOTAL_POINTS - 1))); do
    THETA=${THETA_VALUES[$i]}
    PHI=${PHI_VALUES[$i]}
    ROOT_OUT_DIR="/data/gpfs/projects/punim1378/earles/LIVE_Scanning_ROOT_saves/${SN}/live_monitor_${SN}_theta${THETA}_phi${PHI}"
    echo ""
    echo "=== Scan Point $((i + 1))/$TOTAL_POINTS: theta=${THETA}, phi=${PHI} ==="
    
    PROCESSED=false
    
    while [ "$PROCESSED" = false ]; do
        # Search for the DIRECTORY containing txt files
        SEARCH_DIR="/data/gpfs/projects/punim1378/earles/WaveDumpSaves/wavedump_output_*/${SN}/wavesave_theta${THETA}_phi${PHI}"
        
        # Find directories that exist and contain txt files
        RUN_DIR=$(find /data/gpfs/projects/punim1378/earles/WaveDumpSaves/wavedump_output_*/${SN}/wavesave_theta${THETA}_phi${PHI} -type d -maxdepth 0 2>/dev/null | head -n 1)
        
        if [ -n "$RUN_DIR" ]; then
            # Check for specific channel files (use ls to check with wildcards)
            CH0_EXISTS=false
            CH1_EXISTS=false
            CH2_EXISTS=false
            CH3_EXISTS=false
            
            # Use ls to check if files matching the pattern exist
            ls "$RUN_DIR"/wave0*.txt >/dev/null 2>&1 && CH0_EXISTS=true
            ls "$RUN_DIR"/wave1*.txt >/dev/null 2>&1 && CH1_EXISTS=true
            ls "$RUN_DIR"/wave2*.txt >/dev/null 2>&1 && CH2_EXISTS=true
            ls "$RUN_DIR"/wave3*.txt >/dev/null 2>&1 && CH3_EXISTS=true
            
            # Check if we have the required channels (ch0, ch1, and either ch2 or ch3)
            CH2_OR_CH3_EXISTS=false
            if [ "$CH2_EXISTS" = true ] || [ "$CH3_EXISTS" = true ]; then
                CH2_OR_CH3_EXISTS=true
            fi
            
            CHANNELS=""
            [ "$CH0_EXISTS" = true ] && CHANNELS="${CHANNELS}0, "
            [ "$CH1_EXISTS" = true ] && CHANNELS="${CHANNELS}1, "
            [ "$CH2_EXISTS" = true ] && CHANNELS="${CHANNELS}2, "
            [ "$CH3_EXISTS" = true ] && CHANNELS="${CHANNELS}3, "
            # Remove trailing comma and space
            CHANNELS="${CHANNELS%, }"

            PMT_CHANNEL=""
            if [ "$CH2_EXISTS" = true ]; then
                PMT_CHANNEL="2"
            elif [ "$CH3_EXISTS" = true ]; then
                PMT_CHANNEL="3"
            fi

            if [ "$CH0_EXISTS" = true ] && [ "$CH1_EXISTS" = true ] && [ "$CH2_OR_CH3_EXISTS" = true ]; then
                # Check if already processed
                if grep -q "$RUN_DIR" "$PROCESSED_LOG"; then
                    echo "  [$(date +%H:%M:%S)] Directory already processed: $RUN_DIR"
                    PROCESSED=true
                else
                    # Count and report which files are present
                    TXT_COUNT=$(ls "$RUN_DIR"/wave*.txt 2>/dev/null | wc -l)
                    CHANNEL_INFO="ch0, ch1"
                    [ "$CH2_EXISTS" = true ] && CHANNEL_INFO="${CHANNEL_INFO}, ch2"
                    [ "$CH3_EXISTS" = true ] && CHANNEL_INFO="${CHANNEL_INFO}, ch3"
                    
                    echo "  [$(date +%H:%M:%S)] Found directory with $TXT_COUNT txt files ($CHANNEL_INFO): $RUN_DIR"
                    
                    GENERATED_YAML="${YAML_OUTPUT_DIR}/config_${SN}_theta${THETA}_phi${PHI}.yaml"
                    
                    # Generate YAML
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
                        
                        # Create output directory and run pyrate
                        mkdir -p "$ROOT_OUT_DIR"
                        pyrate -c "$GENERATED_YAML"
                        
                        if [ $? -eq 0 ]; then
                            echo "  ✓ ROOT file generation completed successfully"
                            
                            # Now wait for and process the ROOT file
                            echo "  Waiting for ROOT file to be ready..."
                            ROOT_FILE_PATTERN="${ROOT_OUT_DIR}.root"
                            ROOT_READY=false
                            
                            # Wait for ROOT file to appear and stabilize
                            while [ "$ROOT_READY" = false ]; do
                                ROOT_FILE=$(ls -t $ROOT_FILE_PATTERN 2>/dev/null | head -n 1)
                                if [ -n "$ROOT_FILE" ]; then
                                    # Check if file is complete (size not changing)
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
                            
                            # Run Python analysis script
                            echo "  Running Python analysis script..."
                            python3 /data/gpfs/projects/punim1378/earles/Precal_GUI/live_monitoring_data_analysis.py "$SN" "$THETA" "$PHI"
                            
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