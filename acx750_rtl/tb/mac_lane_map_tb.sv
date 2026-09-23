`timescale 1ns / 1ps

// 成员B工作 / Team member B: exhaustive five-layer OIHW mapping coverage.
module lane_map_case #(
    parameter integer ID=1,K=5,CIN=1,COUT=16,IN_PAR=1,OUT_PAR=2
)(output reg done);
    localparam integer LANES=K*K*IN_PAR*OUT_PAR;
    localparam integer TOTAL=K*K*CIN*COUT;
    reg [2:0] phase=0;
    wire [7:0] out_ch[0:LANES-1];
    wire [7:0] in_ch[0:LANES-1];
    wire [5:0] tap[0:LANES-1];
    wire [31:0] address[0:LANES-1];
    bit seen[0:TOTAL-1];
    integer p,l,a,count;
    genvar g;
    generate for(g=0;g<LANES;g=g+1)begin:lanes
        mac_lane_map #(.K(K),.CIN(CIN),.COUT(COUT),.IN_PAR(IN_PAR),.OUT_PAR(OUT_PAR),.LANE(g)) dut (
            .phase(phase),.out_channel(out_ch[g]),.in_channel(in_ch[g]),
            .tap_index(tap[g]),.weight_oihw_address(address[g])
        );
    end endgenerate
    initial begin
        done=0;count=0;
        for(a=0;a<TOTAL;a=a+1)seen[a]=0;
        for(p=0;p<8;p=p+1)begin
            phase=p;
            #1;
            for(l=0;l<LANES;l=l+1)begin
                a=address[l];
                if(out_ch[l]>=COUT||in_ch[l]>=CIN||tap[l]>=K*K||a>=TOTAL)
                    $fatal(1,"L%0d invalid phase=%0d lane=%0d",ID,p,l);
                if(a!=((out_ch[l]*CIN+in_ch[l])*K*K+tap[l]))
                    $fatal(1,"L%0d OIHW address mismatch",ID);
                if(seen[a])$fatal(1,"L%0d duplicate address=%0d",ID,a);
                seen[a]=1;count=count+1;
            end
        end
        for(a=0;a<TOTAL;a=a+1)if(!seen[a])$fatal(1,"L%0d missing address=%0d",ID,a);
        if(count!=TOTAL)$fatal(1,"L%0d count=%0d expected=%0d",ID,count,TOTAL);
        $display("L%0d map PASS lanes=%0d MAC=%0d",ID,LANES,count);
        done=1;
    end
endmodule

module mac_lane_map_tb;
    wire d1,d2,d3,d4,d5;
    lane_map_case #(.ID(1),.K(5),.CIN(1),.COUT(16),.IN_PAR(1),.OUT_PAR(2)) l1(.done(d1));
    lane_map_case #(.ID(2),.K(1),.CIN(16),.COUT(8),.IN_PAR(2),.OUT_PAR(8)) l2(.done(d2));
    lane_map_case #(.ID(3),.K(3),.CIN(8),.COUT(8),.IN_PAR(1),.OUT_PAR(8)) l3(.done(d3));
    lane_map_case #(.ID(4),.K(1),.CIN(8),.COUT(16),.IN_PAR(1),.OUT_PAR(16)) l4(.done(d4));
    lane_map_case #(.ID(5),.K(5),.CIN(16),.COUT(4),.IN_PAR(2),.OUT_PAR(4)) l5(.done(d5));
    initial begin
        wait(d1&&d2&&d3&&d4&&d5);
        $display("ACX750_MEMBER_B_LANE_MAP_PASS total_mac_per_pixel=2832 lanes=354");
        $finish;
    end
endmodule
