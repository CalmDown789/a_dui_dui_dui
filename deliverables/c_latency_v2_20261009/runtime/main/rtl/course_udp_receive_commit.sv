`timescale 1ns/1ps
`default_nettype none
module course_udp_receive_commit(
    input wire clk125,rst_n,input wire gmii_rxdv,gmii_rxerr,input wire[7:0]gmii_rxd,
    output wire m_valid,input wire m_ready,output wire[7:0]m_data,output wire m_last,
    output wire[15:0]m_length,output wire[95:0]m_metadata,
    output wire[31:0]committed,rejected,timeouts
);
    wire rclk,rv,done,error,begin_ready;
    wire[7:0]rdata;wire[15:0]rlen,rport;wire[47:0]rmac;wire[31:0]rip;
    reg previous_valid_q;
    always @(posedge clk125 or negedge rst_n)if(!rst_n)previous_valid_q<=0;else previous_valid_q<=rv;
    wire first=rv&&!previous_valid_q;
    course_eth_udp_rx_checked u_rx(
        .reset_p(!rst_n),.local_mac(48'h000a3501fec0),.local_ip(32'hc0a80002),.local_port(16'd5000),
        .clk125m_o(rclk),.exter_mac(rmac),.exter_ip(rip),.exter_port(rport),.rx_data_length(rlen),
        .data_overflow_i(first&&!begin_ready),.payload_valid_o(rv),.payload_dat_o(rdata),
        .one_pkt_done(done),.pkt_error(error),.debug_crc_check(),
        .gmii_rx_clk(clk125),.gmii_rxdv(gmii_rxdv),.gmii_rxerr(gmii_rxerr),.gmii_rxd(gmii_rxd));
    udp_packet_commit_buffer #(.MAX_BYTES(1088),.META_WIDTH(96),.GOOD_FLAG_WIDTH(1),.TIMEOUT_CYCLES(2048))u_commit(
        .clk(clk125),.rst_n(rst_n),.rx_begin(first),.rx_declared_len(rlen),.rx_metadata({rmac,rip,rport}),
        .rx_data_valid(rv),.rx_data(rdata),.rx_end(done),.rx_good_flags(!error),.rx_begin_ready(begin_ready),.rx_busy(),
        .out_valid(m_valid),.out_ready(m_ready),.out_data(m_data),.out_last(m_last),.out_length(m_length),.out_metadata(m_metadata),
        .committed_count(committed),.rejected_event_count(rejected),.timeout_count(timeouts),.last_reject_reason());
endmodule
`default_nettype wire
