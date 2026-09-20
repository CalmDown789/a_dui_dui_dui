set script_dir [file dirname [file normalize [info script]]]
set work_dir [file join $script_dir work]
cd $script_dir

open_project -reset $work_dir
set_top conv3x3_mac_top
add_files sr_primitives.cpp -cflags "-I."
add_files -tb sr_primitives_tb.cpp -cflags "-I."

open_solution -reset solution1 -flow_target vivado
set_part {xc7z020clg400-1}
create_clock -period 10 -name default

csim_design
csynth_design

exit
