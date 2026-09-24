`timescale 1ns / 1ps

module conv3x3_backend_tb;

    reg clk;
    reg rst;
    reg in_valid;

    reg signed [7:0] x00, x01, x02, x10, x11, x12, x20, x21, x22;
    reg signed [7:0] k00, k01, k02, k10, k11, k12, k20, k21, k22;
    reg signed [31:0] bias;

    wire signed [31:0] result;
    wire result_valid;

    integer error_count;
    integer result_count;
    integer timeout_count;

    conv3x3_backend #(
        .ACT_W(8),
        .WGT_W(8),
        .ACC_W(32),
        .CHANNELS(2)
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

    task set_x_all;
        input signed [7:0] value;
        begin
            x00=value; x01=value; x02=value;
            x10=value; x11=value; x12=value;
            x20=value; x21=value; x22=value;
        end
    endtask

    task set_k_all;
        input signed [7:0] value;
        begin
            k00=value; k01=value; k02=value;
            k10=value; k11=value; k12=value;
            k20=value; k21=value; k22=value;
        end
    endtask

    task send_contribution;
        input signed [7:0] x_value;
        input signed [7:0] k_value;
        input signed [31:0] bias_value;
        begin
            @(negedge clk);
            set_x_all(x_value);
            set_k_all(k_value);
            bias = bias_value;
            in_valid = 1'b1;
        end
    endtask

    always @(posedge clk) begin
        #1;
        if (result_valid) begin
            if (result_count == 0) begin
                // 5 + (9 * 1 * 1) + (9 * 1 * 1) = 23
                if (result !== 32'sd23) begin
                    $display("RESULT0_MISMATCH got=%0d expected=23", result);
                    error_count = error_count + 1;
                end
            end else if (result_count == 1) begin
                // -4 + (9 * 1 * -1) + (9 * 2 * 1) = 5
                if (result !== 32'sd5) begin
                    $display("RESULT1_MISMATCH got=%0d expected=5", result);
                    error_count = error_count + 1;
                end
            end else begin
                $display("UNEXPECTED_RESULT got=%0d", result);
                error_count = error_count + 1;
            end
            result_count = result_count + 1;
        end
    end

    initial begin
        rst = 1'b1;
        in_valid = 1'b0;
        bias = 0;
        error_count = 0;
        result_count = 0;
        timeout_count = 0;
        set_x_all(0);
        set_k_all(0);

        repeat (3) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;

        send_contribution(1,  1,  5);
        send_contribution(1,  1,  5);
        send_contribution(1, -1, -4);
        send_contribution(2,  1, -4);

        @(negedge clk);
        in_valid = 1'b0;

        while ((result_count < 2) && (timeout_count < 30)) begin
            @(posedge clk);
            timeout_count = timeout_count + 1;
        end

        if (result_count != 2) begin
            $display("RESULT_COUNT_MISMATCH got=%0d expected=2", result_count);
            error_count = error_count + 1;
        end

        if (error_count == 0)
            $display("ACX750_CONV3X3_BACKEND_TEST_PASS");
        else
            $display("ACX750_CONV3X3_BACKEND_TEST_FAIL errors=%0d", error_count);

        #10;
        $finish;
    end

endmodule
