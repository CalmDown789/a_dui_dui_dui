`timescale 1ns / 1ps

module conv5x5_u8s8_backend_tb;

    reg clk;
    reg rst;
    reg in_valid;
    reg [199:0] x_flat;
    reg signed [199:0] k_flat;
    reg signed [31:0] bias;
    wire signed [31:0] result;
    wire result_valid;

    integer i;
    integer result_count;
    integer error_count;
    integer timeout_count;

    conv5x5_u8s8_backend #(
        .ACT_W(8), .WGT_W(8), .ACC_W(32), .CHANNELS(1)
    ) dut (
        .clk(clk), .rst(rst), .in_valid(in_valid),
        .x_flat(x_flat), .k_flat(k_flat), .bias(bias),
        .result(result), .result_valid(result_valid)
    );

    initial begin
        clk=1'b0;
        forever #5 clk=~clk;
    end

    task send_all;
        input [7:0] x_value;
        input signed [7:0] k_value;
        input signed [31:0] bias_value;
        begin
            @(negedge clk);
            for (i=0; i<25; i=i+1) begin
                x_flat[(i*8) +: 8]=x_value;
                k_flat[(i*8) +: 8]=k_value;
            end
            bias=bias_value;
            in_valid=1'b1;
        end
    endtask

    always @(posedge clk) begin
        #1;
        if (result_valid) begin
            case (result_count)
                0: if (result !== -32'sd816000) begin
                    $display("U8S8_RESULT0_MISMATCH got=%0d", result);
                    error_count=error_count+1;
                end
                1: if (result !== 32'sd809630) begin
                    $display("U8S8_RESULT1_MISMATCH got=%0d", result);
                    error_count=error_count+1;
                end
                2: if (result !== -32'sd3193) begin
                    $display("U8S8_RESULT2_MISMATCH got=%0d", result);
                    error_count=error_count+1;
                end
                default: begin
                    $display("U8S8_UNEXPECTED_RESULT got=%0d", result);
                    error_count=error_count+1;
                end
            endcase
            result_count=result_count+1;
        end
    end

    initial begin
        rst=1'b1; in_valid=1'b0; x_flat=0; k_flat=0; bias=0;
        result_count=0; error_count=0; timeout_count=0;
        repeat (3) @(posedge clk);
        @(negedge clk); rst=1'b0;

        // These vectors distinguish unsigned input from signed INT8 input.
        send_all(8'd255, -8'sd128, 32'sd0);
        send_all(8'd255,  8'sd127, 32'sd5);
        @(negedge clk); in_valid=1'b0;
        send_all(8'd128, -8'sd1, 32'sd7);
        @(negedge clk); in_valid=1'b0;

        while ((result_count < 3) && (timeout_count < 40)) begin
            @(posedge clk);
            timeout_count=timeout_count+1;
        end

        if (result_count != 3) begin
            $display("U8S8_RESULT_COUNT_MISMATCH got=%0d expected=3", result_count);
            error_count=error_count+1;
        end
        if (error_count == 0)
            $display("ACX750_CONV5X5_U8S8_BACKEND_TEST_PASS results=%0d", result_count);
        else
            $display("ACX750_CONV5X5_U8S8_BACKEND_TEST_FAIL errors=%0d", error_count);
        #10; $finish;
    end

endmodule
