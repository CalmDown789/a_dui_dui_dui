`timescale 1ns / 1ps
module tb_phase_acc36;
    reg clk=0;
    always #5 clk=~clk;
    reg rst=1;
    reg phase_valid=0;
    wire phase_ready;
    reg [2:0] phase=0;
    reg [31:0] partial_sums=0;
    reg [31:0] bias_flat=0;
    wire out_valid;
    reg out_ready=1;
    wire [31:0] out_data;
    integer case_idx;

    phase_accumulator #(.CIN(8),.COUT(1),.IN_PAR(1),.OUT_PAR(1)) dut (
        .clk(clk),.rst(rst),.phase_valid(phase_valid),.phase_ready(phase_ready),
        .phase(phase),.partial_sums(partial_sums),.bias_flat(bias_flat),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data)
    );

    function [31:0] sat48;
        input signed [47:0] v;
        begin
            if(v>48'sd2147483647) sat48=32'h7fffffff;
            else if(v< -48'sd2147483648) sat48=32'h80000000;
            else sat48=v[31:0];
        end
    endfunction

    task automatic run_case(input integer mode);
        integer p;
        reg signed [31:0] x;
        reg signed [31:0] b;
        reg signed [47:0] gold_sum;
        reg [31:0] expected;
        begin
            case(mode)
                0: b=32'sh7fffffff;
                1: b=32'sh80000000;
                2,3,4,5,8: b=0;
                6: b=32'sh7fffffff;
                7: b=32'sh80000000;
                default: b=$random;
            endcase
            bias_flat=b;
            gold_sum=0;
            for(p=0;p<8;p=p+1) begin
                case(mode)
                    0: x=32'sh7fffffff;
                    1: x=32'sh80000000;
                    2: x=(p==0)?32'sh7fffffff:0;
                    3: x=(p==0)?32'sh80000000:0;
                    4: x=(p==0)?32'sh7fffffff:0;
                    5: x=(p==0)?32'sh80000000:0;
                    6,7: x=0;
                    8: x=(p==0)?32'sh075bcd15:((p==1)?-32'sh075bcd15:0);
                    default: x=$random;
                endcase
                @(negedge clk);
                if(!phase_ready) $fatal(1,"phase_ready unexpectedly low");
                phase_valid=1;
                phase=p;
                partial_sums=x;
                @(posedge clk);
                gold_sum=gold_sum+x;
            end
            @(negedge clk);
            phase_valid=0;
            @(posedge clk); #1;
            expected=sat48(gold_sum+b);
            if(!out_valid) $fatal(1,"case %0d missing out_valid",mode);
            if(out_data!==expected)
                $fatal(1,"case %0d mismatch got=%08x expected=%08x sum=%0d bias=%0d",mode,out_data,expected,gold_sum,b);
        end
    endtask

    initial begin
        #2; rst=1;
        repeat(2) @(posedge clk);
        @(negedge clk); rst=0;
        for(case_idx=0;case_idx<9;case_idx=case_idx+1) run_case(case_idx);
        for(case_idx=0;case_idx<256;case_idx=case_idx+1) run_case(9);
        $display("RESULT: PASS");
        $finish;
    end
    initial begin
        #1000000;
        $fatal(1,"watchdog timeout");
    end
endmodule