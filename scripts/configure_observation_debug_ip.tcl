# Caller must open a Vivado project and define ip_dir before sourcing.
if {![info exists ip_dir]} {error "ip_dir must be set before sourcing this file"}
if {[llength [get_projects -quiet]] != 1} {error "an open project is required"}
file mkdir $ip_dir
file mkdir "$ip_dir/ila_obs_snapshot"
file mkdir "$ip_dir/vio_obs_snapshot_ctrl"

set ila_defs [get_ipdefs -all xilinx.com:ip:ila:*]
set vio_defs [get_ipdefs -all xilinx.com:ip:vio:*]
if {[llength $ila_defs] == 0 || [llength $vio_defs] == 0} {error "ILA or VIO IP definition unavailable"}
set ila_vlnv [lindex $ila_defs 0]
set vio_vlnv [lindex $vio_defs 0]
set ila_version [lindex [split $ila_vlnv :] 3]
set vio_version [lindex [split $vio_vlnv :] 3]
puts "OBS_IP_VERSIONS ila=$ila_vlnv vio=$vio_vlnv"

create_ip -name ila -vendor xilinx.com -library ip -version $ila_version \
    -module_name ila_obs_snapshot -dir "$ip_dir/ila_obs_snapshot"
set ila [get_ips ila_obs_snapshot]
set ila_cfg [list \
    CONFIG.C_CLK_FREQ {150} \
    CONFIG.C_CLK_PERIOD {6.666667} \
    CONFIG.C_DATA_DEPTH {1024} \
    CONFIG.C_NUM_OF_PROBES {10} \
    CONFIG.C_PROBE0_WIDTH {1} \
    CONFIG.C_PROBE1_WIDTH {934} \
    CONFIG.C_PROBE2_WIDTH {4} \
    CONFIG.C_PROBE3_WIDTH {1} \
    CONFIG.C_PROBE4_WIDTH {1} \
    CONFIG.C_PROBE5_WIDTH {1} \
    CONFIG.C_PROBE6_WIDTH {1} \
    CONFIG.C_PROBE7_WIDTH {1} \
    CONFIG.C_PROBE8_WIDTH {1} \
    CONFIG.C_PROBE9_WIDTH {1}]
set_property -dict $ila_cfg $ila
# Full 934-bit snapshot is captured as data. Trigger on the nine small probes.
# TYPE=1 is DATA in the installed ILA 6.2 component.xml.
set_property CONFIG.C_PROBE1_TYPE 1 $ila

create_ip -name vio -vendor xilinx.com -library ip -version $vio_version \
    -module_name vio_obs_snapshot_ctrl -dir "$ip_dir/vio_obs_snapshot_ctrl"
set vio [get_ips vio_obs_snapshot_ctrl]
set vio_cfg [list \
    CONFIG.C_NUM_PROBE_IN {6} \
    CONFIG.C_NUM_PROBE_OUT {1} \
    CONFIG.C_PROBE_IN0_WIDTH {256} \
    CONFIG.C_PROBE_IN1_WIDTH {256} \
    CONFIG.C_PROBE_IN2_WIDTH {256} \
    CONFIG.C_PROBE_IN3_WIDTH {166} \
    CONFIG.C_PROBE_IN4_WIDTH {1} \
    CONFIG.C_PROBE_IN5_WIDTH {5} \
    CONFIG.C_PROBE_OUT0_WIDTH {5} \
    CONFIG.C_PROBE_OUT0_INIT_VAL {0x00}]
set_property -dict $vio_cfg $vio

foreach {ip properties} [list \
    $ila [list CONFIG.C_CLK_FREQ CONFIG.C_CLK_PERIOD CONFIG.C_DATA_DEPTH CONFIG.C_NUM_OF_PROBES \
        CONFIG.C_PROBE0_WIDTH CONFIG.C_PROBE1_WIDTH CONFIG.C_PROBE2_WIDTH \
        CONFIG.C_PROBE3_WIDTH CONFIG.C_PROBE4_WIDTH CONFIG.C_PROBE5_WIDTH \
        CONFIG.C_PROBE6_WIDTH CONFIG.C_PROBE7_WIDTH CONFIG.C_PROBE8_WIDTH CONFIG.C_PROBE9_WIDTH] \
    $vio [list CONFIG.C_NUM_PROBE_IN CONFIG.C_NUM_PROBE_OUT \
        CONFIG.C_PROBE_IN0_WIDTH CONFIG.C_PROBE_IN1_WIDTH CONFIG.C_PROBE_IN2_WIDTH \
        CONFIG.C_PROBE_IN3_WIDTH CONFIG.C_PROBE_IN4_WIDTH CONFIG.C_PROBE_IN5_WIDTH \
        CONFIG.C_PROBE_OUT0_WIDTH CONFIG.C_PROBE_OUT0_INIT_VAL]] {
    set name [get_property NAME $ip]
    foreach key $properties {
        puts "OBS_IP_CONFIG $name $key=[get_property $key $ip]"
    }
    generate_target all $ip
}
puts "OBS_IP_GENERATION_COMPLETE"
