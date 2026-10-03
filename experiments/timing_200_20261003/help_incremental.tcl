# Read-only installed 2025.2 command documentation for the next candidate.
foreach command {read_checkpoint place_design report_incremental_reuse} {
    puts "INSTALLED_COMMAND_HELP=$command"
    if {[catch {help $command} result]} {puts "HELP_UNAVAILABLE=$result"} else {puts $result}
}
