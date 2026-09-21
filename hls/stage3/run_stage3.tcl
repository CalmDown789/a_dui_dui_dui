set script_dir [file dirname [file normalize [info script]]]
set work_dir [file join $script_dir work]
cd $script_dir

open_project -reset $work_dir
set_top stage3_pipeline_top
add_files stage3_pipeline.cpp -cflags "-I."
add_files conv3x3_layer.cpp -cflags "-I."
add_files postprocess.cpp -cflags "-I."
add_files pixel_shuffle.cpp -cflags "-I."
add_files -tb stage3_pipeline_tb.cpp -cflags "-I."

open_solution -reset solution1 -flow_target vivado
set_part {xc7z020clg400-1}
create_clock -period 10 -name default

csim_design
csynth_design

exit
