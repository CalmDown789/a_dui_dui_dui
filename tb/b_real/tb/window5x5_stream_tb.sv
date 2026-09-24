`timescale 1ns / 1ps

module window5x5_stream_tb;

    reg clk;
    reg rst;
    reg [7:0] pixel_in;
    reg pixel_valid;
    wire [199:0] window_flat;
    wire window_valid;

    integer error_count;
    integer window_count;
    integer value;
    integer tap;
    integer expected;

    window5x5_stream #(
        .DATA_W(8),
        .IMG_W(6)
    ) dut (
        .clk(clk), .rst(rst),
        .pixel_in(pixel_in), .pixel_valid(pixel_valid),
        .window_flat(window_flat), .window_valid(window_valid)
    );

    initial begin
        clk=1'b0;
        forever #5 clk=~clk;
    end

    task check_current_window;
        integer row;
        integer col;
        integer got;
        begin
            for (tap=0; tap<25; tap=tap+1) begin
                row=tap/5;
                col=tap%5;
                expected=(row*6)+col+1+window_count;
                got=window_flat[(tap*8) +: 8];
                if (got != expected) begin
                    $display("WINDOW5_MISMATCH window=%0d tap=%0d got=%0d expected=%0d",
                             window_count, tap, got, expected);
                    error_count=error_count+1;
                end
            end
        end
    endtask

    task send_pixel;
        input [7:0] sample;
        begin
            @(negedge clk);
            pixel_in=sample;
            pixel_valid=1'b1;
            @(posedge clk);
            #1;
            if (window_valid) begin
                check_current_window();
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
            if (window_valid || (dut.row_count != row_before) ||
                (dut.col_count != col_before)) begin
                $display("WINDOW5_BUBBLE_STATE_ERROR");
                error_count=error_count+1;
            end
        end
    endtask

    initial begin
        rst=1'b1;
        pixel_in=0;
        pixel_valid=1'b0;
        error_count=0;
        window_count=0;

        repeat (3) @(posedge clk);
        @(negedge clk);
        rst=1'b0;

        for (value=1; value<=30; value=value+1) begin
            send_pixel(value[7:0]);
            if ((value == 4) || (value == 17) || (value == 28))
                send_bubble();
        end

        @(negedge clk);
        pixel_valid=1'b0;

        if (window_count != 2) begin
            $display("WINDOW5_COUNT_MISMATCH got=%0d expected=2", window_count);
            error_count=error_count+1;
        end

        if (error_count == 0)
            $display("ACX750_WINDOW5X5_TEST_PASS windows=%0d", window_count);
        else
            $display("ACX750_WINDOW5X5_TEST_FAIL errors=%0d", error_count);

        #10;
        $finish;
    end

endmodule
