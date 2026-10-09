# Independent characterization-only temporary JTAG. Root binds this exact SHA.
# Exactly one verified actual candidate BIT path; no Flash, PHY/BMCR/MDIO writes.
set lab_target_open 0
set lab_manager_open 0
set lab_connected 0
if {[catch {
    if {[llength $argv] != 1} {error "Exactly one preverified characterization BIT path required"}
    set lab_bit [file normalize [lindex $argv 0]]
    if {![file isfile $lab_bit] || [file size $lab_bit] <= 0 || [string tolower [file extension $lab_bit]] ne ".bit"} {
        error "Real root-issued candidate BIT missing/empty/invalid"
    }
    puts "CHARACTERIZATION_ONLY_SELECTED_BIT=$lab_bit"
    puts "LOCAL_BIT_AND_ROOT_MANIFEST_SHA_PRECHECK_REQUIRED=YES"
    open_hw_manager
    set lab_manager_open 1
    connect_hw_server -url localhost:3121
    set lab_connected 1
    set lab_targets [get_hw_targets]
    puts "CHARACTERIZATION_TARGETS=$lab_targets"
    if {[llength $lab_targets] != 1} {error "Expected one unambiguous C JTAG target"}
    set lab_target [lindex $lab_targets 0]
    if {![string match "*/Digilent/250520092545" $lab_target]} {error "Previously verified C cable identity differs"}
    current_hw_target $lab_target
    open_hw_target $lab_target
    set lab_target_open 1
    set lab_devices [get_hw_devices]
    puts "CHARACTERIZATION_DEVICES=$lab_devices"
    if {[llength $lab_devices] != 1 || [lindex $lab_devices 0] ne "xc7a200t_0"} {error "Expected only xc7a200t_0"}
    set lab_device [lindex $lab_devices 0]
    current_hw_device $lab_device
    set_property PROBES.FILE {} $lab_device
    set_property FULL_PROBES.FILE {} $lab_device
    refresh_hw_device $lab_device
    set lab_part [get_property PART $lab_device]
    set lab_id_hex [string tolower [get_property IDCODE_HEX $lab_device]]
    set lab_id_binary [get_property IDCODE $lab_device]
    puts "CHARACTERIZATION_JTAG_TARGET=$lab_target DEVICE=$lab_device PART=$lab_part IDCODE_HEX=$lab_id_hex IDCODE=$lab_id_binary"
    if {$lab_part ne "xc7a200t" || $lab_id_hex ne "13636093" || $lab_id_binary ne "00010011011000110110000010010011"} {
        error "C device PART/IDCODE differs"
    }
    set_property PROGRAM.FILE $lab_bit $lab_device
    program_hw_devices $lab_device
    refresh_hw_device $lab_device
    set lab_host_file [file normalize [get_property PROGRAM.FILE $lab_device]]
    puts "POST_PROGRAM_HOST_PROPERTY_PROGRAM_FILE=$lab_host_file"
    puts "HOST_PROGRAM_FILE_IS_NOT_BITSTREAM_READBACK=YES"
    if {$lab_host_file ne $lab_bit} {error "Host PROGRAM.FILE property differs"}
    set lab_done_internal [get_property REGISTER.CONFIG_STATUS.BIT13_DONE_INTERNAL_SIGNAL_STATUS $lab_device]
    set lab_done_pin [get_property REGISTER.CONFIG_STATUS.BIT14_DONE_PIN $lab_device]
    set lab_crc_error [get_property REGISTER.CONFIG_STATUS.BIT00_CRC_ERROR $lab_device]
    set lab_id_error [get_property REGISTER.CONFIG_STATUS.BIT15_IDCODE_ERROR $lab_device]
    puts "CHARACTERIZATION_CONFIG_STATUS DONE_INTERNAL=$lab_done_internal DONE_PIN=$lab_done_pin CRC_ERROR=$lab_crc_error IDCODE_ERROR=$lab_id_error"
    report_property $lab_device
    if {$lab_done_internal ne "1" || $lab_done_pin ne "1" || $lab_crc_error ne "0" || $lab_id_error ne "0"} {
        error "Actual configuration status unsuccessful"
    }
    puts "CHARACTERIZATION_ONLY_JTAG_CONFIG_STATUS=YES"
    puts "PHYSICAL_IO_SIGNOFF_AND_NETWORK_VIDEO_PERMISSION=FALSE"
} lab_error]} {
    puts stderr "CHARACTERIZATION_ONLY_JTAG_FAILED: $lab_error"
    if {[info exists ::errorInfo]} {puts stderr $::errorInfo}
    if {$lab_target_open} {catch {close_hw_target}}
    if {$lab_connected} {catch {disconnect_hw_server}}
    if {$lab_manager_open} {catch {close_hw_manager}}
    exit 1
}
if {$lab_target_open} {close_hw_target}
if {$lab_connected} {disconnect_hw_server}
if {$lab_manager_open} {close_hw_manager}
exit 0
