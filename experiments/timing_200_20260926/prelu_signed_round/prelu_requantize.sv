`timescale 1ns / 1ps

// Isolated PReLU signed-round candidate: retain V2 scalar latency (8 stages).

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

    reg signed [47:0] prelu_product_s1;
    reg signed [31:0] accumulator_s1;
    reg signed [31:0] multiplier_s1;
    reg valid_s1;

    // Reuse the former absolute-value stage as a second product register.
    // No KEEP/DONT_TOUCH on either PReLU product stage: let synthesis infer
    // internal DSP pipeline registers, then verify MREG/PREG in the netlist.
    reg signed [47:0] prelu_product_full_s2;
    reg signed [31:0] accumulator_s2;
    reg signed [31:0] multiplier_s2;
    reg valid_s2;

    // Floor quotient plus asymmetric increment implements nearest/ties-away
    // for both signs without an absolute value or subsequent sign restore.
    wire signed [32:0] prelu_trunc_s2 = $signed(prelu_product_full_s2[47:15]);
    wire prelu_round_up_s2 = prelu_product_full_s2[14] &
        (~prelu_product_full_s2[47] | (|prelu_product_full_s2[13:0]));
    wire signed [33:0] prelu_rounded_s2 =
        $signed({prelu_trunc_s2[32],prelu_trunc_s2}) +
        $signed({33'd0,prelu_round_up_s2});
    reg signed [33:0] prelu_rounded_s3;
    reg signed [31:0] accumulator_s3;
    reg signed [31:0] multiplier_s3;
    reg valid_s3;

    reg signed [31:0] prelu_value_s4;
    reg signed [31:0] multiplier_s4;
    reg valid_s4;

    reg signed [63:0] requant_product_s5;
    reg valid_s5;

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
            prelu_product_s1 <= 0;
            accumulator_s1 <= 0;
            multiplier_s1 <= 0;
            valid_s1 <= 1'b0;
        end else begin
            if (in_valid) begin
                prelu_product_s1 <= accumulator_int32 * prelu_q15;
                accumulator_s1 <= accumulator_int32;
                multiplier_s1 <= multiplier_q31;
            end
            valid_s1 <= in_valid;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            prelu_product_full_s2 <= 0;
            accumulator_s2 <= 0;
            multiplier_s2 <= 0;
            valid_s2 <= 1'b0;
        end else begin
            if (valid_s1) begin
                prelu_product_full_s2 <= prelu_product_s1;
                accumulator_s2 <= accumulator_s1;
                multiplier_s2 <= multiplier_s1;
            end
            valid_s2 <= valid_s1;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            prelu_rounded_s3 <= 0;
            accumulator_s3 <= 0;
            multiplier_s3 <= 0;
            valid_s3 <= 1'b0;
        end else begin
            if (valid_s2) begin
                prelu_rounded_s3 <= prelu_rounded_s2;
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
                    if (prelu_rounded_s3 > 34'sd2147483647)
                        prelu_value_s4 <= 32'sh7fffffff;
                    else if (prelu_rounded_s3 < -34'sd2147483648)
                        prelu_value_s4 <= 32'sh80000000;
                    else
                        prelu_value_s4 <= prelu_rounded_s3[31:0];
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
            requant_product_s5 <= 0;
            valid_s5 <= 1'b0;
        end else begin
            if (valid_s4)
                requant_product_s5 <= prelu_value_s4 * multiplier_s4;
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
