`timescale 1ns/1ps
`default_nettype none
// Bounded retained window over the existing synchronous stripe read port.
// ACK batches are validated in full before ANY ownership bit is changed.
module evf2_result_window #(
    parameter integer OUTPUT_BYTES=2073600,MAX_WINDOW=128,RETRY_CYCLES=3000000
)(
    input wire clk,rst_n,input wire frame_start,input wire[127:0]frame_session,
    input wire[31:0]frame_id,input wire core_done,
    output wire rd_req,input wire rd_busy,rd_valid,input wire[7:0]rd_data,
    input wire control_valid,output reg control_ready,input wire[1:0]control_kind,
    input wire[127:0]control_session,input wire[31:0]control_frame,control_crc,
    input wire[95:0]control_metadata,input wire[7:0]control_count,control_window,
    output wire proof_req,output wire[6:0]proof_index,input wire proof_valid,
    input wire[31:0]proof_sequence,proof_crc,
    output reg desc_valid,input wire desc_ready,
    output reg[7:0]desc_type,output reg[15:0]desc_status,desc_flags,desc_length,
    output reg[127:0]desc_session,output reg[31:0]desc_frame_id,desc_sequence,desc_offset,
    output reg[31:0]desc_frame_crc,desc_next_offset,desc_payload_crc,
    output reg[95:0]desc_metadata,
    input wire payload_rd_req,input wire[9:0]payload_rd_addr,
    output reg payload_rd_valid,output wire[7:0]payload_rd_data,
    output reg frame_release,output reg active,output reg negotiated,
    output reg[31:0]read_bytes_count,release_count,rejected_count,retransmitted_count,
    output wire[31:0]window_base,window_next
);
    localparam integer SW=$clog2(MAX_WINDOW),PACKETS=(OUTPUT_BYTES+1023)/1024;
    localparam integer PACKET_QW=(PACKETS<2)?1:$clog2(PACKETS+1);
    localparam integer QW=(PACKET_QW<SW)?SW:PACKET_QW;
    localparam integer LAST_BYTES=OUTPUT_BYTES-(PACKETS-1)*1024;
    localparam ACK_IDLE=0,ACK_REQ=1,ACK_WAIT=2,ACK_APPLY=3,ACK_CHECK=4;
    reg[2:0]ack_state_q;
    reg[7:0]ack_index_q,window_q;
    reg[MAX_WINDOW-1:0]ready_q,sent_q,acked_q,ack_mask_q,ack_seen_q;
    reg ack_bad_q;
    reg[QW-1:0]tag_q[0:MAX_WINDOW-1];
    reg[31:0]crc_q[0:MAX_WINDOW-1];
    reg[15:0]length_q[0:MAX_WINDOW-1];
    (* ram_style="block" *)reg[7:0]retained_mem[0:MAX_WINDOW*1024-1];
    reg[QW-1:0]base_q,next_q,scan_q;
    reg[31:0]frame_q,rolling_crc_q,chunk_crc_q;
    reg[127:0]session_q;reg[95:0]peer_q;
    reg filling_q,read_request_q,read_update_q,done_seen_q;
    reg[SW-1:0]fill_bank_q,desc_bank_q;
    reg[15:0]fill_q,chunk_length_q;reg[2:0]pending_q;
    reg[7:0]read_byte_q;
    reg[1:0]desc_action_q;
    reg control_reply_q,reply_release_q;reg[7:0]reply_type_q;reg[15:0]reply_status_q,reply_length_q;
    reg[127:0]reply_session_q;reg[31:0]reply_frame_q,reply_crc_q;
    reg[95:0]reply_metadata_q;reg[63:0]capability_q;
    reg[31:0]retry_timer_q;reg retry_pass_q,retry_requested_q;
    // Retry age starts at serializer completion, never at global scan expiry.
    // 20 ms at 150 MHz is an INITIAL DIAGNOSTIC setting, not a measured RTT.
    reg[31:0]tx_clock_q,last_tx_q[0:MAX_WINDOW-1];
    reg[31:0]scan_age_q;
    reg[QW-1:0]scan_age_sequence_q;
    wire unsent_ready=|(ready_q&~sent_q&~acked_q);
    reg done_valid_q;reg[127:0]done_session_q;reg[31:0]done_frame_q,done_crc_q;reg[95:0]done_peer_q;
    wire[SW-1:0]base_bank=base_q[SW-1:0],scan_bank=scan_q[SW-1:0],proof_bank=proof_sequence[SW-1:0];
    wire read_fire=read_request_q&&rd_busy;
    wire[16:0]reserved_bytes={1'b0,fill_q}+pending_q+read_request_q;
    wire request_available=active&&filling_q&&rd_busy&&reserved_bytes<chunk_length_q&&(pending_q+read_request_q)<4;
    wire identity_ok=control_session==session_q&&control_frame==frame_q&&control_metadata==peer_q;
    wire[QW:0]occupied_slots={1'b0,next_q}-{1'b0,base_q};
    // Snapshot lookup at the same edge as the original ACK_WAIT check.
    // The next clock validates only registered values, keeping a 128:1 lookup
    // out of the CRC/range/ownership decision path. Parser HOLD remains owned.
    reg[SW-1:0]ack_bank_q;
    reg[QW-1:0]ack_tag_q;
    reg[31:0]ack_slot_crc_q,ack_wire_sequence_q,ack_wire_crc_q;
    reg ack_sent_q,ack_seen_one_q,ack_range_q,ack_current_q;
    wire proof_good=ack_range_q&&ack_tag_q==ack_wire_sequence_q&&
        ack_slot_crc_q==ack_wire_crc_q&&ack_sent_q&&!ack_seen_one_q;
    assign rd_req=rst_n&&read_request_q;
    assign proof_req=rst_n&&ack_state_q==ACK_REQ;
    assign proof_index=ack_index_q[6:0];
    assign window_base=base_q;assign window_next=next_q;
    function automatic[31:0]crc_byte(input[31:0]c,input[7:0]d);
        reg[31:0]v;integer k;
        begin v=c^{24'd0,d};for(k=0;k<8;k=k+1)v=v[0]?((v>>1)^32'hedb88320):(v>>1);crc_byte=v;end
    endfunction
    function automatic[31:0]cap_crc(input[63:0]cap);
        reg[31:0]v;integer k;
        begin v=32'hffffffff;for(k=0;k<8;k=k+1)v=crc_byte(v,cap[63-k*8-:8]);cap_crc=~v;end
    endfunction
    wire[63:0]offered_cap={16'd1024,8'd0,control_window,32'h17000000};
    reg[7:0]retained_read_q,capability_read_q;
    reg capability_selected_q;
    // Dedicated SDP RAM output register: no unrelated capability mux inside
    // the inference port. Both branches retain exactly one-cycle read latency.
    assign payload_rd_data=capability_selected_q?capability_read_q:retained_read_q;
    always @(posedge clk)begin
        if(payload_rd_req)begin
            capability_selected_q<=desc_action_q==1;
            capability_read_q<=capability_q[63-payload_rd_addr*8-:8];
        end
    end
    always @(posedge clk)begin
        if(rst_n&&read_update_q)retained_mem[{fill_bank_q,fill_q[9:0]}]<=read_byte_q;
        if(payload_rd_req)retained_read_q<=retained_mem[{desc_bank_q,payload_rd_addr}];
        payload_rd_valid<=rst_n&&payload_rd_req;
    end
    integer i;
    initial begin
        if(OUTPUT_BYTES<1||OUTPUT_BYTES>2073600||MAX_WINDOW<2||MAX_WINDOW>128||
            (MAX_WINDOW&(MAX_WINDOW-1))!=0||RETRY_CYCLES<1||RETRY_CYCLES>=2147483647)$fatal(1,"invalid EVF2 window parameters");
    end
    always @(posedge clk)begin
        if(!rst_n)begin
            ack_bank_q<=0;ack_tag_q<=0;ack_slot_crc_q<=0;ack_wire_sequence_q<=0;ack_wire_crc_q<=0;
            ack_sent_q<=0;ack_seen_one_q<=0;ack_range_q<=0;ack_current_q<=0;
            ack_state_q<=ACK_IDLE;ack_index_q<=0;ack_mask_q<=0;ack_seen_q<=0;ack_bad_q<=0;control_ready<=0;
            window_q<=1;ready_q<=0;sent_q<=0;acked_q<=0;active<=0;negotiated<=0;
            base_q<=0;next_q<=0;scan_q<=0;frame_q<=0;session_q<=0;peer_q<=0;
            rolling_crc_q<=32'hffffffff;chunk_crc_q<=32'hffffffff;filling_q<=0;
            read_request_q<=0;read_update_q<=0;pending_q<=0;read_byte_q<=0;fill_bank_q<=0;
            fill_q<=0;chunk_length_q<=0;done_seen_q<=0;frame_release<=0;
            desc_valid<=0;desc_bank_q<=0;desc_action_q<=0;desc_type<=0;desc_status<=0;desc_flags<=0;desc_length<=0;
            desc_session<=0;desc_frame_id<=0;desc_sequence<=0;desc_offset<=0;desc_frame_crc<=0;
            desc_next_offset<=0;desc_payload_crc<=0;desc_metadata<=0;
            control_reply_q<=0;reply_release_q<=0;reply_type_q<=0;reply_status_q<=0;reply_length_q<=0;
            reply_session_q<=0;reply_frame_q<=0;reply_crc_q<=0;reply_metadata_q<=0;capability_q<=0;
            tx_clock_q<=0;scan_age_q<=0;scan_age_sequence_q<=0;retry_timer_q<=0;retry_pass_q<=0;retry_requested_q<=0;read_bytes_count<=0;release_count<=0;rejected_count<=0;retransmitted_count<=0;
            done_valid_q<=0;done_session_q<=0;done_frame_q<=0;done_crc_q<=0;done_peer_q<=0;
            for(i=0;i<MAX_WINDOW;i=i+1)begin tag_q[i]<=32'hffffffff;crc_q[i]<=0;length_q[i]<=0;last_tx_q[i]<=0;end
        end else begin
            frame_release<=0;control_ready<=0;read_request_q<=0;read_update_q<=0;
            tx_clock_q<=tx_clock_q+1'b1;
            // Pipeline the indexed age lookup before the scheduling decision.
            // Unsigned subtraction handles one 32-bit clock wrap; the bounded
            // frame deadline is far shorter than half the 28.6-second period.
            scan_age_q<=tx_clock_q-last_tx_q[scan_bank];
            scan_age_sequence_q<=scan_q;
            if(core_done&&active)done_seen_q<=1;
            if(frame_start)begin
                if(!active&&negotiated&&frame_session==session_q&&!desc_valid&&!control_reply_q)begin
                    active<=1;frame_q<=frame_id;base_q<=0;next_q<=0;scan_q<=0;
                    ready_q<=0;sent_q<=0;acked_q<=0;rolling_crc_q<=32'hffffffff;
                    filling_q<=0;pending_q<=0;read_bytes_count<=0;done_seen_q<=core_done;retry_timer_q<=0;retry_pass_q<=0;retry_requested_q<=0;
                end else rejected_count<=rejected_count+1;
            end
            // Descriptor owns its bank until the serializer's final handshake.
            if(desc_valid&&desc_ready)begin
                desc_valid<=0;
                if(desc_action_q==0)begin
                    if(sent_q[desc_bank_q])retransmitted_count<=retransmitted_count+1;
                    sent_q[desc_bank_q]<=1;last_tx_q[desc_bank_q]<=tx_clock_q;
                end else if(desc_action_q==2)begin
                    active<=0;frame_release<=1;release_count<=release_count+1;
                    done_valid_q<=1;done_session_q<=session_q;done_frame_q<=frame_q;
                    done_crc_q<=~rolling_crc_q;done_peer_q<=peer_q;
                end
            end
            // A batch mask refers to the ownership seen while proving it.
            // Do not recycle any bank between proof lookup and atomic apply.
            // An already-started fill may finish, but was not a valid sent
            // packet at proof lookup and cannot enter this batch's mask.
            if(active&&ack_state_q==ACK_IDLE&&base_q<next_q&&acked_q[base_bank]&&ready_q[base_bank]&&
                !(desc_valid&&desc_action_q==0&&desc_bank_q==base_bank))begin
                ready_q[base_bank]<=0;acked_q[base_bank]<=0;base_q<=base_q+1;
            end
            if(active&&ack_state_q==ACK_IDLE&&!filling_q&&next_q<PACKETS&&occupied_slots<window_q&&!ready_q[next_q[SW-1:0]])begin
                filling_q<=1;fill_bank_q<=next_q[SW-1:0];fill_q<=0;chunk_crc_q<=32'hffffffff;
                chunk_length_q<=(next_q==PACKETS-1)?LAST_BYTES:16'd1024;
                sent_q[next_q[SW-1:0]]<=0;acked_q[next_q[SW-1:0]]<=0;
            end
            if(request_available)read_request_q<=1;
            case({read_fire,read_update_q})
                2'b10:pending_q<=pending_q+1'b1;
                2'b01:pending_q<=pending_q-1'b1;
                default:begin end
            endcase
            if(rd_valid&&pending_q!=0)begin read_byte_q<=rd_data;read_update_q<=1;end
            if(read_update_q)begin
                fill_q<=fill_q+1;read_bytes_count<=read_bytes_count+1;
                rolling_crc_q<=crc_byte(rolling_crc_q,read_byte_q);chunk_crc_q<=crc_byte(chunk_crc_q,read_byte_q);
                if(fill_q==chunk_length_q-1)begin
                    ready_q[fill_bank_q]<=1;tag_q[fill_bank_q]<=next_q;
                    crc_q[fill_bank_q]<=~crc_byte(chunk_crc_q,read_byte_q);length_q[fill_bank_q]<=chunk_length_q;
                    next_q<=next_q+1;filling_q<=0;
                end
            end
            if(active)begin
                // Expiry requests a later pass. It must not restart an ongoing
                // scan, which would starve high slots under frequent retries.
                if(retry_timer_q==RETRY_CYCLES-1)begin retry_timer_q<=0;retry_requested_q<=1;end
                else retry_timer_q<=retry_timer_q+1;
            end
            if(!desc_valid)begin
                if(control_reply_q)begin
                    control_reply_q<=0;desc_valid<=1;desc_type<=reply_type_q;desc_status<=reply_status_q;
                    desc_flags<=0;desc_length<=reply_length_q;desc_session<=reply_session_q;desc_frame_id<=reply_frame_q;
                    desc_sequence<=reply_type_q==8'h89 ? PACKETS : 0;desc_offset<=reply_type_q==8'h89 ? OUTPUT_BYTES : 0;
                    desc_frame_crc<=reply_crc_q;desc_next_offset<=reply_type_q==8'h89 ? OUTPUT_BYTES : 0;
                    desc_payload_crc<=reply_length_q==8?cap_crc(capability_q):0;desc_metadata<=reply_metadata_q;
                    desc_action_q<=reply_release_q?2:1;
                end else if(active)begin
                    if(scan_q<base_q)scan_q<=base_q;
                    else if(scan_q>=next_q)begin scan_q<=base_q;retry_pass_q<=retry_requested_q;retry_requested_q<=0;end
                    else if(retry_pass_q&&ready_q[scan_bank]&&!acked_q[scan_bank]&&
                        sent_q[scan_bank]&&!unsent_ready&&scan_age_sequence_q!=scan_q)begin
                        // Hold this scan position for its registered age.
                    end else if(ready_q[scan_bank]&&!acked_q[scan_bank]&&
                        (!sent_q[scan_bank]||(retry_pass_q&&!unsent_ready&&
                        scan_age_sequence_q==scan_q&&scan_age_q>=RETRY_CYCLES)))begin
                        desc_valid<=1;desc_action_q<=0;desc_bank_q<=scan_bank;
                        desc_type<=8'h17;desc_status<=1;desc_flags<=scan_q==PACKETS-1?1:0;desc_length<=length_q[scan_bank];
                        desc_session<=session_q;desc_frame_id<=frame_q;desc_sequence<=scan_q;desc_offset<=scan_q*1024;
                        desc_frame_crc<=scan_q==PACKETS-1?~rolling_crc_q:0;desc_next_offset<=0;
                        desc_payload_crc<=crc_q[scan_bank];desc_metadata<=peer_q;scan_q<=scan_q+1;
                    end else scan_q<=scan_q+1;
                end
            end
            case(ack_state_q)
                ACK_IDLE:if(control_valid&&!control_ready)begin
                    if(control_kind==1&&!control_reply_q&&!desc_valid)begin
                        control_ready<=1;control_reply_q<=1;reply_type_q<=8'h81;reply_release_q<=0;
                        reply_session_q<=control_session;reply_frame_q<=0;reply_crc_q<=0;reply_metadata_q<=control_metadata;
                        if(active&&(control_session!=session_q||control_metadata!=peer_q||control_window!=window_q))begin
                            reply_status_q<=5;reply_length_q<=0;rejected_count<=rejected_count+1;
                        end else begin
                            negotiated<=1;session_q<=control_session;peer_q<=control_metadata;window_q<=control_window;
                            capability_q<=offered_cap;reply_status_q<=0;reply_length_q<=8;
                        end
                    end else if(control_kind==2)begin
                        ack_index_q<=0;ack_mask_q<=0;ack_seen_q<=0;ack_bad_q<=!active||!identity_ok||control_count==0||control_count>window_q;
                        ack_state_q<=ACK_REQ;
                    end else if(control_kind==3&&!control_reply_q)begin
                        control_ready<=1;control_reply_q<=1;reply_type_q<=8'h89;reply_length_q<=0;reply_release_q<=0;
                        reply_session_q<=control_session;reply_frame_q<=control_frame;reply_crc_q<=control_crc;reply_metadata_q<=control_metadata;
                        if(done_valid_q&&control_session==done_session_q&&control_frame==done_frame_q&&
                            control_crc==done_crc_q&&control_metadata==done_peer_q)reply_status_q<=4;
                        else if(!active||!identity_ok)begin reply_status_q<=16;rejected_count<=rejected_count+1;end
                        else if(base_q!=PACKETS||next_q!=PACKETS||!done_seen_q)begin reply_status_q<=24;rejected_count<=rejected_count+1;end
                        else if(control_crc!=~rolling_crc_q)begin reply_status_q<=21;rejected_count<=rejected_count+1;end
                        else begin reply_status_q<=4;reply_release_q<=1;end
                    end
                end
                ACK_REQ:ack_state_q<=ACK_WAIT;
                ACK_WAIT:if(proof_valid)begin
                    ack_bank_q<=proof_bank;ack_tag_q<=tag_q[proof_bank];ack_slot_crc_q<=crc_q[proof_bank];
                    ack_wire_sequence_q<=proof_sequence;ack_wire_crc_q<=proof_crc;
                    ack_sent_q<=sent_q[proof_bank];ack_seen_one_q<=ack_seen_q[proof_bank];
                    ack_range_q<=proof_sequence<next_q;
                    ack_current_q<=proof_sequence>=base_q&&proof_sequence<next_q;
                    ack_state_q<=ACK_CHECK;
                end
                ACK_CHECK:begin
                    if(!proof_good)ack_bad_q<=1;
                    ack_seen_q[ack_bank_q]<=1;
                    if(ack_current_q)ack_mask_q[ack_bank_q]<=1;
                    if(ack_index_q+1>=control_count)ack_state_q<=ACK_APPLY;
                    else begin ack_index_q<=ack_index_q+1;ack_state_q<=ACK_REQ;end
                end
                ACK_APPLY:begin
                    if(!ack_bad_q)begin
                        for(i=0;i<MAX_WINDOW;i=i+1)if(ack_mask_q[i])acked_q[i]<=1;
                    end
                    else rejected_count<=rejected_count+1;
                    control_ready<=1;ack_state_q<=ACK_IDLE;
                end
            endcase
        end
    end
endmodule
`default_nettype wire
