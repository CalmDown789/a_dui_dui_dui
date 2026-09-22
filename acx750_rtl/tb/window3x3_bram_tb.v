`timescale 1ns / 1ps

module window3x3_bram_tb;
    reg clk, rst;
    reg [7:0] pixel_in;
    reg pixel_valid;
    wire [7:0] w00,w01,w02,w10,w11,w12,w20,w21,w22;
    wire window_valid;
    integer value, window_count, error_count, timeout_count;

    window3x3_bram #(.DATA_W(8),.IMG_W(4)) dut (
        .clk(clk),.rst(rst),.pixel_in(pixel_in),.pixel_valid(pixel_valid),
        .w00(w00),.w01(w01),.w02(w02),.w10(w10),.w11(w11),.w12(w12),
        .w20(w20),.w21(w21),.w22(w22),.window_valid(window_valid)
    );

    initial begin clk=0; forever #5 clk=~clk; end

    task check9;
        input [7:0] e00,e01,e02,e10,e11,e12,e20,e21,e22;
        begin
            if ({w00,w01,w02,w10,w11,w12,w20,w21,w22} !==
                {e00,e01,e02,e10,e11,e12,e20,e21,e22}) begin
                $display("BRAM_WINDOW_MISMATCH count=%0d",window_count);
                error_count=error_count+1;
            end
        end
    endtask

    always @(posedge clk) begin
        #1;
        if (window_valid) begin
            case(window_count)
                0: check9(1,2,3,5,6,7,9,10,11);
                1: check9(2,3,4,6,7,8,10,11,12);
                2: check9(5,6,7,9,10,11,13,14,15);
                3: check9(6,7,8,10,11,12,14,15,16);
                default: begin
                    $display("BRAM_WINDOW_UNEXPECTED");
                    error_count=error_count+1;
                end
            endcase
            window_count=window_count+1;
        end
    end

    task send_pixel;
        input [7:0] sample;
        begin @(negedge clk); pixel_in=sample; pixel_valid=1; end
    endtask
    task bubble;
        begin @(negedge clk); pixel_valid=0; end
    endtask

    initial begin
        rst=1; pixel_in=0; pixel_valid=0;
        window_count=0; error_count=0; timeout_count=0;
        repeat(3) @(posedge clk);
        @(negedge clk); rst=0;
        for(value=1;value<=16;value=value+1) begin
            send_pixel(value[7:0]);
            if((value==2)||(value==10)||(value==15)) bubble();
        end
        @(negedge clk); pixel_valid=0;
        while((window_count<4)&&(timeout_count<20)) begin
            @(posedge clk); timeout_count=timeout_count+1;
        end
        if(window_count!=4) begin
            $display("BRAM_WINDOW_COUNT_MISMATCH got=%0d",window_count);
            error_count=error_count+1;
        end
        if(error_count==0)
            $display("ACX750_WINDOW3X3_BRAM_TEST_PASS windows=%0d",window_count);
        else
            $display("ACX750_WINDOW3X3_BRAM_TEST_FAIL errors=%0d",error_count);
        #10; $finish;
    end
endmodule
