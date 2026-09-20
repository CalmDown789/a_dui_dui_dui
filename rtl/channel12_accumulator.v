`timescale 1ns / 1ps

module channel12_accumulator #(
    parameter integer DOT_W    = 20,
    parameter integer ACC_W    = 24,
    parameter integer CHANNELS = 12,
    parameter integer COUNT_W  = $clog2(CHANNELS)
)(
    input  wire                         clk,
    input  wire                         rst,
    input  wire                         dot9_valid,
    input  wire signed [DOT_W-1:0]      dot9,
    input  wire signed [ACC_W-1:0]      bias,

    output reg  signed [ACC_W-1:0]      result,
    output reg                          result_valid
);

    // Number of valid dot9 values already accumulated in the current group.
    reg signed [ACC_W-1:0] acc;
    reg        [COUNT_W-1:0] channel_count;

    // Extend dot9 to the accumulator width before signed addition.
    wire signed [ACC_W-1:0] dot9_ext;
    assign dot9_ext = {
        {(ACC_W-DOT_W){dot9[DOT_W-1]}},
        dot9
    };

    always @(posedge clk) begin
        if (rst) begin
            acc           <= 0;
            channel_count <= 0;
            result        <= 0;
            result_valid  <= 1'b0;
        end
        else begin
            // A result is valid for exactly one cycle when a group completes.
            result_valid <= 1'b0;

            if (dot9_valid) begin
                if (channel_count == CHANNELS-1) begin
                    // dot9 is the twelfth contribution of this output group.
                    result        <= acc + dot9_ext + bias;
                    result_valid  <= 1'b1;
                    acc           <= 0;
                    channel_count <= 0;
                end
                else begin
                    acc           <= acc + dot9_ext;
                    channel_count <= channel_count + 1'b1;
                end
            end
        end
    end

endmodule
