`timescale 1ns / 1ps

module dot25_pipeline_tb;

    reg clk;
    reg rst;
    reg in_valid;
    reg signed [199:0] x_flat;
    reg signed [199:0] k_flat;
    wire signed [20:0] dot25;
    wire dot25_valid;

    integer error_count;
    integer result_count;
    integer timeout_count;
    integer i;

    dot25_pipeline #(
        .ACT_W(8),
        .WGT_W(8)
    ) dut (
        .clk(clk), .rst(rst), .in_valid(in_valid),
        .x_flat(x_flat), .k_flat(k_flat),
        .dot25(dot25), .dot25_valid(dot25_valid)
    );

    initial begin
        clk=1'b0;
        forever #5 clk=~clk;
    end

    task set_all;
        input signed [7:0] x_value;
        input signed [7:0] k_value;
        begin
            for (i=0; i<25; i=i+1) begin
                x_flat[(i*8) +: 8]=x_value;
                k_flat[(i*8) +: 8]=k_value;
            end
        end
    endtask

    task send_sample;
        input signed [7:0] x_value;
        input signed [7:0] k_value;
        begin
            @(negedge clk);
            set_all(x_value, k_value);
            in_valid=1'b1;
        end
    endtask

    always @(posedge clk) begin
        #1;
        if (dot25_valid) begin
            case (result_count)
                0: if (dot25 !== 21'sd25) begin
                    $display("DOT25_RESULT0_MISMATCH got=%0d", dot25);
                    error_count=error_count+1;
                end
                1: if (dot25 !== -21'sd150) begin
                    $display("DOT25_RESULT1_MISMATCH got=%0d", dot25);
                    error_count=error_count+1;
                end
                2: if (dot25 !== 21'sd409600) begin
                    $display("DOT25_RESULT2_MISMATCH got=%0d", dot25);
                    error_count=error_count+1;
                end
                default: begin
                    $display("DOT25_UNEXPECTED_RESULT got=%0d", dot25);
                    error_count=error_count+1;
                end
            endcase
            result_count=result_count+1;
        end
    end

    initial begin
        rst=1'b1;
        in_valid=1'b0;
        x_flat=0;
        k_flat=0;
        error_count=0;
        result_count=0;
        timeout_count=0;

        repeat (3) @(posedge clk);
        @(negedge clk);
        rst=1'b0;

        send_sample(1,1);
        send_sample(-2,3);
        @(negedge clk);
        in_valid=1'b0;
        send_sample(-128,-128);
        @(negedge clk);
        in_valid=1'b0;

        while ((result_count < 3) && (timeout_count < 30)) begin
            @(posedge clk);
            timeout_count=timeout_count+1;
        end

        if (result_count != 3) begin
            $display("DOT25_RESULT_COUNT_MISMATCH got=%0d expected=3", result_count);
            error_count=error_count+1;
        end

        if (error_count == 0)
            $display("ACX750_DOT25_PIPELINE_TEST_PASS results=%0d", result_count);
        else
            $display("ACX750_DOT25_PIPELINE_TEST_FAIL errors=%0d", error_count);

        #10;
        $finish;
    end

endmodule
