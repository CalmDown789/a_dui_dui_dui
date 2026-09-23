`timescale 1ns / 1ps

module prelu_requantize_tb;

    reg clk;
    reg rst;

    reg signed_valid;
    reg signed [31:0] signed_accum;
    reg signed [15:0] signed_alpha;
    reg signed [31:0] signed_multiplier;
    wire [15:0] signed_out_bits;
    wire signed [15:0] signed_out = signed_out_bits;
    wire signed_out_valid;

    reg unsigned_valid;
    reg signed [31:0] unsigned_accum;
    reg signed [31:0] unsigned_multiplier;
    wire [7:0] unsigned_out;
    wire unsigned_out_valid;

    integer signed_count;
    integer unsigned_count;
    integer errors;
    integer timeout_count;

    prelu_requantize #(
        .OUT_W(16), .OUT_SIGNED(1), .APPLY_PRELU(1)
    ) signed_dut (
        .clk(clk), .rst(rst), .in_valid(signed_valid),
        .accumulator_int32(signed_accum), .prelu_q15(signed_alpha),
        .multiplier_q31(signed_multiplier),
        .out_data(signed_out_bits), .out_valid(signed_out_valid)
    );

    prelu_requantize #(
        .OUT_W(8), .OUT_SIGNED(0), .APPLY_PRELU(0)
    ) unsigned_dut (
        .clk(clk), .rst(rst), .in_valid(unsigned_valid),
        .accumulator_int32(unsigned_accum), .prelu_q15(16'sd0),
        .multiplier_q31(unsigned_multiplier),
        .out_data(unsigned_out), .out_valid(unsigned_out_valid)
    );

    initial begin
        clk=1'b0;
        forever #5 clk=~clk;
    end

    task send_signed;
        input signed [31:0] accum;
        input signed [15:0] alpha;
        input signed [31:0] multiplier;
        begin
            @(negedge clk);
            signed_accum=accum;
            signed_alpha=alpha;
            signed_multiplier=multiplier;
            signed_valid=1'b1;
        end
    endtask

    task send_unsigned;
        input signed [31:0] accum;
        input signed [31:0] multiplier;
        begin
            @(negedge clk);
            unsigned_accum=accum;
            unsigned_multiplier=multiplier;
            unsigned_valid=1'b1;
        end
    endtask

    always @(posedge clk) begin
        #1;
        if (signed_out_valid) begin
            case (signed_count)
                0: if (signed_out !== -16'sd4) errors=errors+1;
                1: if (signed_out !==  16'sd4) errors=errors+1;
                2: if (signed_out !==  16'sd1) errors=errors+1;
                3: if (signed_out !==  16'sd32767) errors=errors+1;
                4: if (signed_out !== -16'sd1) errors=errors+1;
                default: errors=errors+1;
            endcase
            if (errors != 0)
                $display("SIGNED_POSTPROCESS_MISMATCH index=%0d got=%0d", signed_count, signed_out);
            signed_count=signed_count+1;
        end
        if (unsigned_out_valid) begin
            case (unsigned_count)
                0: if (unsigned_out !== 8'd0) errors=errors+1;
                1: if (unsigned_out !== 8'd1) errors=errors+1;
                2: if (unsigned_out !== 8'd255) errors=errors+1;
                default: errors=errors+1;
            endcase
            if (errors != 0)
                $display("UNSIGNED_POSTPROCESS_MISMATCH index=%0d got=%0d", unsigned_count, unsigned_out);
            unsigned_count=unsigned_count+1;
        end
    end

    initial begin
        rst=1'b1;
        signed_valid=1'b0; signed_accum=0; signed_alpha=0; signed_multiplier=0;
        unsigned_valid=1'b0; unsigned_accum=0; unsigned_multiplier=0;
        signed_count=0; unsigned_count=0; errors=0; timeout_count=0;
        repeat (3) @(posedge clk);
        @(negedge clk); rst=1'b0;

        send_signed(-32'sd7,  16'sd16384, 32'sd2147483647);
        send_signed(-32'sd7, -16'sd16384, 32'sd2147483647);
        send_signed( 32'sd1,  16'sd0,     32'sd1073741824);
        send_signed( 32'sd100000, 16'sd0, 32'sd2147483647);
        send_signed(-32'sd1, 16'sd32767,  32'sd1073741824);
        @(negedge clk); signed_valid=1'b0;

        send_unsigned(-32'sd1, 32'sd2147483647);
        send_unsigned( 32'sd1, 32'sd1073741824);
        send_unsigned( 32'sd300, 32'sd2147483647);
        @(negedge clk); unsigned_valid=1'b0;

        while (((signed_count < 5) || (unsigned_count < 3)) && (timeout_count < 40)) begin
            @(posedge clk);
            timeout_count=timeout_count+1;
        end
        if ((signed_count != 5) || (unsigned_count != 3)) begin
            $display("POSTPROCESS_COUNT_MISMATCH signed=%0d unsigned=%0d", signed_count, unsigned_count);
            errors=errors+1;
        end
        if (errors == 0)
            $display("ACX750_PRELU_REQUANTIZE_TEST_PASS signed=%0d unsigned=%0d", signed_count, unsigned_count);
        else
            $display("ACX750_PRELU_REQUANTIZE_TEST_FAIL errors=%0d", errors);
        #10; $finish;
    end

endmodule
