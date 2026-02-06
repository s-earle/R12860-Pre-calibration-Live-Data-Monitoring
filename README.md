# R12860-Pre-calibration-Live-Data-Monitoring
GUI that shows current data quality

## Quick start Instructions:
How to run and use the live monitoring software:

 Open terminal and enter command:
```
streamlit run R12860_LIVE_MONITORING.py --server.port 9602
```
A Streamlit window will open in the installed browser, which can be employed as follows:

1. Click Start under STEP 1: Background Executor
2. Check Remote server configuration under STEP 2
   a. Ensure ssh keys are configured for the server user login on local machine
3. Clean-up local data files under STEP 3 - it is recomended to clear all data now
4. Enter the PMT serial number under STEP 4 and hit 'enter'
5. Click 'RUN LIVE MONITORING
6. Once scan has completed, either Flag or archive data depending on data quality - archiving will occur automatically when the next scan begins 

## Set-up Instructions
If a new user is configuring the local machine and server for the first time, they must first set-up a ssh-key for the local machine for the server user login that will be used. Github guide is [here](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent).


# Server-side:
Pyrate will need to be installed on the server for the appropriate user. Make a directory for the live monitoring to run and copy the contents of the server-side directory into it. 

**Pyrate**
```
cd user/project/directory

git clone pyrate (will insert actual command)

cd pyrate

source setup.sh
```

**Live-Monitoring script Set-up**
```
cd user/project/directory

mkdir _R12860_LIVE_MONITOR_PROCESSING

cd _R12860_LIVE_MONITOR_PROCESSING

```
If working on Spartan Unimelb:
```
git clone https://github.com/s-earle/R12860-Pre-calibration-Live-Data-Monitoring/tree/main/_server-side_processing_/spartan_hpc_unimelb_slurm
```
If working on Sukap:
```
git clone https://github.com/s-earle/R12860-Pre-calibration-Live-Data-Monitoring/tree/main/_server-side_processing_/sukap_
```


**Requirements:**
Streamlit and some of its extensions will need to be installed via terminal 
```
pip install streamlit

pip install streamlit-autorefresh

pip install streamlit-extras
```
PMT Serial Number

## Workflow
The Live Monitoring GUI sends a job to be executed on a server cluster. This job runs an algorithm to process data quickly and sends data back to the GUI operator. This is to ensure no faults have occurred during data acquisition. The GUI syncronises with the server cluster, receiving a charge distribution plot and a measured value of gain of the PMT. This data is then loaded into the data grid and indicates to the operator whether the gain is within an appropriate operating range or not. 

## Operation 
The software requires a background script to be running - "background_executor". This is started on the left-most panel in the GUI. The background_executor enables the software to run automatically while still being interacted with. 
The server connection details are then confirmed. This is via ssh, and the user confirms what batch script is run on the server cluster. 
The GUI software stores png and txt files locally for the current run. These need to be delete and can be done so in the drop down bar. 

The operator now _must_ enter the PMT serial number and press enter. Once that is done, the data monitoring can begin. 

The automatic data monitoring will send a command to the server cluster to look for new data. Once the new data is written, the server will process the data into a ROOT file and utilise a python script to output a charge distribution png file and then using zfit will determine the gain of the PMT at the corresponding coordinate and out the gain in a txt file. Those files will then be copied from the server to the local machine automatically through the sync function, and present the 2 files in the Live Data Grid. 

If any data points fall outside the healthy gain range, the operator _must_ flag the data. This will move the data from the operating directory into the FLAG directory. If all the data points are healthy, the operator can archive the data which will move the data into the archive directory. This archiving will also happen automatically when a new scan monitoring run is begun. 
