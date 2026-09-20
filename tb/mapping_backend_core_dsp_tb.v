`timescale 1ns / 1ps

// Joint self-check for the verified DSP dot9 pipeline followed by the
// 12-input-channel sequential accumulator. This starts from prepared 3x3
// windows; feature-map storage and multi-channel window scheduling are not
// part of this testbench.
module mapping_backend_core_dsp_tb;

    localparam integer ACT_W = 8;
    localparam integer WGT_W = 8;
    localparam integer DOT_W = 20;
    localparam integer ACC_W = 24;

    reg clk;
    reg rst;
    reg in_valid;

    reg signed [ACT_W-1:0] x00, x01, x02;
    reg signed [ACT_W-1:0] x10, x11, x12;
    reg signed [ACT_W-1:0] x20, x21, x22;
    reg signed [WGT_W-1:0] k00, k01, k02;
    reg signed [WGT_W-1:0] k10, k11, k12;
    reg signed [WGT_W-1:0] k20, k21, k22;
    reg signed [ACC_W-1:0] bias;

    wire signed [DOT_W-1:0] dot9;
    wire                    dot9_valid;
    wire signed [ACC_W-1:0] result;
    wire                    result_valid;

    integer error_count;
    integer expected_write;
    integer expected_read;
    integer model_count;
    integer completed_groups;
    reg signed [ACC_W-1:0] model_acc;
    reg signed [DOT_W-1:0] consumed_dot9;
    reg signed [ACC_W-1:0] consumed_bias;
    reg signed [DOT_W-1:0] expected_dot9 [0:31];

    mapping_backend_core_dsp #(
        .ACT_W    (ACT_W),
        .WGT_W    (WGT_W),
        .ACC_W    (ACC_W),
        .CHANNELS (12)
    ) dut (
        .clk          (clk),
        .rst          (rst),
        .in_valid     (in_valid),
        .x00          (x00), .x01(x01), .x02(x02),
        .x10          (x10), .x11(x11), .x12(x12),
        .x20          (x20), .x21(x21), .x22(x22),
        .k00          (k00), .k01(k01), .k02(k02),
        .k10          (k10), .k11(k11), .k12(k12),
        .k20          (k20), .k21(k21), .k22(k22),
        .bias         (bias),
        .dot9         (dot9),
        .dot9_valid   (dot9_valid),
        .result       (result),
        .result_valid (result_valid)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    // For the joint-interface test, k00=1 and all other weights are zero.
    // Therefore each prepared window's dot9 value equals x00 exactly.
    task send_scalar_window;
        input signed [ACT_W-1:0] value;
        begin
            @(negedge clk);
            in_valid = 1'b1;
            x00 = value;
            expected_dot9[expected_write] = value;
            expected_write = expected_write + 1;
        end
    endtask

    task send_bubble;
        begin
            @(negedge clk);
            in_valid = 1'b0;
            x00 = 8'sd99; // Deliberately meaningless while invalid.
        end
    endtask

    // Observe exactly what the accumulator consumes at each rising edge.
    // The wrapper exposes dot9/dot9_valid, so the model checks both the
    // pipeline order and the final 12-channel grouping.
    always @(posedge clk) begin
        if (rst) begin
            expected_read   = 0;
            model_count     = 0;
            completed_groups = 0;
            model_acc       = 0;
        end
        else if (dot9_valid) begin
            // Capture the old values that the accumulator samples on this
            // edge. After #1, the upstream pipeline may already show the next
            // dot9 value because nonblocking assignments have completed.
            consumed_dot9 = dot9;
            consumed_bias = bias;

            if (expected_read >= expected_write) begin
                $display("ERROR: unexpected dot9_valid at %0t", $time);
                error_count = error_count + 1;
            end
            else if (consumed_dot9 !== expected_dot9[expected_read]) begin
                $display("ERROR: dot9=%0d expected=%0d at %0t",
                         $signed(consumed_dot9),
                         $signed(expected_dot9[expected_read]),
                         $time);
                error_count = error_count + 1;
            end
            expected_read = expected_read + 1;

            if (model_count == 11) begin
                #1;
                if (result_valid !== 1'b1) begin
                    $display("ERROR: result_valid missing at %0t", $time);
                    error_count = error_count + 1;
                end
                if (result !== model_acc + $signed(consumed_dot9)
                                      + $signed(consumed_bias)) begin
                    $display("ERROR: result=%0d expected=%0d at %0t",
                             $signed(result),
                             $signed(model_acc + $signed(consumed_dot9)
                                              + $signed(consumed_bias)),
                             $time);
                    error_count = error_count + 1;
                end
                model_acc        = 0;
                model_count      = 0;
                completed_groups = completed_groups + 1;
            end
            else begin
                #1;
                if (result_valid !== 1'b0) begin
                    $display("ERROR: early result_valid at %0t", $time);
                    error_count = error_count + 1;
                end
                model_acc   = model_acc + $signed(consumed_dot9);
                model_count = model_count + 1;
            end
        end
        else begin
            #1;
            if (result_valid !== 1'b0) begin
                $display("ERROR: result_valid asserted without dot9_valid at %0t",
                         $time);
                error_count = error_count + 1;
            end
        end
    end

    initial begin
        rst          = 1'b1;
        in_valid     = 1'b0;
        bias         = -24'sd2;
        error_count  = 0;
        expected_write = 0;

        x00=0; x01=0; x02=0;
        x10=0; x11=0; x12=0;
        x20=0; x21=0; x22=0;

        k00=1; k01=0; k02=0;
        k10=0; k11=0; k12=0;
        k20=0; k21=0; k22=0;

        repeat (2) @(negedge clk);
        rst = 1'b0;

        // Group A: dot9 sum=22, bias=-2, expected result=20.
        send_scalar_window( 8'sd10);
        send_scalar_window(-8'sd3);
        send_scalar_window( 8'sd5);
        send_scalar_window( 8'sd0);
        send_bubble;
        send_scalar_window( 8'sd2);
        send_scalar_window(-8'sd4);
        send_scalar_window( 8'sd7);
        send_scalar_window( 8'sd1);
        send_scalar_window(-8'sd6);
        send_scalar_window( 8'sd8);
        send_bubble;
        send_scalar_window(-8'sd2);
        send_scalar_window( 8'sd4);
        send_bubble;

        wait (completed_groups == 1);

        // Group B: 12*(-1), bias=-3, expected result=-15.
        @(negedge clk);
        bias = -24'sd3;
        in_valid = 1'b1;
        x00 = -8'sd1;
        expected_dot9[expected_write] = -20'sd1;
        expected_write = expected_write + 1;
        repeat (11) send_scalar_window(-8'sd1);
        send_bubble;

        wait (completed_groups == 2);
        repeat (2) @(posedge clk);
        #1;

        if (expected_read != expected_write) begin
            $display("ERROR: consumed %0d dot9 values but expected %0d",
                     expected_read, expected_write);
            error_count = error_count + 1;
        end

        if (error_count == 0)
            $display("MAPPING_BACKEND_DSP_TEST_PASS");
        else
            $display("MAPPING_BACKEND_DSP_TEST_FAIL errors=%0d", error_count);

        $finish;
    end

endmodule
