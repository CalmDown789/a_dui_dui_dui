from pathlib import Path


root = Path(__file__).resolve().parents[1]
tb_dir = root / "overlay" / "multiframe" / "tb"
source = tb_dir / "tb_c_multiframe_uart.v"
target = tb_dir / "tb_c_controlled_pause.v"
if target.exists():
    raise SystemExit(f"preserving existing testbench: {target}")
text = source.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    text = text.replace(old, new, 1)


replace_once("module tb_c_multiframe_uart;", "module tb_c_controlled_pause;", "module name")
replace_once(
    ".USE_MMCM(0), .CLK_HZ(CLK_HZ), .UART_BAUD(UART_BAUD)\n",
    ".USE_MMCM(0), .CLK_HZ(CLK_HZ), .UART_BAUD(UART_BAUD),\n        .OBS_TEST_PAUSE_ENABLE(1)\n",
    "test-only pause enable",
)
replace_once(
    "    wire dbg_core_busy, dbg_core_done;\n",
    """    wire dbg_core_busy, dbg_core_done;
    reg [4:0] obs_control = 5'd0;
    wire [933:0] obs_snapshot_data;
    wire obs_snapshot_valid;
    wire [4:0] obs_snapshot_count;
    wire obs_snapshot_overflow;
    wire obs_pause_effective;
    wire obs_pause_forced_block;
    wire obs_clk;
    integer forced_block_cycles = 0;
    integer pause_injections = 0;
    integer pause_countdown = 0;
    reg pause_injected_this_frame = 1'b0;
""",
    "debug declarations",
)
replace_once(
    """        .dbg_obs_control(5'd0),
        .dbg_obs_snapshot_data(), .dbg_obs_snapshot_valid(),
        .dbg_obs_snapshot_count(), .dbg_obs_snapshot_overflow(),
        .dbg_obs_pause_effective(), .dbg_obs_pause_forced_block(), .dbg_obs_clk()
""",
    """        .dbg_obs_control(obs_control),
        .dbg_obs_snapshot_data(obs_snapshot_data),
        .dbg_obs_snapshot_valid(obs_snapshot_valid),
        .dbg_obs_snapshot_count(obs_snapshot_count),
        .dbg_obs_snapshot_overflow(obs_snapshot_overflow),
        .dbg_obs_pause_effective(obs_pause_effective),
        .dbg_obs_pause_forced_block(obs_pause_forced_block), .dbg_obs_clk(obs_clk)
""",
    "observation debug ports",
)
replace_once(
    "    function [31:0] crc32_byte;\n",
    """    always @(posedge clk) begin
        if (rst_n && obs_pause_forced_block)
            forced_block_cycles = forced_block_cycles + 1;
    end

    // Inject one short pause per frame only when B presents a beat that C
    // could otherwise accept. This makes the forced block causally observable.
    always @(negedge clk) begin
        if (!rst_n) begin
            obs_control = 5'd0;
            pause_countdown = 0;
            pause_injected_this_frame = 1'b0;
        end else begin
            if (dbg_frame_start)
                pause_injected_this_frame = 1'b0;
            if (obs_control[4]) begin
                if (pause_countdown > 0)
                    pause_countdown = pause_countdown - 1;
                if (pause_countdown == 0)
                    obs_control[4] = 1'b0;
            end
            if (dbg_frame_active && !pause_injected_this_frame &&
                dut.obs_b_out_valid && dut.u_core.out_ready_base && !obs_control[4]) begin
                obs_control[4] = 1'b1;
                pause_countdown = 16;
                pause_injected_this_frame = 1'b1;
                pause_injections = pause_injections + 1;
                $display("CONTROLLED_PAUSE_START frame=%0d", dbg_expected_frame_id);
            end
        end
    end

    task check_observation;
        input [3:0] slot;
        input [31:0] expected_id;
        begin
            obs_control[3:0] = slot;
            #1;
            if (obs_snapshot_valid !== 1'b1) begin
                $display("[FAIL] observation slot %0d invalid", slot);
                errors = errors + 1;
            end
            if (obs_snapshot_data[4:1] !== slot || obs_snapshot_data[36:5] !== expected_id) begin
                $display("[FAIL] observation slot/id got=%0d/%08x expected=%0d/%08x",
                         obs_snapshot_data[4:1], obs_snapshot_data[36:5], slot, expected_id);
                errors = errors + 1;
            end
            if (obs_snapshot_data[37] !== 1'b1 || obs_snapshot_data[38] !== 1'b0 ||
                obs_snapshot_data[39] !== 1'b1 || obs_snapshot_data[40] !== 1'b1 ||
                obs_snapshot_data[41] !== 1'b1 || obs_snapshot_data[933] !== 1'b0) begin
                $display("[FAIL] observation completion flags slot=%0d", slot);
                errors = errors + 1;
            end
            if (obs_snapshot_data[73:42] !== IN_BYTES ||
                obs_snapshot_data[105:74] !== OUT_BYTES ||
                obs_snapshot_data[121:106] !== 16'd2 ||
                obs_snapshot_data[129:122] !== 8'd1 ||
                obs_snapshot_data[161:130] !== OUT_BYTES) begin
                $display("[FAIL] observation stream counts slot=%0d in=%0d out=%0d stripe=%0d frame=%0d uart=%0d",
                         slot, obs_snapshot_data[73:42], obs_snapshot_data[105:74],
                         obs_snapshot_data[121:106], obs_snapshot_data[129:122],
                         obs_snapshot_data[161:130]);
                errors = errors + 1;
            end
            if (obs_snapshot_data[162] || obs_snapshot_data[163] || obs_snapshot_data[164] ||
                obs_snapshot_data[196:165] !== 32'd0 || obs_snapshot_data[228:197] !== 32'd0) begin
                $display("[FAIL] observation errors slot=%0d", slot);
                errors = errors + 1;
            end
            if (obs_snapshot_data[772:741] !== 32'd0 || obs_snapshot_data[804:773] !== 32'd0) begin
                $display("[FAIL] hold violation in slot=%0d c2b=%0d bout=%0d",
                         slot, obs_snapshot_data[772:741], obs_snapshot_data[804:773]);
                errors = errors + 1;
            end
            if (obs_snapshot_data[868:805] == 64'd0 || obs_snapshot_data[932:869] == 64'd0) begin
                $display("[FAIL] pause evidence missing in slot=%0d request=%0d forced=%0d",
                         slot, obs_snapshot_data[868:805], obs_snapshot_data[932:869]);
                errors = errors + 1;
            end
            $display("OBSERVATION_FRAME slot=%0d frame_id=%0d input=%0d output=%0d pause=%0d forced=%0d hold=%0d/%0d",
                     slot, obs_snapshot_data[36:5], obs_snapshot_data[73:42],
                     obs_snapshot_data[105:74], obs_snapshot_data[868:805],
                     obs_snapshot_data[932:869], obs_snapshot_data[772:741],
                     obs_snapshot_data[804:773]);
        end
    endtask

    function [31:0] crc32_byte;
""",
    "pause driver, checks, and CRC function",
)
replace_once(
    """        if (errors == 0) begin
            $display("RESULT: PASS 2 consecutive UART frames, no reset, each %0d/%0d byte-exact",
                     OUT_BYTES, OUT_BYTES);
""",
    """        if (pause_injections != 2 || forced_block_cycles < 2 ||
            obs_snapshot_count != 5'd2 || obs_snapshot_overflow !== 1'b0) begin
            $display("[FAIL] controlled pause summary injections=%0d forced_cycles=%0d snapshots=%0d overflow=%0d",
                     pause_injections, forced_block_cycles, obs_snapshot_count, obs_snapshot_overflow);
            errors = errors + 1;
        end
        check_observation(4'd0, 32'd0);
        check_observation(4'd1, 32'd1);

        if (errors == 0) begin
            $display("RESULT: PASS controlled pause with two consecutive byte-exact UART frames; forced_block_cycles=%0d",
                     forced_block_cycles);
""",
    "controlled pause final acceptance",
)
target.write_text(text, encoding="ascii", newline="")
print(f"created {target}")
