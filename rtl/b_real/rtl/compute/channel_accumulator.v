`timescale 1ns / 1ps

// Team member B: pure-RTL cross-channel accumulation and INT32 saturation.

module channel_accumulator #(
    parameter integer DOT_W    = 20,
    parameter integer ACC_W    = 32,
    parameter integer CHANNELS = 1,
    parameter integer COUNT_W  = (CHANNELS <= 1) ? 1 : $clog2(CHANNELS),
    parameter integer SUM_GROW = (CHANNELS <= 1) ? 0 : $clog2(CHANNELS),
    parameter integer INTERNAL_W =
        (ACC_W > (DOT_W + SUM_GROW) ? ACC_W : (DOT_W + SUM_GROW)) + 1
)(
    input  wire clk,
    input  wire rst,
    input  wire dot_valid,
    input  wire signed [DOT_W-1:0] dot_value,
    input  wire signed [ACC_W-1:0] bias,

    output reg signed [ACC_W-1:0] result,
    output reg                    result_valid
);

    reg signed [INTERNAL_W-1:0] accumulator;
    reg [COUNT_W-1:0] channel_count;

    wire signed [INTERNAL_W-1:0] dot_extended;
    wire signed [INTERNAL_W-1:0] bias_extended;
    assign dot_extended = {{(INTERNAL_W-DOT_W){dot_value[DOT_W-1]}}, dot_value};
    assign bias_extended = {{(INTERNAL_W-ACC_W){bias[ACC_W-1]}}, bias};

    localparam signed [ACC_W-1:0] ACC_MAX = {1'b0, {(ACC_W-1){1'b1}}};
    localparam signed [ACC_W-1:0] ACC_MIN = {1'b1, {(ACC_W-1){1'b0}}};

    function signed [ACC_W-1:0] saturate_to_acc;
        input signed [INTERNAL_W-1:0] value;
        reg signed [INTERNAL_W-1:0] max_extended;
        reg signed [INTERNAL_W-1:0] min_extended;
        begin
            max_extended = {{(INTERNAL_W-ACC_W){ACC_MAX[ACC_W-1]}}, ACC_MAX};
            min_extended = {{(INTERNAL_W-ACC_W){ACC_MIN[ACC_W-1]}}, ACC_MIN};
            if (value > max_extended)
                saturate_to_acc = ACC_MAX;
            else if (value < min_extended)
                saturate_to_acc = ACC_MIN;
            else
                saturate_to_acc = value[ACC_W-1:0];
        end
    endfunction

    initial begin
        if (CHANNELS < 1)
            $error("CHANNELS must be at least 1");
        if (ACC_W < DOT_W)
            $error("ACC_W must not be smaller than DOT_W");
    end

    always @(posedge clk) begin
        if (rst) begin
            accumulator <= 0;
            channel_count <= 0;
            result <= 0;
            result_valid <= 1'b0;
        end else begin
            result_valid <= 1'b0;

            if (dot_valid) begin
                if (CHANNELS == 1) begin
                    result <= saturate_to_acc(bias_extended + dot_extended);
                    result_valid <= 1'b1;
                    accumulator <= 0;
                    channel_count <= 0;
                end else if (channel_count == 0) begin
                    accumulator <= bias_extended + dot_extended;
                    channel_count <= 1;
                end else if (channel_count == CHANNELS-1) begin
                    result <= saturate_to_acc(accumulator + dot_extended);
                    result_valid <= 1'b1;
                    accumulator <= 0;
                    channel_count <= 0;
                end else begin
                    accumulator <= accumulator + dot_extended;
                    channel_count <= channel_count + 1'b1;
                end
            end
        end
    end

endmodule
