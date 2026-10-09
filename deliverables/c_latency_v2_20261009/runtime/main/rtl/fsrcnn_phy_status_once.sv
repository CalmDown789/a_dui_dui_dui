`timescale 1ns/1ps
`default_nettype none
// Snapshot ONE 32-byte terminal diagnostic packet and replay the cached bytes
// every two seconds using a standard valid/ready byte stream. No MDIO commands.
// Set REPLAY_INTERVAL_CYCLES=0 for one transmission only. Connect to the parent's
// existing UART transmitter/arbiter.
// UART configuration and packet exclusivity are the parent's responsibility.
// This reset is the same dedicated configuration reset, never video S0.
module fsrcnn_phy_status_once #(
    parameter integer REPLAY_INTERVAL_CYCLES=100000000
)(
    input wire clk_50, cfg_rst_n, cfg_done, cfg_ok, cfg_failed,
    input wire identity_ok, page_saved, tx_write_attempted, restore_verified,
    input wire [7:0] failure_code, restore_failure_code, diag_valid, diag_state,
    input wire [1:0] restore_attempts,
    input wire [15:0] id2,id3,tx_old,tx_actual,rx_old,rx_actual,original_page,restored_page,
    output wire byte_valid,
    output wire [7:0] byte_data,
    input wire byte_ready,
    output reg packet_sent,
    output reg frame_done
);
    reg [1:0] state_q;
    reg [5:0] index_q;
    reg [7:0] payload_q [0:29];
    reg [15:0] crc_q;
    reg [31:0] replay_count_q;
    integer j;
    assign byte_valid=(state_q==2);
    assign byte_data=(index_q<30) ? payload_q[index_q] :
                     ((index_q==30) ? crc_q[7:0] : crc_q[15:8]);
    function automatic [15:0] crc16_byte(input [15:0] crc, input [7:0] datum);
        reg [15:0] c;
        integer i;
        begin
            c=crc ^ {datum,8'h00};
            for(i=0;i<8;i=i+1) c=c[15] ? ((c<<1)^16'h1021) : (c<<1);
            crc16_byte=c;
        end
    endfunction
    always @(posedge clk_50 or negedge cfg_rst_n) begin
        if(!cfg_rst_n) begin
            state_q<=0; index_q<=0; crc_q<=16'hffff; packet_sent<=0;
            frame_done<=0; replay_count_q<=0;
            for(j=0;j<30;j=j+1) payload_q[j]<=0;
        end else begin
            frame_done<=0;
            case(state_q)
                0: if(cfg_done) begin
                    payload_q[0]<=8'h50; payload_q[1]<=8'h48;
                    payload_q[2]<=8'h59; payload_q[3]<=8'h30; // PHY0
                    payload_q[4]<=1; payload_q[5]<=32;
                    payload_q[6]<={1'b0,cfg_done,restore_verified,tx_write_attempted,
                                  page_saved,identity_ok,cfg_failed,cfg_ok};
                    payload_q[7]<=failure_code; payload_q[8]<=restore_failure_code;
                    payload_q[9]<={6'b0,restore_attempts}; payload_q[10]<=5;
                    payload_q[11]<=diag_valid;
                    payload_q[12]<=id2[7:0]; payload_q[13]<=id2[15:8];
                    payload_q[14]<=id3[7:0]; payload_q[15]<=id3[15:8];
                    payload_q[16]<=tx_old[7:0]; payload_q[17]<=tx_old[15:8];
                    payload_q[18]<=tx_actual[7:0]; payload_q[19]<=tx_actual[15:8];
                    payload_q[20]<=rx_old[7:0]; payload_q[21]<=rx_old[15:8];
                    payload_q[22]<=rx_actual[7:0]; payload_q[23]<=rx_actual[15:8];
                    payload_q[24]<=original_page[7:0]; payload_q[25]<=original_page[15:8];
                    payload_q[26]<=restored_page[7:0]; payload_q[27]<=restored_page[15:8];
                    payload_q[28]<=diag_state; payload_q[29]<=0;
                    state_q<=1; index_q<=0; crc_q<=16'hffff;
                end
                1: begin
                    crc_q<=crc16_byte(crc_q,payload_q[index_q]);
                    if(index_q==29) begin index_q<=0; state_q<=2; end
                    else index_q<=index_q+1'b1;
                end
                2: if(byte_ready) begin
                    if(index_q==31) begin state_q<=3; packet_sent<=1;
                        frame_done<=1; replay_count_q<=0; end
                    else index_q<=index_q+1'b1;
                end
                3: if(REPLAY_INTERVAL_CYCLES!=0) begin
                    if(replay_count_q==REPLAY_INTERVAL_CYCLES-1) begin
                        replay_count_q<=0; index_q<=0; state_q<=2;
                    end else replay_count_q<=replay_count_q+1'b1;
                end
                default: state_q<=3;
            endcase
        end
    end
endmodule
`default_nettype wire
