`timescale 1ns / 1ps

// 成员B工作 / Team member B: phase/order/stall regression.
module eight_phase_issue_tb;
    reg clk=0,rst=1,in_valid=0,out_ready=0;
    reg [15:0] in_window=0;
    wire in_ready,out_valid,out_last_phase;
    wire [15:0] out_window;
    wire [2:0] out_phase;
    integer cycle=0,sent=0,received=0;
    reg held=0;
    reg [15:0] held_window;
    reg [2:0] held_phase;
    reg held_last;
    always #5 clk=~clk;
    eight_phase_issue #(.DATA_W(16)) dut (
        .clk(clk),.rst(rst),.in_valid(in_valid),.in_ready(in_ready),
        .in_window(in_window),.out_valid(out_valid),.out_ready(out_ready),
        .out_window(out_window),.out_phase(out_phase),.out_last_phase(out_last_phase)
    );
    initial begin
        repeat(3)@(negedge clk);rst=0;
        wait(received==13*8);
        if(sent!=13)$fatal(1,"accepted windows=%0d",sent);
        $display("ACX750_MEMBER_B_EIGHT_PHASE_PASS windows=13 transfers=104");
        $finish;
    end
    always @(negedge clk)begin
        if(!rst)begin
            cycle=cycle+1;
            in_valid=(sent<13)&&((cycle%11)!=4);
            in_window=16'h5000+sent;
            out_ready=((cycle%7)!=1)&&((cycle%7)!=2);
        end
    end
    always @(posedge clk)begin
        if(!rst)begin
            if(held&&(!out_valid||out_window!==held_window||out_phase!==held_phase||out_last_phase!==held_last))
                $fatal(1,"issue output changed under stall");
            held=out_valid&&!out_ready;
            if(held)begin
                held_window=out_window;held_phase=out_phase;held_last=out_last_phase;
            end
            if(out_valid&&out_ready)begin
                if(out_window!==(16'h5000+received/8)||out_phase!==(received%8)||out_last_phase!==(received%8==7))
                    $fatal(1,"transfer=%0d window=%h phase=%0d last=%b",received,out_window,out_phase,out_last_phase);
                received=received+1;
            end
            if(in_valid&&in_ready)sent=sent+1;
            if(cycle>400)$fatal(1,"issue timeout");
        end
    end
endmodule
