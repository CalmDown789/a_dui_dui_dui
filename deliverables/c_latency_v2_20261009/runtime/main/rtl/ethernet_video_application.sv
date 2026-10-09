`timescale 1ns/1ps
`default_nettype none
// Single clock domain application only. Input datagrams must already be fully
// validated and committed by the vendor-derived network/CDC adapter.
module ethernet_video_application #(
    parameter integer INPUT_BYTES=518400,OUTPUT_BYTES=2073600,
    parameter integer RX_IDLE_TIMEOUT_CYCLES=1500000000
)(
    input wire clk,rst_n,
    input wire s_valid,output wire s_ready,input wire [7:0] s_data,
    input wire s_last,input wire [15:0] s_length,input wire [95:0] s_metadata,
    output wire m_valid,input wire m_ready,output wire [7:0] m_data,
    output wire m_last,output wire [15:0] m_length,output wire [95:0] m_metadata,
    output wire frame_wr_en,output wire [18:0] frame_wr_addr,output wire [7:0] frame_wr_data,
    output wire core_start,input wire core_done,
    output wire result_rd_req,input wire result_rd_busy,result_rd_valid,input wire [7:0] result_rd_data,
    output wire frame_locked,output wire [2:0] frame_state,
    output wire [31:0] expected_frame_id,input_bytes_count,output_bytes_count,start_count,release_count,
    output wire [31:0] input_reject_count,output_reject_count
);

    wire lv,lr,ll,legacy_ready,control_input_ready,wv,wr,wl,core_start_i;
    wire[7:0]ld,wd;wire[15:0]ln,wn;wire[95:0]lm,wm;
    wire[127:0]input_session;wire[31:0]input_frame;
    wire legacy_req,window_req,window_release,window_active,window_negotiated;
    wire[31:0]legacy_bytes,legacy_releases,legacy_rejects,window_bytes,window_releases,window_rejects;
    wire cv,cr,pq,pv,dv,dr,pr,prv;wire[1:0]ck;wire[6:0]pi;
    wire[127:0]cs,ds;wire[31:0]cf,cc,ps,pc,df,dseq,doff,dc,dnext,dpc;
    wire[95:0]cm,dm;wire[7:0]cn,cw,dt,pd;wire[9:0]pa;wire[15:0]dst,dflags,dlen;
    wire[31:0]parser_rejects;
    assign s_ready=legacy_ready&&control_input_ready;
    assign core_start=core_start_i;
    assign result_rd_req=window_negotiated?window_req:legacy_req;
    assign output_bytes_count=window_negotiated?window_bytes:legacy_bytes;
    assign release_count=legacy_releases+window_releases;
    assign output_reject_count=legacy_rejects+window_rejects+parser_rejects;
    // Select once per whole packet. Neither serializer can lose its descriptor
    // or have bytes interleaved with the other serializer under backpressure.
    reg transmitting_q,selected_q;
    wire selected=transmitting_q?selected_q:!lv;
    assign m_valid=selected?wv:lv;
    assign m_data=selected?wd:ld;assign m_last=selected?wl:ll;
    assign m_length=selected?wn:ln;assign m_metadata=selected?wm:lm;
    assign lr=m_ready&&!selected;assign wr=m_ready&&selected;
    always @(posedge clk)begin
        if(!rst_n)begin transmitting_q<=0;selected_q<=0;end
        else if(!transmitting_q&&(lv||wv))begin
            selected_q<=!lv;
            transmitting_q<=!(m_valid&&m_ready&&m_last);
        end else if(transmitting_q&&m_valid&&m_ready&&m_last)transmitting_q<=0;
    end
    ethernet_video_application_v1 #(.INPUT_BYTES(INPUT_BYTES),.OUTPUT_BYTES(OUTPUT_BYTES),
        .RX_IDLE_TIMEOUT_CYCLES(RX_IDLE_TIMEOUT_CYCLES)) u_v1(
        .clk(clk),.rst_n(rst_n),.s_valid(s_valid&&control_input_ready),.s_ready(legacy_ready),
        .s_data(s_data),.s_last(s_last),.s_length(s_length),.s_metadata(s_metadata),
        .m_valid(lv),.m_ready(lr),.m_data(ld),.m_last(ll),.m_length(ln),.m_metadata(lm),
        .frame_wr_en(frame_wr_en),.frame_wr_addr(frame_wr_addr),.frame_wr_data(frame_wr_data),
        .core_start(core_start_i),.core_done(core_done),.result_rd_req(legacy_req),
        .result_rd_busy(result_rd_busy&&!window_negotiated),.result_rd_valid(result_rd_valid&&!window_negotiated),
        .result_rd_data(result_rd_data),.frame_locked(frame_locked),.frame_state(frame_state),
        .expected_frame_id(expected_frame_id),.input_bytes_count(input_bytes_count),.output_bytes_count(legacy_bytes),
        .start_count(start_count),.release_count(legacy_releases),.input_reject_count(input_reject_count),
        .output_reject_count(legacy_rejects),.external_owner(window_negotiated),.external_release(window_release),
        .input_session(input_session),.input_frame(input_frame));
    evf2_control_parser #(.OUTPUT_BYTES(OUTPUT_BYTES)) u_window_parser(
        .clk(clk),.rst_n(rst_n),.s_valid(s_valid&&legacy_ready),.s_ready(control_input_ready),
        .s_data(s_data),.s_last(s_last),.s_length(s_length),.s_metadata(s_metadata),
        .control_valid(cv),.control_ready(cr),.control_kind(ck),.control_session(cs),.control_frame(cf),
        .control_crc(cc),.control_metadata(cm),.control_count(cn),.control_window(cw),
        .proof_req(pq),.proof_index(pi),.proof_valid(pv),.proof_sequence(ps),.proof_crc(pc),
        .rejected_count(parser_rejects),.timeout_count());
    evf2_result_window #(.OUTPUT_BYTES(OUTPUT_BYTES)) u_window(
        .clk(clk),.rst_n(rst_n),.frame_start(core_start_i&&window_negotiated),.frame_session(input_session),
        .frame_id(input_frame),.core_done(core_done),.rd_req(window_req),
        .rd_busy(result_rd_busy&&window_negotiated),.rd_valid(result_rd_valid&&window_negotiated),.rd_data(result_rd_data),
        .control_valid(cv),.control_ready(cr),.control_kind(ck),.control_session(cs),.control_frame(cf),.control_crc(cc),
        .control_metadata(cm),.control_count(cn),.control_window(cw),.proof_req(pq),.proof_index(pi),
        .proof_valid(pv),.proof_sequence(ps),.proof_crc(pc),.desc_valid(dv),.desc_ready(dr),.desc_type(dt),
        .desc_status(dst),.desc_flags(dflags),.desc_length(dlen),.desc_session(ds),.desc_frame_id(df),
        .desc_sequence(dseq),.desc_offset(doff),.desc_frame_crc(dc),.desc_next_offset(dnext),.desc_payload_crc(dpc),
        .desc_metadata(dm),.payload_rd_req(pr),.payload_rd_addr(pa),.payload_rd_valid(prv),.payload_rd_data(pd),
        .frame_release(window_release),.active(window_active),.negotiated(window_negotiated),
        .read_bytes_count(window_bytes),.release_count(window_releases),.rejected_count(window_rejects),
        .retransmitted_count(),.window_base(),.window_next());
    evf2_response_serializer u_window_serializer(
        .clk(clk),.rst_n(rst_n),.desc_valid(dv),.desc_ready(dr),.busy(),.desc_type(dt),.desc_status(dst),
        .desc_flags(dflags),.desc_length(dlen),.desc_session(ds),.desc_frame_id(df),.desc_sequence(dseq),.desc_offset(doff),
        .desc_frame_bytes(OUTPUT_BYTES),.desc_frame_crc(dc),.desc_next_offset(dnext),.desc_payload_crc(dpc),.desc_metadata(dm),
        .payload_rd_req(pr),.payload_rd_addr(pa),.payload_rd_valid(prv),.payload_rd_data(pd),
        .m_valid(wv),.m_ready(wr),.m_data(wd),.m_last(wl),.m_length(wn),.m_metadata(wm));
