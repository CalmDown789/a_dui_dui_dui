`timescale 1ns / 1ps

// Team member B: bit-exact PReLU and requantization pipeline.

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

    reg signed [31:0] prelu_value_s2;
    reg signed [31:0] multiplier_s2;
    reg valid_s2;

    reg signed [63:0] requant_product_s3;
    reg valid_s3;

    function automatic signed [31:0] round_q15_saturate_int32;
        input signed [47:0] value;
        reg signed [48:0] extended;
        reg signed [48:0] magnitude;
        reg signed [48:0] rounded;
        begin
            extended = {value[47], value};
            if (extended < 0) begin
                magnitude = -extended;
                rounded = -((magnitude + 49'sd16384) >>> 15);
            end else begin
                rounded = (extended + 49'sd16384) >>> 15;
            end
            if (rounded > 49'sd2147483647)
                round_q15_saturate_int32 = 32'sh7fffffff;
            else if (rounded < -49'sd2147483648)
                round_q15_saturate_int32 = 32'sh80000000;
            else
                round_q15_saturate_int32 = rounded[31:0];
        end
    endfunction

    function automatic [OUT_W-1:0] round_q31_saturate_output;
        input signed [63:0] value;
        reg signed [64:0] extended;
        reg signed [64:0] magnitude;
        reg signed [64:0] rounded;
        reg signed [64:0] maximum;
        reg signed [64:0] minimum;
        begin
            extended = {value[63], value};
            if (extended < 0) begin
                magnitude = -extended;
                rounded = -((magnitude + 65'sd1073741824) >>> 31);
            end else begin
                rounded = (extended + 65'sd1073741824) >>> 31;
            end

            if (OUT_SIGNED != 0) begin
                maximum = (65'sd1 <<< (OUT_W-1)) - 1;
                minimum = -(65'sd1 <<< (OUT_W-1));
            end else begin
                maximum = (65'sd1 <<< OUT_W) - 1;
                minimum = 0;
            end

            if (rounded > maximum)
                round_q31_saturate_output = maximum[OUT_W-1:0];
            else if (rounded < minimum)
                round_q31_saturate_output = minimum[OUT_W-1:0];
            else
                round_q31_saturate_output = rounded[OUT_W-1:0];
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
            prelu_value_s2 <= 0;
            multiplier_s2 <= 0;
            valid_s2 <= 1'b0;
        end else begin
            if (valid_s1) begin
                if ((APPLY_PRELU != 0) && (accumulator_s1 < 0))
                    prelu_value_s2 <= round_q15_saturate_int32(prelu_product_s1);
                else
                    prelu_value_s2 <= accumulator_s1;
                multiplier_s2 <= multiplier_s1;
            end
            valid_s2 <= valid_s1;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            requant_product_s3 <= 0;
            valid_s3 <= 1'b0;
        end else begin
            if (valid_s2)
                requant_product_s3 <= prelu_value_s2 * multiplier_s2;
            valid_s3 <= valid_s2;
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            out_data <= 0;
            out_valid <= 1'b0;
        end else begin
            if (valid_s3)
                out_data <= round_q31_saturate_output(requant_product_s3);
            out_valid <= valid_s3;
        end
    end

endmodule
