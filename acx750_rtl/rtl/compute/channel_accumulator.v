`timescale 1ns / 1ps

module channel_accumulator #(
    parameter integer DOT_W    = 20,
    parameter integer ACC_W    = 32,
    parameter integer CHANNELS = 1,
    parameter integer COUNT_W  = (CHANNELS <= 1) ? 1 : $clog2(CHANNELS)
)(
    input  wire clk,
    input  wire rst,
    input  wire dot_valid,
    input  wire signed [DOT_W-1:0] dot_value,
    input  wire signed [ACC_W-1:0] bias,

    output reg signed [ACC_W-1:0] result,
    output reg                    result_valid
);

    reg signed [ACC_W-1:0] accumulator;
    reg [COUNT_W-1:0] channel_count;

    wire signed [ACC_W-1:0] dot_extended;
    assign dot_extended = {{(ACC_W-DOT_W){dot_value[DOT_W-1]}}, dot_value};

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
                    result <= bias + dot_extended;
                    result_valid <= 1'b1;
                    accumulator <= 0;
                    channel_count <= 0;
                end else if (channel_count == 0) begin
                    accumulator <= bias + dot_extended;
                    channel_count <= 1;
                end else if (channel_count == CHANNELS-1) begin
                    result <= accumulator + dot_extended;
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
