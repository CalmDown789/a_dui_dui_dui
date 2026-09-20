set script_dir [file dirname [file normalize [info script]]]
set work_dir [file join $script_dir work]
cd $script_dir

open_project -reset $work_dir
set_top add_one
add_files add_one.cpp
add_files -tb add_one_tb.cpp

open_solution -reset solution1 -flow_target vivado
set_part {xc7z020clg400-1}
create_clock -period 10 -name default

csim_design
csynth_design

exit
