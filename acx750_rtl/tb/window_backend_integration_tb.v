`timescale 1ns / 1ps

module window_backend_integration_tb;

    reg clk;
    reg rst;
    reg [7:0] pixel_in;
    reg pixel_valid;

    wire [7:0] w00, w01, w02;
    wire [7:0] w10, w11, w12;
    wire [7:0] w20, w21, w22;
    wire window_valid;

    reg signed [7:0] k00, k01, k02;
    reg signed [7:0] k10, k11, k12;
    reg signed [7:0] k20, k21, k22;
    reg signed [31:0] bias;
    wire signed [31:0] result;
    wire result_valid;

    integer error_count;
    integer result_count;
    integer timeout_count;

    window3x3_stream #(
        .DATA_W(8),
        .IMG_W(4)
    ) u_window (
        .clk(clk), .rst(rst),
        .pixel_in(pixel_in), .pixel_valid(pixel_valid),
        .w00(w00), .w01(w01), .w02(w02),
        .w10(w10), .w11(w11), .w12(w12),
        .w20(w20), .w21(w21), .w22(w22),
        .window_valid(window_valid)
    );

    conv3x3_backend #(
        .ACT_W(8),
        .WGT_W(8),
        .ACC_W(32),
        .CHANNELS(1)
    ) u_backend (
        .clk(clk), .rst(rst), .in_valid(window_valid),
        .x00(w00), .x01(w01), .x02(w02),
        .x10(w10), .x11(w11), .x12(w12),
        .x20(w20), .x21(w21), .x22(w22),
        .k00(k00), .k01(k01), .k02(k02),
        .k10(k10), .k11(k11), .k12(k12),
        .k20(k20), .k21(k21), .k22(k22),
        .bias(bias),
        .result(result), .result_valid(result_valid)
    );

    initial begin
        clk=1'b0;
        forever #5 clk=~clk;
    end

    always @(posedge clk) begin
        #1;
        if (result_valid) begin
            case (result_count)
                0: if (result !== 32'sd44) begin
                    $display("INTEGRATION_RESULT0_MISMATCH got=%0d", result);
                    error_count=error_count+1;
                end
                1: if (result !== 32'sd53) begin
                    $display("INTEGRATION_RESULT1_MISMATCH got=%0d", result);
                    error_count=error_count+1;
                end
                2: if (result !== 32'sd80) begin
                    $display("INTEGRATION_RESULT2_MISMATCH got=%0d", result);
                    error_count=error_count+1;
                end
                3: if (result !== 32'sd89) begin
                    $display("INTEGRATION_RESULT3_MISMATCH got=%0d", result);
                    error_count=error_count+1;
                end
                default: begin
                    $display("UNEXPECTED_INTEGRATION_RESULT got=%0d", result);
                    error_count=error_count+1;
                end
            endcase
            result_count=result_count+1;
        end
    end

    task send_pixel;
        input [7:0] value;
        begin
            @(negedge clk);
            pixel_in=value;
            pixel_valid=1'b1;
        end
    endtask

    task send_bubble;
        begin
            @(negedge clk);
            pixel_valid=1'b0;
        end
    endtask

    integer value;
    initial begin
        rst=1'b1;
        pixel_in=0;
        pixel_valid=1'b0;
        k00=1; k01=1; k02=1;
        k10=1; k11=1; k12=1;
        k20=1; k21=1; k22=1;
        bias=-10;
        error_count=0;
        result_count=0;
        timeout_count=0;

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

        while ((result_count < 4) && (timeout_count < 30)) begin
            @(posedge clk);
            timeout_count=timeout_count+1;
        end

        if (result_count != 4) begin
            $display("INTEGRATION_RESULT_COUNT_MISMATCH got=%0d expected=4", result_count);
            error_count=error_count+1;
        end

        if (error_count == 0)
            $display("ACX750_WINDOW_BACKEND_INTEGRATION_TEST_PASS results=%0d", result_count);
        else
            $display("ACX750_WINDOW_BACKEND_INTEGRATION_TEST_FAIL errors=%0d", error_count);

        #10;
        $finish;
    end

endmodule
