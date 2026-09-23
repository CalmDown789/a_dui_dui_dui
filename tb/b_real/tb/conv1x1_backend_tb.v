`timescale 1ns / 1ps
module conv1x1_backend_tb;
    reg clk,rst,in_valid;reg signed[7:0]x,k;reg signed[31:0]bias;
    wire signed[31:0]result;wire result_valid;
    integer result_count,error_count,timeout_count;
    conv1x1_backend #(.ACT_W(8),.WGT_W(8),.ACC_W(32),.CHANNELS(3))dut(
        .clk(clk),.rst(rst),.in_valid(in_valid),.x(x),.k(k),.bias(bias),
        .result(result),.result_valid(result_valid));
    initial begin clk=0;forever #5 clk=~clk;end
    task send;input signed[7:0]xv;input signed[7:0]kv;input signed[31:0]bv;
        begin @(negedge clk);x=xv;k=kv;bias=bv;in_valid=1;end endtask
    always @(posedge clk)begin
        #1;if(result_valid)begin
            if((result_count==0)&&(result!==32'sd4))begin $display("CONV1_RESULT0_MISMATCH got=%0d",result);error_count=error_count+1;end
            else if((result_count==1)&&(result!==-32'sd69))begin $display("CONV1_RESULT1_MISMATCH got=%0d",result);error_count=error_count+1;end
            else if(result_count>1)begin $display("CONV1_UNEXPECTED got=%0d",result);error_count=error_count+1;end
            result_count=result_count+1;
        end
    end
    initial begin
        rst=1;in_valid=0;x=0;k=0;bias=0;result_count=0;error_count=0;timeout_count=0;
        repeat(3)@(posedge clk);@(negedge clk);rst=0;
        // 10 + 2*3 + (-4)*5 + 1*8 = 4
        send(2,3,10);send(-4,5,999);send(1,8,-999);
        @(negedge clk);in_valid=0;@(negedge clk);
        // -7 + (-128)*1 + 127*1 + (-61)*1 = -69
        send(-128,1,-7);send(127,1,111);send(-61,1,222);
        @(negedge clk);in_valid=0;
        while((result_count<2)&&(timeout_count<30))begin @(posedge clk);timeout_count=timeout_count+1;end
        if(result_count!=2)begin $display("CONV1_COUNT_MISMATCH got=%0d",result_count);error_count=error_count+1;end
        if(error_count==0)$display("ACX750_CONV1X1_BACKEND_TEST_PASS results=%0d",result_count);
        else $display("ACX750_CONV1X1_BACKEND_TEST_FAIL errors=%0d",error_count);
        #10;$finish;
    end
endmodule
