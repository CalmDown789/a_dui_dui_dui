`timescale 1ns / 1ps

module window5_backend_integration_tb;

    reg clk;
    reg rst;
    reg [7:0] pixel_in;
    reg pixel_valid;
    wire [199:0] window_flat;
    wire window_valid;
    reg signed [199:0] k_flat;
    reg signed [31:0] bias;
    wire signed [31:0] result;
    wire result_valid;

    integer i;
    integer value;
    integer result_count;
    integer error_count;
    integer timeout_count;

    window5x5_stream #(.DATA_W(8), .IMG_W(6)) u_window (
        .clk(clk), .rst(rst), .pixel_in(pixel_in), .pixel_valid(pixel_valid),
        .window_flat(window_flat), .window_valid(window_valid)
    );

    conv5x5_backend #(
        .ACT_W(8), .WGT_W(8), .ACC_W(32), .CHANNELS(1)
    ) u_backend (
        .clk(clk), .rst(rst), .in_valid(window_valid),
        .x_flat(window_flat), .k_flat(k_flat), .bias(bias),
        .result(result), .result_valid(result_valid)
    );

    initial begin
        clk=1'b0;
        forever #5 clk=~clk;
    end

    always @(posedge clk) begin
        #1;
        if (result_valid) begin
            if ((result_count == 0) && (result !== 32'sd275)) begin
                $display("WINDOW5_INTEGRATION_RESULT0_MISMATCH got=%0d", result);
                error_count=error_count+1;
            end else if ((result_count == 1) && (result !== 32'sd300)) begin
                $display("WINDOW5_INTEGRATION_RESULT1_MISMATCH got=%0d", result);
                error_count=error_count+1;
            end else if (result_count > 1) begin
                $display("WINDOW5_INTEGRATION_UNEXPECTED got=%0d", result);
                error_count=error_count+1;
            end
            result_count=result_count+1;
        end
    end

    task send_pixel;
        input [7:0] sample;
        begin
            @(negedge clk);
            pixel_in=sample;
            pixel_valid=1'b1;
        end
    endtask

    task send_bubble;
        begin
            @(negedge clk);
            pixel_valid=1'b0;
        end
    endtask

    initial begin
        rst=1'b1; pixel_in=0; pixel_valid=1'b0; bias=-100;
        k_flat=0; result_count=0; error_count=0; timeout_count=0;
        for (i=0; i<25; i=i+1)
            k_flat[(i*8) +: 8]=8'sd1;

        repeat (3) @(posedge clk);
        @(negedge clk); rst=1'b0;

        for (value=1; value<=30; value=value+1) begin
            send_pixel(value[7:0]);
            if ((value == 4) || (value == 17) || (value == 28))
                send_bubble();
        end
        @(negedge clk); pixel_valid=1'b0;

        while ((result_count < 2) && (timeout_count < 40)) begin
            @(posedge clk);
            timeout_count=timeout_count+1;
        end

        if (result_count != 2) begin
            $display("WINDOW5_INTEGRATION_COUNT_MISMATCH got=%0d expected=2", result_count);
            error_count=error_count+1;
        end
        if (error_count == 0)
            $display("ACX750_WINDOW5_BACKEND_INTEGRATION_TEST_PASS results=%0d", result_count);
        else
            $display("ACX750_WINDOW5_BACKEND_INTEGRATION_TEST_FAIL errors=%0d", error_count);
        #10; $finish;
    end

endmodule
