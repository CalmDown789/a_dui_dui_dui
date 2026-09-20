`timescale 1ns / 1ps

module dot9_pipelined_dsp_tb;

    reg clk;
    reg rst;
    reg in_valid;

    reg signed [7:0] x00, x01, x02;
    reg signed [7:0] x10, x11, x12;
    reg signed [7:0] x20, x21, x22;
    reg signed [7:0] k00, k01, k02;
    reg signed [7:0] k10, k11, k12;
    reg signed [7:0] k20, k21, k22;

    wire signed [19:0] dot9;
    wire               dot9_valid;

    integer error_count;
    integer cycle_after_reset;

    dot9_pipelined_dsp #(
        .ACT_W (8),
        .WGT_W (8)
    ) dut (
        .clk        (clk),
        .rst        (rst),
        .in_valid   (in_valid),
        .x00        (x00), .x01(x01), .x02(x02),
        .x10        (x10), .x11(x11), .x12(x12),
        .x20        (x20), .x21(x21), .x22(x22),
        .k00        (k00), .k01(k01), .k02(k02),
        .k10        (k10), .k11(k11), .k12(k12),
        .k20        (k20), .k21(k21), .k22(k22),
        .dot9       (dot9),
        .dot9_valid (dot9_valid)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    task drive_case_a;
        begin
            @(negedge clk);
            in_valid = 1'b1;
            x00=1; x01=2; x02=3;
            x10=4; x11=5; x12=6;
            x20=7; x21=8; x22=9;
            k00=1; k01=0; k02=-1;
            k10=1; k11=0; k12=-1;
            k20=1; k21=0; k22=-1;
        end
    endtask

    task drive_case_b;
        begin
            @(negedge clk);
            in_valid = 1'b1;
            x00=1; x01=1; x02=1;
            x10=1; x11=1; x12=1;
            x20=1; x21=1; x22=1;
            k00=1; k01=1; k02=1;
            k10=1; k11=1; k12=1;
            k20=1; k21=1; k22=1;
        end
    endtask

    task drive_case_c;
        begin
            @(negedge clk);
            in_valid = 1'b1;
            x00=-2; x01=-2; x02=-2;
            x10=-2; x11=-2; x12=-2;
            x20=-2; x21=-2; x22=-2;
            k00=1; k01=1; k02=1;
            k10=1; k11=1; k12=1;
            k20=1; k21=1; k22=1;
        end
    endtask

    task drive_bubble;
        begin
            @(negedge clk);
            in_valid = 1'b0;
        end
    endtask

    task check_valid_dot;
        input [19:0] expected;
        begin
            if (dot9_valid !== 1'b1) begin
                $display("VALID_MISSING at time %0t", $time);
                error_count = error_count + 1;
            end
            if (dot9 !== expected) begin
                $display("DOT_MISMATCH at time %0t: got %0d expected %0d",
                         $time, $signed(dot9), $signed(expected));
                error_count = error_count + 1;
            end
        end
    endtask

    always @(posedge clk) begin
        if (rst) begin
            cycle_after_reset = 0;
        end
        else begin
            cycle_after_reset = cycle_after_reset + 1;
            #1;
            case (cycle_after_reset)
                6: check_valid_dot(-20'sd6);
                7: check_valid_dot( 20'sd9);
                8: begin
                    if (dot9_valid !== 1'b0) begin
                        $display("BUBBLE_VALID_ERROR at time %0t", $time);
                        error_count = error_count + 1;
                    end
                end
                9: check_valid_dot(-20'sd18);
            endcase
        end
    end

    initial begin
        rst = 1'b1;
        in_valid = 1'b0;
        error_count = 0;
        cycle_after_reset = 0;

        x00=0; x01=0; x02=0;
        x10=0; x11=0; x12=0;
        x20=0; x21=0; x22=0;
        k00=0; k01=0; k02=0;
        k10=0; k11=0; k12=0;
        k20=0; k21=0; k22=0;

        repeat (2) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;

        drive_case_a;
        drive_case_b;
        drive_bubble;
        drive_case_c;

        @(negedge clk);
        in_valid = 1'b0;
        repeat (6) @(posedge clk);

        if (error_count == 0)
            $display("DOT9_PIPELINED_DSP_TEST_PASS");
        else
            $display("DOT9_PIPELINED_DSP_TEST_FAIL errors=%0d", error_count);

        #10;
        $finish;
    end

endmodule
