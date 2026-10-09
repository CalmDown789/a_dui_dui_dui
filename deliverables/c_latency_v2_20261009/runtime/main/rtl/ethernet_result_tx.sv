`timescale 1ns/1ps
`default_nettype none
// Output owner for the frozen C ping-pong read port. Only one packet is retained.
// No PHY/MAC or SR calculation is implemented here. A complete PC frame ACK,
// all expected bytes and seen core_done are required before frame_release.
module ethernet_result_tx #(
    parameter integer OUTPUT_BYTES=2073600,
    parameter integer CHUNK_BYTES=1024,
    parameter integer PACKET_GAP_TIMEOUT_CYCLES=1024
)(
    input wire clk, rst_n,
    input wire frame_start, input wire [127:0] frame_session, input wire [31:0] frame_id,
    input wire core_done,
    output wire rd_req, input wire rd_busy, rd_valid, input wire [7:0] rd_data,
    input wire s_valid, output wire s_ready, input wire [7:0] s_data,
    input wire s_last, input wire [15:0] s_length, input wire [95:0] s_metadata,
    output wire response_valid, input wire response_ready,
    output reg [7:0] response_type,
    output reg [15:0] response_status, response_flags, response_length,
    output reg [127:0] response_session,
    output reg [31:0] response_frame_id, response_sequence, response_offset,
    output reg [31:0] response_frame_crc, response_next_offset, response_payload_crc,
    output reg [95:0] response_metadata,
    input wire payload_rd_req, input wire [9:0] payload_rd_addr,
    output reg payload_rd_valid, output reg [7:0] payload_rd_data,
    output reg frame_release,
    output reg [31:0] read_bytes_count, release_count, rejected_count,
    output wire result_active, result_ready
);
    localparam CAPTURE=0, VERIFY=1, REPLY=2;
    localparam [15:0] ACK=1, FRAME_DONE=4, E_SESSION=16, E_FRAME_ID=17,
        E_PAYLOAD_CRC=18, E_LENGTH=19, E_OFFSET=20, E_FRAME_CRC=21, E_FLAGS=22, NOT_READY=24;
    reg [1:0] parser_q;
    reg [511:0] header_q;
    reg [31:0] small_payload_q, header_crc_q, payload_crc_q, gap_q;
    reg [15:0] count_q, length_q; reg bad_length_q;
    reg [95:0] metadata_q;
    reg active_q, done_seen_q, buffer_ready_q, final_acked_q;
    // Up to four accepted reads remain reserved until byte commit.
    reg [2:0] read_pending_q;
    // Isolate the large frozen ping-pong BRAM read mux from the byte CRC logic.
    // A separate request stage and data stage preserve the timing cuts.
    reg read_update_q;
    reg [7:0] read_byte_q;
    reg read_request_q;
    reg [127:0] session_q, done_session_q;
    reg [31:0] frame_q, offset_q, sequence_q, rolling_crc_q, chunk_crc_q;
    reg [15:0] fill_q, chunk_length_q;
    reg [1:0] reply_action_q;
    reg last_ack_valid_q, done_valid_q;
    reg [31:0] last_ack_sequence_q,last_ack_offset_q,last_ack_crc_q,last_ack_progress_q;
    reg [31:0] done_frame_q, done_crc_q;
    (* ram_style="block" *) reg [7:0] result_mem[0:CHUNK_BYTES-1];
    wire [7:0] h_type=header_q[471:464];
    wire [127:0] h_session=header_q[447:320];
    wire [31:0] h_frame=header_q[319:288], h_seq=header_q[287:256], h_offset=header_q[255:224],
        h_bytes=header_q[223:192],h_frame_crc=header_q[191:160],h_payload_crc=header_q[63:32];
    wire [15:0] h_length=header_q[159:144];
    wire take=s_valid&&s_ready;
    wire final_chunk=(offset_q+chunk_length_q==OUTPUT_BYTES);
    assign s_ready=rst_n&&parser_q==CAPTURE;
    assign response_valid=rst_n&&parser_q==REPLY;
    // Registered one-cycle request isolates length/ownership decoding from the
    // frozen, physically wide ping-pong RAM read-enable network. This is the
    // only reader; a granted busy bank cannot be consumed by another reader.
    // Reserve both granted reads and the registered request. Never read
    // ahead of this retained packet, including partial tails and bank gaps.
    wire [16:0] reserved_bytes={1'b0,fill_q}+read_pending_q+read_request_q;
    wire read_fire=read_request_q&&rd_busy;
    wire request_available=active_q&&!buffer_ready_q&&rd_busy&&
        reserved_bytes<{1'b0,chunk_length_q}&&(read_pending_q+read_request_q)<4;
    assign rd_req=rst_n&&read_request_q;
    assign result_active=active_q;
    assign result_ready=buffer_ready_q;
    function automatic [31:0] crc_byte(input [31:0] current,input [7:0] data);
        reg [31:0] v;integer k;
        begin v=current^{24'd0,data};for(k=0;k<8;k=k+1)v=v[0]?((v>>1)^32'hedb88320):(v>>1);crc_byte=v;end
    endfunction
    task automatic clear_capture;
        begin count_q<=0;length_q<=0;header_q<=0;small_payload_q<=0;bad_length_q<=0;
            header_crc_q<=32'hffffffff;payload_crc_q<=32'hffffffff;gap_q<=0;end
    endtask
    task automatic respond(input [15:0] code,input [31:0] progress);
        begin parser_q<=REPLY;response_type<=h_type|8'h80;response_status<=code;
            response_session<=h_session;response_frame_id<=h_frame;response_sequence<=h_seq;
            response_offset<=h_offset;response_frame_crc<=h_frame_crc;response_next_offset<=progress;
            response_metadata<=metadata_q;response_flags<=0;response_length<=0;response_payload_crc<=0;reply_action_q<=0;end
    endtask
    task automatic reject(input [15:0] code);
        begin rejected_count<=rejected_count+1;respond(code,offset_q);end
    endtask
    always @(posedge clk) begin
        if(rst_n&&read_update_q) result_mem[fill_q]<=read_byte_q;
        if(payload_rd_req) payload_rd_data<=result_mem[payload_rd_addr];
        payload_rd_valid<=payload_rd_req&&rst_n;
    end
    initial begin
        if(OUTPUT_BYTES<1||CHUNK_BYTES!=1024||PACKET_GAP_TIMEOUT_CYCLES<1)
            $fatal(1,"invalid ethernet_result_tx parameters");
    end
    always @(posedge clk) begin
        if(!rst_n) begin
            parser_q<=CAPTURE;clear_capture();active_q<=0;done_seen_q<=0;buffer_ready_q<=0;read_pending_q<=0;
            read_update_q<=0;read_byte_q<=0;read_request_q<=0;
            final_acked_q<=0;session_q<=0;frame_q<=0;offset_q<=0;sequence_q<=0;rolling_crc_q<=32'hffffffff;
            chunk_crc_q<=32'hffffffff;fill_q<=0;chunk_length_q<=0;frame_release<=0;
            reply_action_q<=0;last_ack_valid_q<=0;done_valid_q<=0;done_session_q<=0;done_frame_q<=0;done_crc_q<=0;
            last_ack_sequence_q<=0;last_ack_offset_q<=0;last_ack_crc_q<=0;last_ack_progress_q<=0;
            response_type<=0;response_status<=0;response_flags<=0;response_length<=0;response_session<=0;
            response_frame_id<=0;response_sequence<=0;response_offset<=0;response_frame_crc<=0;response_next_offset<=0;
            response_payload_crc<=0;response_metadata<=0;read_bytes_count<=0;release_count<=0;rejected_count<=0;metadata_q<=0;
        end else begin
            frame_release<=0;
            read_update_q<=0;
            read_request_q<=0;
            if(frame_start&&!active_q) begin
                active_q<=1;session_q<=frame_session;frame_q<=frame_id;offset_q<=0;sequence_q<=0;
                rolling_crc_q<=32'hffffffff;chunk_crc_q<=32'hffffffff;fill_q<=0;
                chunk_length_q<=(OUTPUT_BYTES<CHUNK_BYTES)?OUTPUT_BYTES:CHUNK_BYTES;
                buffer_ready_q<=0;read_pending_q<=0;read_update_q<=0;read_request_q<=0;final_acked_q<=0;last_ack_valid_q<=0;done_seen_q<=0;
            end
            if(core_done&&active_q) done_seen_q<=1;
            if(request_available)read_request_q<=1;
            // Count actual bank handshakes, not scheduled requests. A bank
            // may become unavailable while the request stage is asserted.
            case({read_fire,read_update_q})
                2'b10:read_pending_q<=read_pending_q+1'b1;
                2'b01:read_pending_q<=read_pending_q-1'b1;
                default:begin end
            endcase
            if(rd_valid&&read_pending_q!=0)begin
                read_byte_q<=rd_data;read_update_q<=1;
            end
            if(read_update_q) begin
                fill_q<=fill_q+1;read_bytes_count<=read_bytes_count+1;
                chunk_crc_q<=crc_byte(chunk_crc_q,read_byte_q);rolling_crc_q<=crc_byte(rolling_crc_q,read_byte_q);
                if(fill_q==chunk_length_q-1)buffer_ready_q<=1;
            end
            case(parser_q)
                CAPTURE: if(take)begin
                    gap_q<=0;
                    if(count_q==0)begin length_q<=s_length;metadata_q<=s_metadata;end
                    if(count_q<64)header_q<={header_q[503:0],s_data};
                    if(count_q<60)header_crc_q<=crc_byte(header_crc_q,s_data);
                    if(count_q>=64)payload_crc_q<=crc_byte(payload_crc_q,s_data);
                    if(count_q>=64&&count_q<68)small_payload_q<={small_payload_q[23:0],s_data};
                    if(count_q==16'hffff)bad_length_q<=1;else count_q<=count_q+1;
                    if(s_last)parser_q<=VERIFY;
                end else if(count_q!=0)begin
                    if(gap_q==PACKET_GAP_TIMEOUT_CYCLES-1)begin clear_capture();rejected_count<=rejected_count+1;end
                    else gap_q<=gap_q+1;
                end
                VERIFY: begin
                    if(count_q<64||header_q[511:480]!=32'h45564631||header_q[479:472]!=1||~header_crc_q!=header_q[31:0])begin
                        clear_capture();parser_q<=CAPTURE;
                    end else if(h_type<7||h_type>9)begin clear_capture();parser_q<=CAPTURE;end
                    else if(bad_length_q||count_q!=length_q||count_q!=64+h_length||h_length>4)reject(E_LENGTH);
                    else if(~payload_crc_q!=h_payload_crc)reject(E_PAYLOAD_CRC);
                    else if(header_q[463:448]!=0||header_q[143:128]!=0||header_q[127:64]!=0)reject(E_FLAGS);
                    else if(h_bytes!=OUTPUT_BYTES)reject(E_LENGTH);
                    else if(h_type==9&&done_valid_q&&h_session==done_session_q&&h_frame==done_frame_q&&h_frame_crc==done_crc_q&&
                        h_length==0&&h_offset==OUTPUT_BYTES&&h_seq==(OUTPUT_BYTES+CHUNK_BYTES-1)/CHUNK_BYTES)
                        respond(FRAME_DONE,OUTPUT_BYTES);
                    else if(!active_q)reject(NOT_READY);
                    else if(h_session!=session_q)reject(E_SESSION);
                    else if(h_frame!=frame_q)reject(E_FRAME_ID);
                    else if(h_type==7)begin
                        if(h_length!=0||h_frame_crc!=0)reject(E_LENGTH);
                        else if(h_offset!=offset_q||h_seq!=sequence_q)reject(E_OFFSET);
                        else if(!buffer_ready_q)reject(NOT_READY);
                        else begin
                            respond(ACK,offset_q);response_length<=chunk_length_q;response_payload_crc<=~chunk_crc_q;
                            response_flags<=final_chunk?16'd1:16'd0;response_frame_crc<=final_chunk?~rolling_crc_q:32'd0;
                        end
                    end else if(h_type==8)begin
                        if(h_length!=4||h_frame_crc!=0)reject(E_LENGTH);
                        else if(last_ack_valid_q&&h_seq==last_ack_sequence_q&&h_offset==last_ack_offset_q&&small_payload_q==last_ack_crc_q)
                            respond(ACK,last_ack_progress_q);
                        else if(!buffer_ready_q)reject(NOT_READY);
                        else if(h_offset!=offset_q||h_seq!=sequence_q)reject(E_OFFSET);
                        else if(small_payload_q!=~chunk_crc_q)reject(E_PAYLOAD_CRC);
                        else begin respond(ACK,offset_q+chunk_length_q);reply_action_q<=1;end
                    end else begin
                        if(h_length!=0||h_offset!=OUTPUT_BYTES||h_seq!=(OUTPUT_BYTES+CHUNK_BYTES-1)/CHUNK_BYTES)reject(E_OFFSET);
                        else if(!final_acked_q||!done_seen_q)reject(NOT_READY);
                        else if(h_frame_crc!=~rolling_crc_q)reject(E_FRAME_CRC);
                        else begin respond(FRAME_DONE,OUTPUT_BYTES);reply_action_q<=2;end
                    end
                end
                REPLY: if(response_ready)begin
                    if(reply_action_q==1)begin
                        last_ack_valid_q<=1;last_ack_sequence_q<=h_seq;last_ack_offset_q<=h_offset;
                        last_ack_crc_q<=small_payload_q;last_ack_progress_q<=offset_q+chunk_length_q;
                        if(final_chunk)final_acked_q<=1;
                        else begin
                            offset_q<=offset_q+chunk_length_q;sequence_q<=sequence_q+1;fill_q<=0;buffer_ready_q<=0;
                            chunk_crc_q<=32'hffffffff;
                            chunk_length_q<=((OUTPUT_BYTES-offset_q-chunk_length_q)<CHUNK_BYTES)?
                                (OUTPUT_BYTES-offset_q-chunk_length_q):CHUNK_BYTES;
                        end
                    end else if(reply_action_q==2)begin
                        done_valid_q<=1;done_session_q<=session_q;done_frame_q<=frame_q;done_crc_q<=~rolling_crc_q;
                        active_q<=0;buffer_ready_q<=0;frame_release<=1;release_count<=release_count+1;
                    end
                    clear_capture();parser_q<=CAPTURE;
                end
                default:begin parser_q<=CAPTURE;clear_capture();end
            endcase
        end
    end
endmodule
`default_nettype wire
