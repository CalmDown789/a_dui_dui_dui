`timescale 1ns / 1ps

module channel12_accumulator_tb;

    localparam integer DOT_W = 20;
    localparam integer ACC_W = 24;

    reg clk;
    reg rst;
    reg dot9_valid;
    reg signed [DOT_W-1:0] dot9;
    reg signed [ACC_W-1:0] bias;

    wire signed [ACC_W-1:0] result;
    wire                    result_valid;

    integer error_count;
    integer model_count;
    reg signed [ACC_W-1:0] model_acc;

    channel12_accumulator #(
        .DOT_W    (DOT_W),
        .ACC_W    (ACC_W),
        .CHANNELS (12)
    ) dut (
        .clk          (clk),
        .rst          (rst),
        .dot9_valid   (dot9_valid),
        .dot9         (dot9),
        .bias         (bias),
        .result       (result),
        .result_valid (result_valid)
    );

    initial begin
        clk = 1'b0;
        forever #5 clk = ~clk;
    end

    task send_dot9;
        input signed [DOT_W-1:0] value;
        begin
            @(negedge clk);
            dot9_valid = 1'b1;
            dot9       = value;
        end
    endtask

    task send_bubble;
        begin
            @(negedge clk);
            dot9_valid = 1'b0;
            dot9       = 20'sd12345; // Deliberately meaningless while invalid.
        end
    endtask

    // Independent reference model and cycle-by-cycle valid checking.
    always @(posedge clk) begin
        if (rst) begin
            model_acc   = 0;
            model_count = 0;
        end
        else if (dot9_valid) begin
            if (model_count == 11) begin
                #1;
                if (result_valid !== 1'b1) begin
                    $display("ERROR: result_valid should be 1 at %0t", $time);
                    error_count = error_count + 1;
                end
                if (result !== model_acc + $signed(dot9) + $signed(bias)) begin
                    $display("ERROR: result=%0d expected=%0d at %0t",
                             result,
                             model_acc + $signed(dot9) + $signed(bias),
                             $time);
                    error_count = error_count + 1;
                end
                model_acc   = 0;
                model_count = 0;
            end
            else begin
                #1;
                if (result_valid !== 1'b0) begin
                    $display("ERROR: early result_valid at %0t", $time);
                    error_count = error_count + 1;
                end
                model_acc   = model_acc + $signed(dot9);
                model_count = model_count + 1;
            end
        end
        else begin
            #1;
            if (result_valid !== 1'b0) begin
                $display("ERROR: result_valid asserted on bubble at %0t", $time);
                error_count = error_count + 1;
            end
        end
    end

    initial begin
        rst         = 1'b1;
        dot9_valid  = 1'b0;
        dot9        = 0;
        bias        = -24'sd2;
        error_count = 0;

        repeat (2) @(negedge clk);
        rst = 1'b0;

        // Group A: sum=22, bias=-2, expected result=20.
        send_dot9( 20'sd10);
        send_dot9(-20'sd3);
        send_dot9( 20'sd5);
        send_dot9( 20'sd0);
        send_bubble;
        send_dot9( 20'sd2);
        send_dot9(-20'sd4);
        send_dot9( 20'sd7);
        send_dot9( 20'sd1);
        send_dot9(-20'sd6);
        send_dot9( 20'sd8);
        send_bubble;
        send_dot9(-20'sd2);
        send_dot9( 20'sd4);

        // Group B starts on the next available cycle: 12*(-1)-3=-15.
        @(negedge clk);
        bias        = -24'sd3;
        dot9_valid  = 1'b1;
        dot9        = -20'sd1;
        repeat (11) send_dot9(-20'sd1);

        send_bubble;
        repeat (2) @(posedge clk);
        #1;

        if (error_count == 0)
            $display("CHANNEL12_ACCUMULATOR_TEST_PASS");
        else
            $display("CHANNEL12_ACCUMULATOR_TEST_FAIL errors=%0d", error_count);

        $finish;
    end

endmodule