endmodule
`timescale 1ns/1ps
`default_nettype none
// Single clock domain application only. Input datagrams must already be fully
// validated and committed by the vendor-derived network/CDC adapter.
module ethernet_video_application_v1 #(
    parameter integer INPUT_BYTES=518400,OUTPUT_BYTES=2073600,
    parameter integer RX_IDLE_TIMEOUT_CYCLES=1500000000
)(
    input wire external_owner,external_release,
    output wire[127:0]input_session,output wire[31:0]input_frame,
    input wire clk,rst_n,
    input wire s_valid,output wire s_ready,input wire [7:0] s_data,
    input wire s_last,input wire [15:0] s_length,input wire [95:0] s_metadata,
    output wire m_valid,input wire m_ready,output wire [7:0] m_data,
    output wire m_last,output wire [15:0] m_length,output wire [95:0] m_metadata,
    output wire frame_wr_en,output wire [18:0] frame_wr_addr,output wire [7:0] frame_wr_data,
    output wire core_start,input wire core_done,
    output wire result_rd_req,input wire result_rd_busy,result_rd_valid,input wire [7:0] result_rd_data,
    output wire frame_locked,output wire [2:0] frame_state,
    output wire [31:0] expected_frame_id,input_bytes_count,output_bytes_count,start_count,release_count,
    output wire [31:0] input_reject_count,output_reject_count
);
    wire ir_ready,or_ready,iv,ov,ia,oa,serializer_busy;
    wire [7:0] it,ot;
    wire [15:0] ist,ost,oflags,olen;
    wire [127:0] isid,osid;
    wire [31:0] ifid,iseq,ioff,icrc,inext,ofid,oseq,ooff,ocrc,onext,opcrc;
    wire [95:0] imeta,ometa;
    assign input_session=isid;assign input_frame=ifid;
    wire payload_req,payload_valid,release_frame;
    wire [9:0] payload_addr;wire [7:0] payload_data;
    reg selected_output_q;
    wire select_output=serializer_busy?selected_output_q:!iv;
    wire desc_ready;
    assign s_ready=ir_ready&&or_ready;
    assign ia=desc_ready&&!select_output;
    assign oa=desc_ready&&select_output;
    always @(posedge clk)
        if(!rst_n)selected_output_q<=0;
        else if(!serializer_busy&&(iv||ov))selected_output_q<=!iv;
    ethernet_frame_rx #(.FRAME_BYTES(INPUT_BYTES),.OUTPUT_CONTROLLER_PRESENT(1),
        .RX_IDLE_TIMEOUT_CYCLES(RX_IDLE_TIMEOUT_CYCLES)) u_input(
        .clk(clk),.rst_n(rst_n),.s_valid(s_valid&&or_ready),.s_ready(ir_ready),.s_data(s_data),.s_last(s_last),
        .s_length(s_length),.s_metadata(s_metadata),.response_valid(iv),.response_ready(ia),
        .response_type(it),.response_status(ist),.response_session(isid),.response_frame_id(ifid),
        .response_sequence(iseq),.response_offset(ioff),.response_frame_crc(icrc),.response_next_offset(inext),.response_metadata(imeta),
        .frame_wr_en(frame_wr_en),.frame_wr_addr(frame_wr_addr),.frame_wr_data(frame_wr_data),
        .core_start(core_start),.frame_release(release_frame||external_release),.frame_locked(frame_locked),.frame_state(frame_state),
        .expected_frame_id(expected_frame_id),.next_offset(),.start_count(start_count),.written_bytes_count(input_bytes_count),
        .rejected_count(input_reject_count),.receive_timeout_count(),.packet_timeout_count());
    ethernet_result_tx #(.OUTPUT_BYTES(OUTPUT_BYTES)) u_result(
        .clk(clk),.rst_n(rst_n),.frame_start(core_start&&!external_owner),.frame_session(isid),.frame_id(ifid),.core_done(core_done),
        .rd_req(result_rd_req),.rd_busy(result_rd_busy),.rd_valid(result_rd_valid),.rd_data(result_rd_data),
        .s_valid(s_valid&&ir_ready),.s_ready(or_ready),.s_data(s_data),.s_last(s_last),.s_length(s_length),.s_metadata(s_metadata),
        .response_valid(ov),.response_ready(oa),.response_type(ot),.response_status(ost),.response_flags(oflags),.response_length(olen),
        .response_session(osid),.response_frame_id(ofid),.response_sequence(oseq),.response_offset(ooff),.response_frame_crc(ocrc),
        .response_next_offset(onext),.response_payload_crc(opcrc),.response_metadata(ometa),
        .payload_rd_req(payload_req),.payload_rd_addr(payload_addr),.payload_rd_valid(payload_valid),.payload_rd_data(payload_data),
        .frame_release(release_frame),.read_bytes_count(output_bytes_count),.release_count(release_count),.rejected_count(output_reject_count),
        .result_active(),.result_ready());
    evf_response_serializer u_serialize(
        .clk(clk),.rst_n(rst_n),.desc_valid(iv||ov),.desc_ready(desc_ready),.busy(serializer_busy),
        .desc_type(select_output?ot:it),.desc_status(select_output?ost:ist),.desc_flags(select_output?oflags:16'd0),
        .desc_length(select_output?olen:16'd0),.desc_session(select_output?osid:isid),.desc_frame_id(select_output?ofid:ifid),
        .desc_sequence(select_output?oseq:iseq),.desc_offset(select_output?ooff:ioff),.desc_frame_bytes(select_output?OUTPUT_BYTES:INPUT_BYTES),
        .desc_frame_crc(select_output?ocrc:icrc),.desc_next_offset(select_output?onext:inext),.desc_payload_crc(select_output?opcrc:32'd0),
        .desc_metadata(select_output?ometa:imeta),.payload_rd_req(payload_req),.payload_rd_addr(payload_addr),
        .payload_rd_valid(payload_valid),.payload_rd_data(payload_data),
        .m_valid(m_valid),.m_ready(m_ready),.m_data(m_data),.m_last(m_last),.m_length(m_length),.m_metadata(m_metadata));
endmodule
`default_nettype wire
