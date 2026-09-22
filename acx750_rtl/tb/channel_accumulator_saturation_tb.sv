`timescale 1ns / 1ps

module channel_accumulator_saturation_tb;

    reg clk;
    reg rst;
    reg dot_valid;
    reg signed [7:0] dot_value;
    reg signed [7:0] bias;
    wire signed [7:0] result;
    wire result_valid;
    integer result_count;
    integer errors;
    integer timeout_count;

    channel_accumulator #(
        .DOT_W(8), .ACC_W(8), .CHANNELS(2)
    ) dut (
        .clk(clk), .rst(rst), .dot_valid(dot_valid),
        .dot_value(dot_value), .bias(bias),
        .result(result), .result_valid(result_valid)
    );

    initial begin
        clk=1'b0;
        forever #5 clk=~clk;
    end

    task send_dot;
        input signed [7:0] value;
        input signed [7:0] bias_value;
        begin
            @(negedge clk);
            dot_value=value;
            bias=bias_value;
            dot_valid=1'b1;
        end
    endtask

    always @(posedge clk) begin
        #1;
        if (result_valid) begin
            case (result_count)
                0: if (result !== 8'sd127) begin
                    $display("SAT_POS_MISMATCH got=%0d", result);
                    errors=errors+1;
                end
                1: if (result !== -8'sd128) begin
                    $display("SAT_NEG_MISMATCH got=%0d", result);
                    errors=errors+1;
                end
                // 120 + 50 - 50 = 120. Saturating after the first dot would
                // incorrectly produce 77, so this checks final-only saturation.
                2: if (result !== 8'sd120) begin
                    $display("SAT_ORDER_MISMATCH got=%0d", result);
                    errors=errors+1;
                end
                default: begin
                    $display("SAT_UNEXPECTED_RESULT got=%0d", result);
                    errors=errors+1;
                end
            endcase
            result_count=result_count+1;
        end
    end

    initial begin
        rst=1'b1; dot_valid=1'b0; dot_value=0; bias=0;
        result_count=0; errors=0; timeout_count=0;
        repeat (3) @(posedge clk);
        @(negedge clk); rst=1'b0;

        send_dot(8'sd50, 8'sd100);
        send_dot(8'sd50, 8'sd0);
        send_dot(-8'sd50, -8'sd100);
        send_dot(-8'sd50, 8'sd0);
        send_dot(8'sd50, 8'sd120);
        send_dot(-8'sd50, 8'sd0);
        @(negedge clk); dot_valid=1'b0;

        while ((result_count < 3) && (timeout_count < 20)) begin
            @(posedge clk);
            timeout_count=timeout_count+1;
        end
        if (result_count != 3) begin
            $display("SAT_RESULT_COUNT_MISMATCH got=%0d", result_count);
            errors=errors+1;
        end
        if (errors == 0)
            $display("ACX750_CHANNEL_ACCUMULATOR_SATURATION_TEST_PASS");
        else
            $display("ACX750_CHANNEL_ACCUMULATOR_SATURATION_TEST_FAIL errors=%0d", errors);
        #10; $finish;
    end

endmodule
