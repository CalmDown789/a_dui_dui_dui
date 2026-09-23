`timescale 1ns / 1ps

// 成员B工作 / Team member B: five layer phase accumulation and stall test.
module phase_acc_case #(
    parameter integer ID=1,CIN=1,COUT=16,IN_PAR=1,OUT_PAR=2
)(input wire clk,input wire rst,output reg done);
    localparam integer IN_GROUPS=CIN/IN_PAR;
    reg phase_valid=0,out_ready=0;
    reg [2:0] phase=0;
    reg [OUT_PAR*32-1:0] partial_sums=0;
    reg [COUT*32-1:0] bias_flat=0;
    wire phase_ready,out_valid;
    wire [COUT*32-1:0] out_data;
    integer frame,p,l,c,acc,bias,expected_value;
    reg [COUT*32-1:0] held;
    phase_accumulator #(.CIN(CIN),.COUT(COUT),.IN_PAR(IN_PAR),.OUT_PAR(OUT_PAR)) dut (
        .clk(clk),.rst(rst),.phase_valid(phase_valid),.phase_ready(phase_ready),
        .phase(phase),.partial_sums(partial_sums),.bias_flat(bias_flat),
        .out_valid(out_valid),.out_ready(out_ready),.out_data(out_data)
    );
    initial begin
        done=0;
        for(c=0;c<COUT;c=c+1)begin
            if(c==0)bias_flat[c*32+:32]=32'h7fffffff;
            else if(c==1)bias_flat[c*32+:32]=32'h80000000;
            else bias_flat[c*32+:32]=c*17-100;
        end
        wait(!rst);
        for(frame=0;frame<2;frame=frame+1)begin
            for(p=0;p<8;p=p+1)begin
                @(negedge clk);
                phase_valid=1;
                phase=p;
                for(l=0;l<OUT_PAR;l=l+1)
                    partial_sums[l*32+:32]=(frame==0)?(100+p*3+l):(-200-p*5-l);
                do @(posedge clk); while(!phase_ready);
            end
            @(negedge clk);
            phase_valid=0;
            if(!out_valid)$fatal(1,"L%0d frame%0d missing output",ID,frame);
            for(c=0;c<COUT;c=c+1)begin
                acc=0;
                for(p=0;p<8;p=p+1)
                    if(c/OUT_PAR==p/IN_GROUPS)
                        acc=acc+((frame==0)?(100+p*3+c%OUT_PAR):(-200-p*5-c%OUT_PAR));
                if(c==0)bias=2147483647;
                else if(c==1)bias=32'sh80000000;
                else bias=c*17-100;
                if(bias==2147483647 && acc>0)expected_value=2147483647;
                else if(bias==32'sh80000000 && acc<0)expected_value=32'sh80000000;
                else expected_value=bias+acc;
                if($signed(out_data[c*32+:32])!==expected_value)
                    $fatal(1,"L%0d frame=%0d ch=%0d got=%0d want=%0d",ID,frame,c,$signed(out_data[c*32+:32]),expected_value);
            end
            held=out_data;
            repeat(4)begin
                @(posedge clk);
                if(!out_valid||out_data!==held)$fatal(1,"L%0d output changed under stall",ID);
            end
            @(negedge clk);out_ready=1;
            @(posedge clk);
            @(negedge clk);out_ready=0;
        end
        $display("L%0d phase accumulator PASS COUT=%0d",ID,COUT);
        done=1;
    end
endmodule

module phase_accumulator_tb;
    reg clk=0,rst=1;
    always #5 clk=~clk;
    wire d1,d2,d3,d4,d5;
    phase_acc_case #(.ID(1),.CIN(1),.COUT(16),.IN_PAR(1),.OUT_PAR(2)) l1(.clk(clk),.rst(rst),.done(d1));
    phase_acc_case #(.ID(2),.CIN(16),.COUT(8),.IN_PAR(2),.OUT_PAR(8)) l2(.clk(clk),.rst(rst),.done(d2));
    phase_acc_case #(.ID(3),.CIN(8),.COUT(8),.IN_PAR(1),.OUT_PAR(8)) l3(.clk(clk),.rst(rst),.done(d3));
    phase_acc_case #(.ID(4),.CIN(8),.COUT(16),.IN_PAR(1),.OUT_PAR(16)) l4(.clk(clk),.rst(rst),.done(d4));
    phase_acc_case #(.ID(5),.CIN(16),.COUT(4),.IN_PAR(2),.OUT_PAR(4)) l5(.clk(clk),.rst(rst),.done(d5));
    initial begin
        repeat(3)@(negedge clk);rst=0;
        wait(d1&&d2&&d3&&d4&&d5);
        $display("ACX750_MEMBER_B_PHASE_ACCUM_PASS layers=5 frames=2");
        $finish;
    end
endmodule
