`timescale 1ns / 1ps
`include "postprocess_vector_counts.vh"

module prelu_requantize_member_a_tb;

    reg clk;
    reg rst;
    reg signed_valid;
    reg signed [31:0] signed_accum;
    reg signed [15:0] signed_alpha;
    reg signed [31:0] signed_multiplier;
    wire [15:0] signed_out;
    wire signed_out_valid;

    reg unsigned_valid;
    reg signed [31:0] unsigned_accum;
    reg signed [31:0] unsigned_multiplier;
    wire [7:0] unsigned_out;
    wire unsigned_out_valid;

    reg [95:0] signed_vectors [0:`POST_I16_COUNT-1];
    reg [71:0] unsigned_vectors [0:`POST_U8_COUNT-1];
    integer signed_sent;
    integer signed_seen;
    integer unsigned_sent;
    integer unsigned_seen;
    integer errors;
    integer timeout_count;

    prelu_requantize #(
        .OUT_W(16), .OUT_SIGNED(1), .APPLY_PRELU(1)
    ) signed_dut (
        .clk(clk), .rst(rst), .in_valid(signed_valid),
        .accumulator_int32(signed_accum), .prelu_q15(signed_alpha),
        .multiplier_q31(signed_multiplier),
        .out_data(signed_out), .out_valid(signed_out_valid)
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

    always @(posedge clk) begin
        #1;
        if (signed_out_valid) begin
            if (signed_out !== signed_vectors[signed_seen][15:0]) begin
                $display("MEMBER_A_I16_MISMATCH index=%0d got=%h expected=%h",
                         signed_seen, signed_out, signed_vectors[signed_seen][15:0]);
                errors=errors+1;
            end
            signed_seen=signed_seen+1;
        end
        if (unsigned_out_valid) begin
            if (unsigned_out !== unsigned_vectors[unsigned_seen][7:0]) begin
                $display("MEMBER_A_U8_MISMATCH index=%0d got=%h expected=%h",
                         unsigned_seen, unsigned_out, unsigned_vectors[unsigned_seen][7:0]);
                errors=errors+1;
            end
            unsigned_seen=unsigned_seen+1;
        end
    end

    initial begin
        $readmemh("postprocess_i16.mem", signed_vectors);
        $readmemh("postprocess_u8.mem", unsigned_vectors);
        rst=1'b1;
        signed_valid=1'b0; signed_accum=0; signed_alpha=0; signed_multiplier=0;
        unsigned_valid=1'b0; unsigned_accum=0; unsigned_multiplier=0;
        signed_sent=0; signed_seen=0; unsigned_sent=0; unsigned_seen=0;
        errors=0; timeout_count=0;
        repeat (3) @(posedge clk);
        @(negedge clk); rst=1'b0;

        while (signed_sent < `POST_I16_COUNT) begin
            @(negedge clk);
            signed_accum=signed_vectors[signed_sent][95:64];
            signed_alpha=signed_vectors[signed_sent][63:48];
            signed_multiplier=signed_vectors[signed_sent][47:16];
            signed_valid=1'b1;
            signed_sent=signed_sent+1;
        end
        @(negedge clk); signed_valid=1'b0;

        while (unsigned_sent < `POST_U8_COUNT) begin
            @(negedge clk);
            unsigned_accum=unsigned_vectors[unsigned_sent][71:40];
            unsigned_multiplier=unsigned_vectors[unsigned_sent][39:8];
            unsigned_valid=1'b1;
            unsigned_sent=unsigned_sent+1;
        end
        @(negedge clk); unsigned_valid=1'b0;

        while (((signed_seen < `POST_I16_COUNT) || (unsigned_seen < `POST_U8_COUNT)) &&
               (timeout_count < 40)) begin
            @(posedge clk);
            timeout_count=timeout_count+1;
        end
        if ((signed_seen != `POST_I16_COUNT) || (unsigned_seen != `POST_U8_COUNT)) begin
            $display("MEMBER_A_POSTPROCESS_COUNT_MISMATCH i16=%0d/%0d u8=%0d/%0d",
                     signed_seen, `POST_I16_COUNT, unsigned_seen, `POST_U8_COUNT);
            errors=errors+1;
        end
        if (errors == 0)
            $display("ACX750_MEMBER_A_POSTPROCESS_BIT_EXACT_PASS i16=%0d u8=%0d",
                     signed_seen, unsigned_seen);
        else
            $display("ACX750_MEMBER_A_POSTPROCESS_BIT_EXACT_FAIL errors=%0d", errors);
        #10; $finish;
    end

endmodule
