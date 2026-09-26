# Post-route physical optimization evidence

Local stage: `_synth_bc/postroute200_v1_pressure000_try1`. Both binary DCPs remain there; Git contains their hashes, exact runners and text reports. The baseline implementation evidence identifies RTL, constraints and ROM inputs. Reproduction: rebuild that baseline, prepare a NEW stage with the recorded pressure, then run `postroute_finish/finish.tcl`. Record the new DCP hash instead of assuming binary-identical ZIP timestamps. Completion does not imply timing acceptance.
