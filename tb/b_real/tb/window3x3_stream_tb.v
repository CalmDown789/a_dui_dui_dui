`timescale 1ns / 1ps

module window3x3_stream_tb;

    reg clk;
    reg rst;
    reg [7:0] pixel_in;
    reg pixel_valid;

    wire [7:0] w00, w01, w02;
    wire [7:0] w10, w11, w12;
    wire [7:0] w20, w21, w22;
    wire window_valid;

    integer error_count;
    integer window_count;

    window3x3_stream #(
        .DATA_W(8),
        .IMG_W(4)
    ) dut (
        .clk(clk), .rst(rst),
        .pixel_in(pixel_in), .pixel_valid(pixel_valid),
        .w00(w00), .w01(w01), .w02(w02),
        .w10(w10), .w11(w11), .w12(w12),
        .w20(w20), .w21(w21), .w22(w22),
        .window_valid(window_valid)
    );

    initial begin
        clk=1'b0;
        forever #5 clk=~clk;
    end

    task check_window;
        input [7:0] e00, e01, e02;
        input [7:0] e10, e11, e12;
        input [7:0] e20, e21, e22;
        begin
            if ((w00 !== e00) || (w01 !== e01) || (w02 !== e02) ||
                (w10 !== e10) || (w11 !== e11) || (w12 !== e12) ||
                (w20 !== e20) || (w21 !== e21) || (w22 !== e22)) begin
                $display("WINDOW_MISMATCH count=%0d", window_count);
                $display("got %0d %0d %0d | %0d %0d %0d | %0d %0d %0d",
                         w00,w01,w02,w10,w11,w12,w20,w21,w22);
                $display("exp %0d %0d %0d | %0d %0d %0d | %0d %0d %0d",
                         e00,e01,e02,e10,e11,e12,e20,e21,e22);
                error_count=error_count+1;
            end
        end
    endtask

    task send_pixel;
        input [7:0] value;
        begin
            @(negedge clk);
            pixel_in=value;
            pixel_valid=1'b1;
            @(posedge clk);
            #1;

            if (window_valid) begin
                case (window_count)
                    0: check_window(1,2,3,5,6,7,9,10,11);
                    1: check_window(2,3,4,6,7,8,10,11,12);
                    2: check_window(5,6,7,9,10,11,13,14,15);
                    3: check_window(6,7,8,10,11,12,14,15,16);
                    default: begin
                        $display("UNEXPECTED_WINDOW count=%0d", window_count);
                        error_count=error_count+1;
                    end
                endcase
                window_count=window_count+1;
            end
        end
    endtask

    task send_bubble;
        reg [15:0] row_before;
        reg [15:0] col_before;
        begin
            row_before=dut.row_count;
            col_before=dut.col_count;
            @(negedge clk);
            pixel_valid=1'b0;
            @(posedge clk);
            #1;
            if (window_valid !== 1'b0) begin
                $display("VALID_DURING_BUBBLE");
                error_count=error_count+1;
            end
            if ((dut.row_count !== row_before) || (dut.col_count !== col_before)) begin
                $display("COUNTER_MOVED_DURING_BUBBLE");
                error_count=error_count+1;
            end
        end
    endtask

    integer value;
    initial begin
        rst=1'b1;
        pixel_in=0;
        pixel_valid=1'b0;
        error_count=0;
        window_count=0;

        repeat (3) @(posedge clk);
        @(negedge clk);
        rst=1'b0;

        for (value=1; value<=16; value=value+1) begin
            send_pixel(value[7:0]);
            if ((value == 2) || (value == 10) || (value == 15))
                send_bubble();
        end

        @(negedge clk);
        pixel_valid=1'b0;

        if (window_count != 4) begin
            $display("WINDOW_COUNT_MISMATCH got=%0d expected=4", window_count);
            error_count=error_count+1;
        end

        if (error_count == 0)
            $display("ACX750_WINDOW3X3_TEST_PASS windows=%0d", window_count);
        else
            $display("ACX750_WINDOW3X3_TEST_FAIL errors=%0d", error_count);

        #10;
        $finish;
    end

endmodule
