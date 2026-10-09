`timescale 1ns/1ps
`default_nettype none
// Frozen B and C data path + Ethernet application. Only normalized packet ports
// are exposed here. Physical MAC/PHY/CDC and board constraints are separate.
module ethernet_sr_pipeline #(
    parameter integer IMG_W=960,IMG_H=540,STRIPE_H=64,
    parameter integer ROM_DEPTH=524288
)(
    input wire clk,rst_n,
    input wire s_valid,output wire s_ready,input wire [7:0] s_data,
    input wire s_last,input wire [15:0] s_length,input wire [95:0] s_metadata,
    output wire m_valid,input wire m_ready,output wire [7:0] m_data,
    output wire m_last,output wire [15:0] m_length,output wire [95:0] m_metadata,
    output wire [31:0] input_bytes_count,output_bytes_count,start_count,release_count,
    output wire [31:0] expected_frame_id,input_reject_count,output_reject_count,
    output wire frame_locked,core_busy,core_done,
    output wire proto_error,overflow_error,
    output wire [15:0] stripe_count
);
    wire frame_wr_en,core_start,rdreq,rdbusy,rdvalid;wire [7:0] frame_data,rddata;wire [18:0]frame_addr;
    ethernet_video_application #(.INPUT_BYTES(IMG_W*IMG_H),.OUTPUT_BYTES(IMG_W*IMG_H*4))u_application(
        .clk(clk),.rst_n(rst_n),.s_valid(s_valid),.s_ready(s_ready),.s_data(s_data),.s_last(s_last),.s_length(s_length),.s_metadata(s_metadata),
        .m_valid(m_valid),.m_ready(m_ready),.m_data(m_data),.m_last(m_last),.m_length(m_length),.m_metadata(m_metadata),
        .frame_wr_en(frame_wr_en),.frame_wr_addr(frame_addr),.frame_wr_data(frame_data),.core_start(core_start),.core_done(core_done),
        .result_rd_req(rdreq),.result_rd_busy(rdbusy),.result_rd_valid(rdvalid),.result_rd_data(rddata),
        .frame_locked(frame_locked),.frame_state(),.expected_frame_id(expected_frame_id),
        .input_bytes_count(input_bytes_count),.output_bytes_count(output_bytes_count),.start_count(start_count),.release_count(release_count),
        .input_reject_count(input_reject_count),.output_reject_count(output_reject_count));
    c_ethernet_core #(.IMG_W(IMG_W),.IMG_H(IMG_H),.OUT_W(IMG_W*2),.OUT_H(IMG_H*2),.STRIPE_H(STRIPE_H),
        .ROM_ADDR_W(19),.ROM_DEPTH(ROM_DEPTH),.ROM_INIT_EN(0),.ROM_INIT_MODE(0),.CLK_HZ(150000000),.OBS_TEST_PAUSE_ENABLE(0))u_core(
        .clk(clk),.rst_n(rst_n),.start(core_start),.busy(core_busy),.done(core_done),.rb_enable(1'b0),.uart_tx(),
        .net_rd_req(rdreq),.net_rd_busy(rdbusy),.net_rd_valid(rdvalid),.net_rd_data(rddata),
        .frame_wr_en(frame_wr_en),.frame_wr_addr(frame_addr),.frame_wr_data(frame_data),.obs_pause_req(1'b0),
        .dbg_proto_err(proto_error),.dbg_overflow_err(overflow_error),.dbg_stripe_cnt(stripe_count),
        .dbg_buf_state(),.dbg_uart_bytes(),.dbg_stripes_sent(),.dbg_in_done(),.dbg_b_busy(),.dbg_b_done_seen(),
        .dbg_uart_tx_busy(),.dbg_readback_busy(),.dbg_in_x(),.dbg_in_y(),.dbg_out_x(),.dbg_out_y(),
        .dbg_obs_c2b_valid(),.dbg_obs_c2b_ready(),.dbg_obs_c2b_data(),.dbg_obs_b_out_valid(),.dbg_obs_b_out_data(),
        .dbg_obs_b_out_ready(),.dbg_obs_b_stripe_last(),.dbg_obs_b_frame_last(),.dbg_obs_pause_effective(),.dbg_obs_pause_forced_block());
endmodule
`default_nettype wire
