# Working notes

2026_02_26: 

## Future Tasks:
As of 20260116:
1. Re-implement the refernce histogram overlay
2. Implement a signal-to-noise ratio measurement for dar worthyness check - add this to the "helathy/poor" condition
3. An overall plot/diagram showing the "helathy/poor" condition in relation to the PMT positioning
4. The HV Check plot needs to be finished and tested, report errors etc
5. Analysis methods need to align with actual analysis
6. Fit data needs to be reported on the charge distributions
7. Channel 4 needs to be uncommented for the refernce PMT data use

## HV Check Concept/Plan
User enters SN and HV_NOMINAL value 
|
|-- GUI outputs:
    |-- NOMINAL-100
    |-- NOMINAL-50
    |-- NOMINAL 
    |-- NOMINAL+50
    |-- NOMINAL+100   
|-- These values populate the server commands: 
    i.e.
    ```
        sbatch ./HV_CHECK.slurm {SN} {HV_NOMINAL+0} {HV_NOMINAL+50} {HV_NOMINAL-50} {HV_NOMINAL+100} {HV_NOMINAL-100}
    ```    
|
|-- User will then need to change the HV to those values on Han's GUI and that will output waveform files:    

```
    /WaveDumpSaves/wavedump_output_{datetime}/{SN}/wavesave_HV_CHECK/wave{ch_no}save_HV_{HV_NOMINAL-100}.txt
    /WaveDumpSaves/wavedump_output_{datetime}/{SN}/wavesave_HV_CHECK/wave{ch_no}save_HV_{HV_NOMINAL-050}.txt
    /WaveDumpSaves/wavedump_output_{datetime}/{SN}/wavesave_HV_CHECK/wave{ch_no}save_HV_{HV_NOMINAL+000}.txt
    /WaveDumpSaves/wavedump_output_{datetime}/{SN}/wavesave_HV_CHECK/wave{ch_no}save_HV_{HV_NOMINAL+050}.txt
    /WaveDumpSaves/wavedump_output_{datetime}/{SN}/wavesave_HV_CHECK/wave{ch_no}save_HV_{HV_NOMINAL+100}.txt
    
```


### On server:
The batch job command will utilise the automatically input 
to:
1. Generate yaml configs
2. Run through Pyrate to produce ROOT
3. Python script will extract charge distributions and fit to 
4. Mean from SPE utilised to determine Gain estimate
5. Plot of voltage dependent gain produced, with estimate of optimum HV value for 1x10^7 gain (HV value output in txt)
6. Best HV value and gain vs V plot synced back to GUI

GUI then displays:
    Gain vs Voltage plot
    
    G ^
    A |
    I |              *
    N |           *
     1^7-------* 
      |     * |
      |  *    |
      |_______|___________>
              |    VOLTAGE
        optimum HV 

   Optimum HV value for a gain of 1.00x10^7
