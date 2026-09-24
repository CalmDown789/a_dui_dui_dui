`timescale 1ns / 1ps
module window5x5_bram_tb;
    reg clk,rst;reg[7:0]pixel_in;reg pixel_valid;
    wire[199:0]window_flat;wire window_valid;
    integer value,tap,row,col,got,expected,window_count,error_count,timeout_count;
    window5x5_bram #(.DATA_W(8),.IMG_W(6)) dut(
        .clk(clk),.rst(rst),.pixel_in(pixel_in),.pixel_valid(pixel_valid),
        .window_flat(window_flat),.window_valid(window_valid));
    initial begin clk=0;forever #5 clk=~clk;end
    always @(posedge clk)begin
        #1;
        if(window_valid)begin
            for(tap=0;tap<25;tap=tap+1)begin
                row=tap/5;col=tap%5;expected=row*6+col+1+window_count;
                got=window_flat[tap*8+:8];
                if(got!=expected)begin
                    $display("BRAM5_MISMATCH window=%0d tap=%0d got=%0d exp=%0d",window_count,tap,got,expected);
                    error_count=error_count+1;
                end
            end
            window_count=window_count+1;
        end
    end
    task send_pixel;input[7:0]sample;begin @(negedge clk);pixel_in=sample;pixel_valid=1;end endtask
    task bubble;begin @(negedge clk);pixel_valid=0;end endtask
    initial begin
        rst=1;pixel_in=0;pixel_valid=0;window_count=0;error_count=0;timeout_count=0;
        repeat(3)@(posedge clk);@(negedge clk);rst=0;
        for(value=1;value<=30;value=value+1)begin
            send_pixel(value[7:0]);
            if((value==4)||(value==17)||(value==28))bubble();
        end
        @(negedge clk);pixel_valid=0;
        while((window_count<2)&&(timeout_count<20))begin @(posedge clk);timeout_count=timeout_count+1;end
        if(window_count!=2)begin $display("BRAM5_COUNT_MISMATCH got=%0d",window_count);error_count=error_count+1;end
        if(error_count==0)$display("ACX750_WINDOW5X5_BRAM_TEST_PASS windows=%0d",window_count);
        else $display("ACX750_WINDOW5X5_BRAM_TEST_FAIL errors=%0d",error_count);
        #10;$finish;
    end
endmodule
