`timescale 1ns / 1ps

// Isolated nine-cycle scalar candidate. PReLU keeps the V5 signed48 partial
// product implementation. Q31 uses four registered 16-bit partial products,
// two fabric carry-save reductions and one final carry-propagate adder.
// Verify independent DSP mappings and the complete-product FF boundary.

// Frozen integer postprocess contract:
// optional per-channel Q1.15 PReLU, INT32 saturation, signed Q31 requant,
// nearest rounding with ties away from zero, then output saturation.
module prelu_requantize #(
    parameter integer OUT_W = 16,
    parameter integer OUT_SIGNED = 1,
    parameter integer APPLY_PRELU = 1
)(
    input  wire                         clk,
    input  wire                         rst,
    input  wire                         in_valid,
    input  wire signed [31:0]           accumulator_int32,
    input  wire signed [15:0]           prelu_q15,
    input  wire signed [31:0]           multiplier_q31,
    output reg  [OUT_W-1:0]             out_data,
    output reg                          out_valid
);

    wire signed [16:0] prelu_low_operand =
        $signed({1'b0, accumulator_int32[15:0]});
    wire signed [15:0] prelu_high_operand =
        $signed(accumulator_int32[31:16]);
    (* use_dsp = "yes" *) reg signed [32:0] prelu_product_lo_s1;
    (* use_dsp = "yes" *) reg signed [31:0] prelu_product_hi_s1;
    reg signed [31:0] accumulator_s1;
    reg signed [31:0] multiplier_s1;
    reg valid_s1;

    wire signed [47:0] prelu_lo_extended_s1 =
        {{15{prelu_product_lo_s1[32]}}, prelu_product_lo_s1};
    wire signed [47:0] prelu_hi_extended_s1 =
        {{16{prelu_product_hi_s1[31]}}, prelu_product_hi_s1};
    wire signed [47:0] prelu_hi_shifted_s1 = prelu_hi_extended_s1 <<< 16;
    (* use_dsp = "no" *) wire signed [47:0] prelu_reconstructed_s1 =
        prelu_hi_shifted_s1 + prelu_lo_extended_s1;
    // Preserve this boundary after the fabric sum; verify the actual netlist.
    (* use_dsp = "no", KEEP = "yes", DONT_TOUCH = "yes" *)
    reg signed [47:0] prelu_product_s1b;
    reg signed [31:0] accumulator_s1b;
    reg signed [31:0] multiplier_s1b;
    reg valid_s1b;

    wire signed [48:0] prelu_product_extended_s1 =
        {prelu_product_s1b[47],prelu_product_s1b};
    wire prelu_product_negative_s1 = prelu_product_extended_s1 < 0;
    wire [48:0] prelu_product_magnitude_s1 = prelu_product_negative_s1 ?
        -prelu_product_extended_s1 : prelu_product_extended_s1;

    reg [48:0] prelu_magnitude_s2;
    reg prelu_negative_s2;
    reg signed [31:0] accumulator_s2;
    reg signed [31:0] multiplier_s2;
    reg valid_s2;

    wire [49:0] prelu_round_sum_s2 =
        {1'b0,prelu_magnitude_s2} + 50'd16384;
    reg [32:0] prelu_rounded_magnitude_s3;
    reg prelu_negative_s3;
    reg signed [31:0] accumulator_s3;
    reg signed [31:0] multiplier_s3;
    reg valid_s3;

    reg signed [31:0] prelu_value_s4;
    reg signed [31:0] multiplier_s4;
    reg valid_s4;

    wire signed [16:0] requant_a_lo = $signed({1'b0, prelu_value_s4[15:0]});
    wire signed [15:0] requant_a_hi = $signed(prelu_value_s4[31:16]);
    wire signed [16:0] requant_b_lo = $signed({1'b0, multiplier_s4[15:0]});
    wire signed [15:0] requant_b_hi = $signed(multiplier_s4[31:16]);
    (* use_dsp = "yes" *) reg signed [33:0] requant_ll_s5;
    (* use_dsp = "yes" *) reg signed [32:0] requant_lh_s5;
    (* use_dsp = "yes" *) reg signed [32:0] requant_hl_s5;
    (* use_dsp = "yes" *) reg signed [31:0] requant_hh_s5;
    reg valid_s5;

    // Expand each signed partial product before shifting. All following
    // vectors are exactly 64 bits, so discarded carries implement mod 2^64.
    wire [63:0] requant_term_ll = {{30{requant_ll_s5[33]}}, requant_ll_s5};
    wire [63:0] requant_lh_extended = {{31{requant_lh_s5[32]}}, requant_lh_s5};
    wire [63:0] requant_hl_extended = {{31{requant_hl_s5[32]}}, requant_hl_s5};
    wire [63:0] requant_hh_extended = {{32{requant_hh_s5[31]}}, requant_hh_s5};
    wire [63:0] requant_term_lh = requant_lh_extended << 16;
    wire [63:0] requant_term_hl = requant_hl_extended << 16;
    wire [63:0] requant_term_hh = requant_hh_extended << 32;

    // A+B+C = (A^B^C) + (((A&B)|(A&C)|(B&C))<<1), modulo 2^64.
    // Two local bitwise levels reduce four operands to two. Only the final
    // addition propagates carry across bit positions; none may become a DSP.
    (* use_dsp = "no" *) wire [63:0] requant_csa_sum1 =
        requant_term_ll ^ requant_term_lh ^ requant_term_hl;
    (* use_dsp = "no" *) wire [63:0] requant_csa_carry1 =
        ((requant_term_ll & requant_term_lh) |
         (requant_term_ll & requant_term_hl) |
         (requant_term_lh & requant_term_hl)) << 1;
    (* use_dsp = "no" *) wire [63:0] requant_csa_sum2 =
        requant_csa_sum1 ^ requant_csa_carry1 ^ requant_term_hh;
    (* use_dsp = "no" *) wire [63:0] requant_csa_carry2 =
        ((requant_csa_sum1 & requant_csa_carry1) |
         (requant_csa_sum1 & requant_term_hh) |
         (requant_csa_carry1 & requant_term_hh)) << 1;
    (* use_dsp = "no" *) wire signed [63:0] requant_product_s5 =
        $signed(requant_csa_sum2) + $signed(requant_csa_carry2);

    // Preserve a complete product register between DSP partial-product
    // reconstruction and Q31 rounding. Confirm FF boundaries in the netlist:
    // the attribute is a request, not timing evidence.
    (* DONT_TOUCH = "yes", KEEP = "yes" *)
    reg signed [63:0] requant_product_full_s6;
    reg valid_full_s6;
    wire signed [32:0] requant_trunc_s6 = $signed(requant_product_full_s6[63:31]);
    wire requant_round_up_s6 =
        requant_product_full_s6[30] & (~requant_product_full_s6[63] | (|requant_product_full_s6[29:0]));
    wire signed [33:0] requant_rounded_s6 =
        $signed({requant_trunc_s6[32], requant_trunc_s6}) + $signed({33'd0, requant_round_up_s6});
    reg signed [33:0] rounded_q31_s7;
    reg valid_s7;

    function automatic [OUT_W-1:0] saturate_q31_output;
        input signed [33:0] rounded_value;
        reg signed [34:0] rounded;
        reg signed [34:0] maximum;
        reg signed [34:0] minimum;
        begin
            rounded = {rounded_value[33], rounded_value};

            if (OUT_SIGNED != 0) begin
                maximum = (35'sd1 <<< (OUT_W-1)) - 1;
                minimum = -(35'sd1 <<< (OUT_W-1));
            end else begin
                maximum = (35'sd1 <<< OUT_W) - 1;
                minimum = 0;
            end

            if (rounded > maximum)
                saturate_q31_output = maximum[OUT_W-1:0];
            else if (rounded < minimum)
                saturate_q31_output = minimum[OUT_W-1:0];
            else
                saturate_q31_output = rounded[OUT_W-1:0];
        end
    endfunction

    initial begin
        if (OUT_W < 1 || OUT_W > 31)
            $error("OUT_W must be in the range 1..31");
    end

    always @(posedge clk) begin
        if (rst) begin
            prelu_product_lo_s1 <= 0;
            prelu_product_hi_s1 <= 0;
            accumulator_s1 <= 0;
            multiplier_s1 <= 0;
            valid_s1 <= 1'b0;
        end else begin
            if (in_valid) begin
                prelu_product_lo_s1 <= prelu_low_operand * prelu_q15;
                prelu_product_hi_s1 <= prelu_high_operand * prelu_q15;
                accumulator_s1 <= accumulator_int32;
                multiplier_s1 <= multiplier_q31;
            end
            valid_s1 <= in_valid;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            prelu_product_s1b <= 0;
            accumulator_s1b <= 0;
            multiplier_s1b <= 0;
            valid_s1b <= 1'b0;
        end else begin
            if (valid_s1) begin
                prelu_product_s1b <= prelu_reconstructed_s1;
                accumulator_s1b <= accumulator_s1;
                multiplier_s1b <= multiplier_s1;
            end
            valid_s1b <= valid_s1;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            prelu_magnitude_s2 <= 0;
            prelu_negative_s2 <= 0;
            accumulator_s2 <= 0;
            multiplier_s2 <= 0;
            valid_s2 <= 1'b0;
        end else begin
            if (valid_s1b) begin
                prelu_magnitude_s2 <= prelu_product_magnitude_s1;
                prelu_negative_s2 <= prelu_product_negative_s1;
                accumulator_s2 <= accumulator_s1b;
                multiplier_s2 <= multiplier_s1b;
            end
            valid_s2 <= valid_s1b;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            prelu_rounded_magnitude_s3 <= 0;
            prelu_negative_s3 <= 0;
            accumulator_s3 <= 0;
            multiplier_s3 <= 0;
            valid_s3 <= 1'b0;
        end else begin
            if (valid_s2) begin
                prelu_rounded_magnitude_s3 <= prelu_round_sum_s2[47:15];
                prelu_negative_s3 <= prelu_negative_s2;
                accumulator_s3 <= accumulator_s2;
                multiplier_s3 <= multiplier_s2;
            end
            valid_s3 <= valid_s2;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            prelu_value_s4 <= 0;
            multiplier_s4 <= 0;
            valid_s4 <= 1'b0;
        end else begin
            if (valid_s3) begin
                if ((APPLY_PRELU != 0) && (accumulator_s3 < 0)) begin
                    if (prelu_negative_s3) begin
                        if (prelu_rounded_magnitude_s3 > 33'd2147483648)
                            prelu_value_s4 <= 32'sh80000000;
                        else
                            prelu_value_s4 <=
                                -$signed(prelu_rounded_magnitude_s3[31:0]);
                    end else begin
                        if (prelu_rounded_magnitude_s3 > 33'd2147483647)
                            prelu_value_s4 <= 32'sh7fffffff;
                        else
                            prelu_value_s4 <=
                                $signed(prelu_rounded_magnitude_s3[31:0]);
                    end
                end else begin
                    prelu_value_s4 <= accumulator_s3;
                end
                multiplier_s4 <= multiplier_s3;
            end
            valid_s4 <= valid_s3;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            requant_ll_s5 <= 0;
            requant_lh_s5 <= 0;
            requant_hl_s5 <= 0;
            requant_hh_s5 <= 0;
            valid_s5 <= 1'b0;
        end else begin
            if (valid_s4) begin
                requant_ll_s5 <= requant_a_lo * requant_b_lo;
                requant_lh_s5 <= requant_a_lo * requant_b_hi;
                requant_hl_s5 <= requant_a_hi * requant_b_lo;
                requant_hh_s5 <= requant_a_hi * requant_b_hi;
            end
            valid_s5 <= valid_s4;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            requant_product_full_s6 <= 0;
            valid_full_s6 <= 1'b0;
        end else begin
            if (valid_s5)
                requant_product_full_s6 <= requant_product_s5;
            valid_full_s6 <= valid_s5;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            rounded_q31_s7 <= 0;
            valid_s7 <= 1'b0;
        end else begin
            if (valid_full_s6)
                rounded_q31_s7 <= requant_rounded_s6;
            valid_s7 <= valid_full_s6;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            out_data <= 0;
            out_valid <= 1'b0;
        end else begin
            if (valid_s7)
                out_data <= saturate_q31_output(rounded_q31_s7);
            out_valid <= valid_s7;
        end
    end

endmodule
