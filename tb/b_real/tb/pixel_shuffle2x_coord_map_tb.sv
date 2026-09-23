`timescale 1ns / 1ps

module pixel_shuffle2x_coord_map_tb;

    reg [9:0] in_x;
    reg [9:0] in_y;
    reg [1:0] phase;
    reg [7:0] in_data;
    wire [10:0] out_x;
    wire [10:0] out_y;
    wire [7:0] out_data;
    integer errors;

    pixel_shuffle2x_coord_map #(
        .X_W(10), .Y_W(10), .DATA_W(8)
    ) dut (
        .in_x(in_x), .in_y(in_y), .phase(phase), .in_data(in_data),
        .out_x(out_x), .out_y(out_y), .out_data(out_data)
    );

    task check;
        input [1:0] p;
        input [10:0] expected_x;
        input [10:0] expected_y;
        begin
            phase=p;
            #1;
            if ((out_x !== expected_x) || (out_y !== expected_y) ||
                (out_data !== in_data)) begin
                $display("PIXEL_SHUFFLE_MAP_MISMATCH phase=%0d x=%0d y=%0d data=%0d",
                         p, out_x, out_y, out_data);
                errors=errors+1;
            end
        end
    endtask

    initial begin
        errors=0;
        in_x=10'd7;
        in_y=10'd11;
        in_data=8'hA5;
        check(2'd0, 11'd14, 11'd22);
        check(2'd1, 11'd15, 11'd22);
        check(2'd2, 11'd14, 11'd23);
        check(2'd3, 11'd15, 11'd23);

        in_x=10'd959;
        in_y=10'd539;
        in_data=8'h5A;
        check(2'd3, 11'd1919, 11'd1079);

        if (errors == 0)
            $display("ACX750_PIXEL_SHUFFLE2X_COORD_MAP_TEST_PASS");
        else
            $display("ACX750_PIXEL_SHUFFLE2X_COORD_MAP_TEST_FAIL errors=%0d", errors);
        $finish;
    end

endmodule
