`timescale 1ns / 1ps

module window5x5_bram #(
    parameter integer DATA_W = 16,
    parameter integer IMG_W  = 960
)(
    input  wire                       clk,
    input  wire                       rst,
    input  wire [DATA_W-1:0]          pixel_in,
    input  wire                       pixel_valid,
    output wire [(25*DATA_W)-1:0]     window_flat,
    output reg                        window_valid
);

    localparam integer COL_W=(IMG_W<=1)?1:$clog2(IMG_W);
    (* ram_style="block" *) reg [DATA_W-1:0] bank0[0:IMG_W-1];
    (* ram_style="block" *) reg [DATA_W-1:0] bank1[0:IMG_W-1];
    (* ram_style="block" *) reg [DATA_W-1:0] bank2[0:IMG_W-1];
    (* ram_style="block" *) reg [DATA_W-1:0] bank3[0:IMG_W-1];
    (* ram_style="block" *) reg [DATA_W-1:0] bank4[0:IMG_W-1];

    reg [COL_W-1:0] col_count,col_d;
    reg [15:0] row_count,row_d;
    reg [2:0] row_mod5,row_mod5_d;
    reg [DATA_W-1:0] q0,q1,q2,q3,q4,pixel_d;
    reg read_valid_d;
    reg [DATA_W-1:0] prev1,prev2,prev3,prev4;
    reg [DATA_W-1:0] shifts[0:24];

    genvar tap;
    generate
        for(tap=0;tap<25;tap=tap+1) begin:g_flat
            assign window_flat[(tap*DATA_W)+:DATA_W]=shifts[tap];
        end
    endgenerate

    initial begin
        if(DATA_W<1)$error("DATA_W must be at least 1");
        if(IMG_W<5)$error("IMG_W must be at least 5 for a 5x5 window");
    end

    always @* begin
        case(row_mod5_d)
            3'd0: begin prev1=q4;prev2=q3;prev3=q2;prev4=q1;end
            3'd1: begin prev1=q0;prev2=q4;prev3=q3;prev4=q2;end
            3'd2: begin prev1=q1;prev2=q0;prev3=q4;prev4=q3;end
            3'd3: begin prev1=q2;prev2=q1;prev3=q0;prev4=q4;end
            default: begin prev1=q3;prev2=q2;prev3=q1;prev4=q0;end
        endcase
    end

    always @(posedge clk) begin
        if(rst) begin
            col_count<=0;row_count<=0;row_mod5<=0;
            col_d<=0;row_d<=0;row_mod5_d<=0;pixel_d<=0;
            q0<=0;q1<=0;q2<=0;q3<=0;q4<=0;read_valid_d<=0;
        end else begin
            read_valid_d<=pixel_valid;
            if(pixel_valid) begin
                q0<=bank0[col_count];q1<=bank1[col_count];
                q2<=bank2[col_count];q3<=bank3[col_count];q4<=bank4[col_count];
                col_d<=col_count;row_d<=row_count;row_mod5_d<=row_mod5;pixel_d<=pixel_in;
                case(row_mod5)
                    3'd0:bank0[col_count]<=pixel_in;
                    3'd1:bank1[col_count]<=pixel_in;
                    3'd2:bank2[col_count]<=pixel_in;
                    3'd3:bank3[col_count]<=pixel_in;
                    default:bank4[col_count]<=pixel_in;
                endcase
                if(col_count==IMG_W-1) begin
                    col_count<=0;row_count<=row_count+1'b1;
                    row_mod5<=(row_mod5==4)?0:row_mod5+1'b1;
                end else col_count<=col_count+1'b1;
            end
        end
    end

    integer i,row;
    always @(posedge clk) begin
        if(rst) begin
            for(i=0;i<25;i=i+1)shifts[i]<=0;
            window_valid<=0;
        end else begin
            window_valid<=0;
            if(read_valid_d) begin
                if(col_d==0) begin
                    for(row=0;row<5;row=row+1) begin
                        shifts[row*5+0]<=0;shifts[row*5+1]<=0;
                        shifts[row*5+2]<=0;shifts[row*5+3]<=0;
                    end
                end else begin
                    for(row=0;row<5;row=row+1) begin
                        shifts[row*5+0]<=shifts[row*5+1];
                        shifts[row*5+1]<=shifts[row*5+2];
                        shifts[row*5+2]<=shifts[row*5+3];
                        shifts[row*5+3]<=shifts[row*5+4];
                    end
                end
                shifts[4]<=prev4;shifts[9]<=prev3;shifts[14]<=prev2;
                shifts[19]<=prev1;shifts[24]<=pixel_d;
                window_valid<=(row_d>=4)&&(col_d>=4);
            end
        end
    end
endmodule
