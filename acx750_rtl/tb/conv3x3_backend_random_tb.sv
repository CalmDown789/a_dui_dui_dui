`timescale 1ns / 1ps

module conv3x3_backend_random_tb;

    localparam integer CHANNELS = 3;
    localparam integer EXPECTED_GROUPS = 96;

    reg clk;
    reg rst;
    reg in_valid;

    reg signed [7:0] x00, x01, x02, x10, x11, x12, x20, x21, x22;
    reg signed [7:0] k00, k01, k02, k10, k11, k12, k20, k21, k22;
    reg signed [31:0] bias;

    wire signed [31:0] result;
    wire result_valid;

    integer stimulus_fd;
    integer expected_fd;
    integer scan_count;
    integer expected_scan_count;
    integer gap_cycles;
    integer bias_value;
    integer xv0, xv1, xv2, xv3, xv4, xv5, xv6, xv7, xv8;
    integer kv0, kv1, kv2, kv3, kv4, kv5, kv6, kv7, kv8;
    integer expected_value;
    integer error_count;
    integer result_count;
    integer sample_count;
    integer timeout_count;

    conv3x3_backend #(
        .ACT_W(8),
        .WGT_W(8),
        .ACC_W(32),
        .CHANNELS(CHANNELS)
    ) dut (
        .clk(clk), .rst(rst), .in_valid(in_valid),
        .x00(x00), .x01(x01), .x02(x02),
        .x10(x10), .x11(x11), .x12(x12),
        .x20(x20), .x21(x21), .x22(x22),
        .k00(k00), .k01(k01), .k02(k02),
        .k10(k10), .k11(k11), .k12(k12),
        .k20(k20), .k21(k21), .k22(k22),
        .bias(bias),
        .result(result), .result_valid(result_valid)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    task drive_idle_cycle;
        begin
            @(negedge clk);
            in_valid = 1'b0;
        end
    endtask

    task drive_sample;
        begin
            repeat (gap_cycles)
                drive_idle_cycle();

            @(negedge clk);
            x00=xv0; x01=xv1; x02=xv2; x10=xv3; x11=xv4;
            x12=xv5; x20=xv6; x21=xv7; x22=xv8;
            k00=kv0; k01=kv1; k02=kv2; k10=kv3; k11=kv4;
            k12=kv5; k20=kv6; k21=kv7; k22=kv8;
            bias=bias_value;
            in_valid=1'b1;
            sample_count=sample_count+1;
        end
    endtask

    always @(posedge clk) begin
        #1;
        if (result_valid) begin
            expected_scan_count = $fscanf(expected_fd, "%d\n", expected_value);
            if (expected_scan_count != 1) begin
                $display("MISSING_EXPECTED_VALUE result_index=%0d", result_count);
                error_count = error_count + 1;
            end else if (result !== expected_value) begin
                $display("RANDOM_RESULT_MISMATCH index=%0d got=%0d expected=%0d",
                         result_count, result, expected_value);
                error_count = error_count + 1;
            end
            result_count = result_count + 1;
        end
    end

    initial begin
        rst=1'b1; in_valid=1'b0; bias=0;
        x00=0; x01=0; x02=0; x10=0; x11=0;
        x12=0; x20=0; x21=0; x22=0;
        k00=0; k01=0; k02=0; k10=0; k11=0;
        k12=0; k20=0; k21=0; k22=0;
        error_count=0; result_count=0; sample_count=0; timeout_count=0;

        stimulus_fd = $fopen("backend_stimulus.txt", "r");
        expected_fd = $fopen("backend_expected.txt", "r");
        if ((stimulus_fd == 0) || (expected_fd == 0)) begin
            $display("VECTOR_FILE_OPEN_FAIL");
            $finish;
        end

        repeat (3) @(posedge clk);
        @(negedge clk);
        rst=1'b0;

        while (!$feof(stimulus_fd)) begin
            scan_count = $fscanf(
                stimulus_fd,
                "%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d\n",
                gap_cycles, bias_value,
                xv0, xv1, xv2, xv3, xv4, xv5, xv6, xv7, xv8,
                kv0, kv1, kv2, kv3, kv4, kv5, kv6, kv7, kv8
            );
            if (scan_count == 20)
                drive_sample();
            else if (!$feof(stimulus_fd)) begin
                $display("STIMULUS_PARSE_FAIL fields=%0d sample=%0d", scan_count, sample_count);
                error_count = error_count + 1;
                $finish;
            end
        end

        @(negedge clk);
        in_valid=1'b0;

        while ((result_count < EXPECTED_GROUPS) && (timeout_count < 100)) begin
            @(posedge clk);
            timeout_count=timeout_count+1;
        end

        if (sample_count != EXPECTED_GROUPS * CHANNELS) begin
            $display("SAMPLE_COUNT_MISMATCH got=%0d expected=%0d",
                     sample_count, EXPECTED_GROUPS * CHANNELS);
            error_count=error_count+1;
        end
        if (result_count != EXPECTED_GROUPS) begin
            $display("RESULT_COUNT_MISMATCH got=%0d expected=%0d",
                     result_count, EXPECTED_GROUPS);
            error_count=error_count+1;
        end

        if (error_count == 0)
            $display("ACX750_CONV3X3_BACKEND_RANDOM_TEST_PASS groups=%0d samples=%0d",
                     result_count, sample_count);
        else
            $display("ACX750_CONV3X3_BACKEND_RANDOM_TEST_FAIL errors=%0d", error_count);

        $fclose(stimulus_fd);
        $fclose(expected_fd);
        #10;
        $finish;
    end

endmodule
