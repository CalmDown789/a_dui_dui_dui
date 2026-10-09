`timescale 1ns/1ps
`default_nettype none
// Separate EVF2 wire version. Only committed UDP payloads enter this parser.
// All header/payload CRC and envelope checks precede publication of control.
module evf2_control_parser #(
    parameter integer OUTPUT_BYTES=2073600,MAX_WINDOW=128,GAP_TIMEOUT=1024
)(
    input wire clk,rst_n,input wire s_valid,output wire s_ready,input wire[7:0]s_data,
    input wire s_last,input wire[15:0]s_length,input wire[95:0]s_metadata,
    output wire control_valid,input wire control_ready,output reg[1:0]control_kind,
    output reg[127:0]control_session,output reg[31:0]control_frame,control_crc,
    output reg[95:0]control_metadata,output reg[7:0]control_count,control_window,
    input wire proof_req,input wire[6:0]proof_index,
    output reg proof_valid,output reg[31:0]proof_sequence,proof_crc,
    output reg[31:0]rejected_count,timeout_count
);
    localparam CAPTURE=0,VERIFY=1,HOLD=2;
    reg[1:0]state_q;reg[511:0]header_q;
    reg[31:0]hcrc_q,pcrc_q,gap_q;reg[15:0]count_q,length_q;reg bad_q;
    reg[95:0]metadata_q;reg[63:0]proof_shift_q;
    (* ram_style="distributed" *)reg[63:0]proof_mem[0:127];
    wire take=s_valid&&s_ready;
    assign s_ready=rst_n&&state_q==CAPTURE;
    assign control_valid=rst_n&&state_q==HOLD;
    wire[7:0]ht=header_q[471:464];wire[15:0]hl=header_q[159:144];
    function automatic[31:0]crc_byte(input[31:0]c,input[7:0]d);
        reg[31:0]v;integer k;
        begin v=c^{24'd0,d};for(k=0;k<8;k=k+1)v=v[0]?((v>>1)^32'hedb88320):(v>>1);crc_byte=v;end
    endfunction
    task clear_capture;
        begin header_q<=0;hcrc_q<=32'hffffffff;pcrc_q<=32'hffffffff;gap_q<=0;
            count_q<=0;length_q<=0;bad_q<=0;proof_shift_q<=0;end
    endtask
    task reject_packet;
        begin rejected_count<=rejected_count+1;state_q<=CAPTURE;clear_capture();end
    endtask
    always @(posedge clk)begin
        if(rst_n&&take&&count_q>=64&&count_q<1088)begin
            if(count_q[2:0]==7)proof_mem[(count_q-64)>>3]<={proof_shift_q[55:0],s_data};
        end
        if(proof_req)begin {proof_sequence,proof_crc}<=proof_mem[proof_index];end
        proof_valid<=rst_n&&proof_req;
    end
    always @(posedge clk)begin
        if(!rst_n)begin
            state_q<=CAPTURE;clear_capture();metadata_q<=0;rejected_count<=0;timeout_count<=0;
            control_kind<=0;control_session<=0;control_frame<=0;control_crc<=0;
            control_metadata<=0;control_count<=0;control_window<=0;
        end else case(state_q)
            CAPTURE:if(take)begin
                gap_q<=0;
                if(count_q==0)begin length_q<=s_length;metadata_q<=s_metadata;end
                else if(s_length!=length_q||s_metadata!=metadata_q)bad_q<=1;
                if(count_q<64)header_q<={header_q[503:0],s_data};
                if(count_q<60)hcrc_q<=crc_byte(hcrc_q,s_data);
                if(count_q>=64)pcrc_q<=crc_byte(pcrc_q,s_data);
                if(count_q>=64&&count_q<1088)proof_shift_q<={proof_shift_q[55:0],s_data};
                if(count_q>=1088||count_q==16'hffff)bad_q<=1;
                if(count_q!=16'hffff)count_q<=count_q+1'b1;
                if(s_last)state_q<=VERIFY;
            end else if(count_q!=0)begin
                if(gap_q==GAP_TIMEOUT-1)begin timeout_count<=timeout_count+1;reject_packet();end
                else gap_q<=gap_q+1'b1;
            end
            VERIFY:begin
                // A valid EVF1 packet belongs to the unchanged legacy path.
                if(!bad_q&&count_q>=64&&count_q==length_q&&count_q==64+hl&&
                    header_q[511:480]==32'h45564631&&header_q[479:472]==1&&
                    ~hcrc_q==header_q[31:0]&&~pcrc_q==header_q[63:32])begin state_q<=CAPTURE;clear_capture();end
                else if(bad_q||count_q<64||count_q!=length_q||count_q!=64+hl||
                    header_q[511:480]!=32'h45564632||header_q[479:472]!=2||
                    ~hcrc_q!=header_q[31:0]||~pcrc_q!=header_q[63:32]||
                    header_q[463:448]!=0||header_q[95:64]!=0||header_q[223:192]!=OUTPUT_BYTES)reject_packet();
                else if(ht==1)begin
                    if(hl!=8||header_q[319:224]!=0||header_q[191:160]!=0||header_q[143:96]!=0||
                        proof_shift_q[63:48]!=1024||proof_shift_q[47:32]<1||proof_shift_q[47:32]>MAX_WINDOW||
                        proof_shift_q[31:0]!=32'h17000000)reject_packet();
                    else begin control_kind<=1;control_window<=proof_shift_q[39:32];state_q<=HOLD;end
                end else if(ht==8'h97)begin
                    if(hl==0||hl[2:0]!=0||hl>MAX_WINDOW*8||header_q[287:224]!=0||
                        header_q[191:160]!=0||header_q[143:128]!=1)reject_packet();
                    else begin control_kind<=2;control_count<=hl>>3;state_q<=HOLD;end
                end else if(ht==9)begin
                    if(hl!=0||header_q[287:256]!=(OUTPUT_BYTES+1023)/1024||
                        header_q[255:224]!=OUTPUT_BYTES||header_q[143:96]!=0)reject_packet();
                    else begin control_kind<=3;state_q<=HOLD;end
                end else reject_packet();
                control_session<=header_q[447:320];control_frame<=header_q[319:288];
                control_crc<=header_q[191:160];control_metadata<=metadata_q;
            end
            HOLD:if(control_ready)begin state_q<=CAPTURE;clear_capture();end
            default:begin state_q<=CAPTURE;clear_capture();end
        endcase
    end
endmodule
`default_nettype wire
