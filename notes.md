# Working notes

2026016: Currently the GUI is operating at a shortened timeframe which is likely producing bugs when it executes server commands and server sync. 

## Future Tasks:
As of 20260116:
1. ~~Need a reference histogram - this will probably be good to source from the reference PMT, as well as a good histogram ~~
2. ~~Having error bars will also be good so the shifter understands if the system is within operating range ~~
3. A check for darkness - measure the rates - maybe the pedestal ?
4. How can we use this for cross calibration?
5. Can we use this for a High Voltage scan? 
6. Need to implement a if crash - kill server jobs
7. With reference sensors, can/how use SiPM?
8. Reference sensors may be different tabs on LHS
9. Get it all visible on one screen
10. Faster - 2 jobs that run -- first one runs 10% of the data to quickly send the charge info and the the 2nd is the whole lot?
11. ~~Auto-stop~~ / and not scancel all jobs for user - just job number
12. Add ch4

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

*-------------------------------------------------------------------*
| On server:                                                        |

| The batch job command will utilise the automatically input values |

| to:                                                               |

| 1. Generate yaml configs                                          |

| 2. Run through Pyrate to produce ROOT                             |

| 3. Python script will extract charge distributions and fit to SPE |

| 4. Mean from SPE utilised to determine Gain estimate              |

| 5. Plot of voltage dependent gain produced, with estimate of      |

|    optimum HV value for 1x10^7 gain (HV value output in txt)      |

| 6. Best HV value and gain vs V plot synced back to GUI            |

*-------------------------------------------------------------------*

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
