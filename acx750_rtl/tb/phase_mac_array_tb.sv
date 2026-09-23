`timescale 1ns / 1ps

// 成员B工作 / Team member B: five frozen shapes, signed and uint8 L1.
module phase_mac_case #(
    parameter integer ID=1,K=5,CIN=1,COUT=16,IN_PAR=1,OUT_PAR=2,
    parameter integer ACT_W=8,ACT_UNSIGNED=1
)(output reg done);
    localparam integer TAPS=K*K;
    reg [2:0] phase=0;
    reg [TAPS*CIN*ACT_W-1:0] window_flat=0;
    reg [COUT*CIN*TAPS*8-1:0] weight_flat=0;
    wire [OUT_PAR*32-1:0] partial_sums;
    integer t,ic,oc,p,o,i,activation,weight,acc,group_out,group_in;
    phase_mac_array #(.K(K),.CIN(CIN),.COUT(COUT),.IN_PAR(IN_PAR),
        .OUT_PAR(OUT_PAR),.ACT_W(ACT_W),.ACT_UNSIGNED(ACT_UNSIGNED)) dut (
        .phase(phase),.window_flat(window_flat),.weight_flat(weight_flat),
        .partial_sums(partial_sums)
    );
    initial begin
        done=0;
        for(t=0;t<TAPS;t=t+1)for(ic=0;ic<CIN;ic=ic+1)begin
            activation=(ACT_UNSIGNED!=0)?(128+((t*3+ic*5)%128)):(((t*3+ic*5)%23)-11);
            window_flat[(t*CIN+ic)*ACT_W+:ACT_W]=activation;
        end
        for(oc=0;oc<COUT;oc=oc+1)for(ic=0;ic<CIN;ic=ic+1)for(t=0;t<TAPS;t=t+1)begin
            weight=((oc*7+ic*3+t)%17)-8;
            weight_flat[((oc*CIN+ic)*TAPS+t)*8+:8]=weight;
        end
        for(p=0;p<8;p=p+1)begin
            phase=p;
            #1;
            group_out=p/(CIN/IN_PAR);
            group_in=p%(CIN/IN_PAR);
            for(o=0;o<OUT_PAR;o=o+1)begin
                oc=group_out*OUT_PAR+o;
                acc=0;
                for(i=0;i<IN_PAR;i=i+1)for(t=0;t<TAPS;t=t+1)begin
                    ic=group_in*IN_PAR+i;
                    activation=(ACT_UNSIGNED!=0)?(128+((t*3+ic*5)%128)):(((t*3+ic*5)%23)-11);
                    weight=((oc*7+ic*3+t)%17)-8;
                    acc=acc+activation*weight;
                end
                if($signed(partial_sums[o*32+:32])!==acc)
                    $fatal(1,"L%0d phase=%0d lane=%0d got=%0d expected=%0d",ID,p,o,$signed(partial_sums[o*32+:32]),acc);
            end
        end
        $display("L%0d phase MAC PASS",ID);
        done=1;
    end
endmodule

module phase_mac_array_tb;
    wire d1,d2,d3,d4,d5;
    phase_mac_case #(.ID(1),.K(5),.CIN(1),.COUT(16),.IN_PAR(1),.OUT_PAR(2),.ACT_W(8),.ACT_UNSIGNED(1)) l1(.done(d1));
    phase_mac_case #(.ID(2),.K(1),.CIN(16),.COUT(8),.IN_PAR(2),.OUT_PAR(8),.ACT_W(16),.ACT_UNSIGNED(0)) l2(.done(d2));
    phase_mac_case #(.ID(3),.K(3),.CIN(8),.COUT(8),.IN_PAR(1),.OUT_PAR(8),.ACT_W(16),.ACT_UNSIGNED(0)) l3(.done(d3));
    phase_mac_case #(.ID(4),.K(1),.CIN(8),.COUT(16),.IN_PAR(1),.OUT_PAR(16),.ACT_W(16),.ACT_UNSIGNED(0)) l4(.done(d4));
    phase_mac_case #(.ID(5),.K(5),.CIN(16),.COUT(4),.IN_PAR(2),.OUT_PAR(4),.ACT_W(16),.ACT_UNSIGNED(0)) l5(.done(d5));
    initial begin
        wait(d1&&d2&&d3&&d4&&d5);
        $display("ACX750_MEMBER_B_PHASE_MAC_PASS layers=5");
        $finish;
    end
endmodule
