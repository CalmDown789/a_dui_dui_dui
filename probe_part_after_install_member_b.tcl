puts "VIVADO_VERSION=[version -short]"
set p [get_parts -quiet xc7a200tfbg484-2]
puts "PART_COUNT=[llength $p]"
if {[llength $p]} {puts "PART_NAME=[get_property NAME $p]"}
