`timescale 1ns / 1ps

module window3x3_stream_tb;

    reg         clk;
    reg         rst;
    reg  [7:0]  pixel_in;
    reg         pixel_valid;

    wire [7:0]  w00;
    wire [7:0]  w01;
    wire [7:0]  w02;
    wire [7:0]  w10;
    wire [7:0]  w11;
    wire [7:0]  w12;
    wire [7:0]  w20;
    wire [7:0]  w21;
    wire [7:0]  w22;
    wire        window_valid;

    integer error_count;

    window3x3_stream #(
        .DATA_W (8),
        .IMG_W  (4)
    ) dut (
        .clk          (clk),
        .rst          (rst),
        .pixel_in     (pixel_in),
        .pixel_valid  (pixel_valid),
        .w00          (w00),
        .w01          (w01),
        .w02          (w02),
        .w10          (w10),
        .w11          (w11),
        .w12          (w12),
        .w20          (w20),
        .w21          (w21),
        .w22          (w22),
        .window_valid (window_valid)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    task check_window;
        input [7:0] e00;
        input [7:0] e01;
        input [7:0] e02;
        input [7:0] e10;
        input [7:0] e11;
        input [7:0] e12;
        input [7:0] e20;
        input [7:0] e21;
        input [7:0] e22;
        begin
            if ((w00 !== e00) || (w01 !== e01) || (w02 !== e02) ||
                (w10 !== e10) || (w11 !== e11) || (w12 !== e12) ||
                (w20 !== e20) || (w21 !== e21) || (w22 !== e22)) begin
                $display("WINDOW_MISMATCH at time %0t", $time);
                $display("  got: %0d %0d %0d | %0d %0d %0d | %0d %0d %0d",
                         w00, w01, w02, w10, w11, w12, w20, w21, w22);
                $display("  exp: %0d %0d %0d | %0d %0d %0d | %0d %0d %0d",
                         e00, e01, e02, e10, e11, e12, e20, e21, e22);
                error_count = error_count + 1;
            end
        end
    endtask

    task send_pixel;
        input [7:0] value;
        begin
            @(negedge clk);
            pixel_in    = value;
            pixel_valid = 1'b1;

            @(posedge clk);
            #1;

            case (value)
                8'd11: begin
                    if (window_valid !== 1'b1)
                        error_count = error_count + 1;
                    check_window(1, 2, 3, 5, 6, 7, 9, 10, 11);
                end
                8'd12: begin
                    if (window_valid !== 1'b1)
                        error_count = error_count + 1;
                    check_window(2, 3, 4, 6, 7, 8, 10, 11, 12);
                end
                8'd15: begin
                    if (window_valid !== 1'b1)
                        error_count = error_count + 1;
                    check_window(5, 6, 7, 9, 10, 11, 13, 14, 15);
                end
                8'd16: begin
                    if (window_valid !== 1'b1)
                        error_count = error_count + 1;
                    check_window(6, 7, 8, 10, 11, 12, 14, 15, 16);
                end
                default: begin
                    if (window_valid !== 1'b0)
                        error_count = error_count + 1;
                end
            endcase
        end
    endtask

    task send_bubble;
        begin
            @(negedge clk);
            pixel_valid = 1'b0;

            @(posedge clk);
            #1;

            if (window_valid !== 1'b0) begin
                $display("VALID_ERROR during bubble at time %0t", $time);
                error_count = error_count + 1;
            end

            check_window(0, 1, 2, 0, 5, 6, 0, 9, 10);

            if ((dut.row_count !== 16'd2) || (dut.col_count !== 2)) begin
                $display("COUNTER_MOVED during bubble at time %0t", $time);
                error_count = error_count + 1;
            end
        end
    endtask

    initial begin
        rst         = 1'b1;
        pixel_in    = 8'd0;
        pixel_valid = 1'b0;
        error_count = 0;

        repeat (2) @(posedge clk);
        @(negedge clk);
        rst = 1'b0;

        send_pixel(1);
        send_pixel(2);
        send_pixel(3);
        send_pixel(4);
        send_pixel(5);
        send_pixel(6);
        send_pixel(7);
        send_pixel(8);
        send_pixel(9);
        send_pixel(10);

        // The bubble must not occupy an image position.
        send_bubble;

        send_pixel(11);
        send_pixel(12);
        send_pixel(13);
        send_pixel(14);
        send_pixel(15);
        send_pixel(16);

        @(negedge clk);
        pixel_valid = 1'b0;

        if (error_count == 0)
            $display("WINDOW3X3_TEST_PASS");
        else
            $display("WINDOW3X3_TEST_FAIL errors=%0d", error_count);

        #10;
        $finish;
    end

endmodule
