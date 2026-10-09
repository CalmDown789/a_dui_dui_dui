`timescale 1ns/1ps
`default_nettype none

// EVF1 input application controller. s_* is a complete upstream-validated
// UDP payload stream, NOT raw RGMII. No PHY/MAC/IP validation is claimed here.
// A private 1024-byte RAM verifies application CRCs before any core-RAM write.
module ethernet_frame_rx #(
    parameter integer FRAME_BYTES = 518400,
    parameter integer CHUNK_BYTES = 1024,
    parameter integer OUTPUT_CONTROLLER_PRESENT = 0,
    parameter integer RX_IDLE_TIMEOUT_CYCLES = 1500000000,
    parameter integer PACKET_GAP_TIMEOUT_CYCLES = 1024
)(
    input wire clk, input wire rst_n,
    input wire s_valid, output wire s_ready, input wire [7:0] s_data,
    input wire s_last, input wire [15:0] s_length, input wire [95:0] s_metadata,
    output wire response_valid, input wire response_ready,
    output reg [7:0] response_type,
    output reg [15:0] response_status,
    output reg [127:0] response_session,
    output reg [31:0] response_frame_id, response_sequence, response_offset,
    output reg [31:0] response_frame_crc, response_next_offset,
    output reg [95:0] response_metadata,
    output wire frame_wr_en, output wire [18:0] frame_wr_addr, output wire [7:0] frame_wr_data,
    output reg core_start,
    // ONLY complete output transmission+PC frame acknowledgement may release.
    input wire frame_release,
    output wire frame_locked,
    output wire [2:0] frame_state,
    output wire [31:0] next_offset, expected_frame_id,
    output reg [31:0] start_count, written_bytes_count, rejected_count,
    output reg [31:0] receive_timeout_count, packet_timeout_count
);
    localparam [2:0] NO_SESSION=0, IDLE=1, RECEIVING=2, RUNNING=3, FAILED=4;
    localparam [2:0] CAPTURE=0, VERIFY=1, DISPATCH=2, RAM_READ=3, RAM_WRITE=4, REPLY=5, PREPARE=6;
    localparam [15:0] OK=0, ACK=1, STARTED=2, PROCESSING=3, FRAME_DONE=4, BUSY=5,
        E_SESSION=16, E_FRAME_ID=17, E_PAYLOAD_CRC=18, E_LENGTH=19, E_OFFSET=20,
        E_FRAME_CRC=21, E_FLAGS=22, E_TYPE=23, NOT_READY=24;
    reg [2:0] pipe_state_q, frame_state_q;
    reg [511:0] header_q;
    reg [15:0] received_q, packet_length_q;
    reg [95:0] packet_metadata_q;
    reg packet_length_bad_q;
    reg [31:0] header_crc_q, payload_crc_q;
    reg [31:0] gap_timer_q, idle_timer_q;
    (* ram_style="block" *) reg [7:0] payload_mem [0:2*CHUNK_BYTES-1];
    reg [15:0] apply_index_q;
    reg [7:0] apply_data_q;
    reg [31:0] apply_offset_q;
    reg [31:0] expected_chunk_q;
    reg [127:0] session_q;
    reg [31:0] expected_id_q, progress_q, sequence_q, declared_crc_q, frame_crc_q;
    reg last_packet_valid_q, last_done_valid_q;
    reg [31:0] last_sequence_q, last_offset_q, last_payload_crc_q, last_done_id_q, last_done_crc_q;
    reg [15:0] last_length_q;
    wire [7:0] h_type = header_q[471:464];
    wire [127:0] h_session = header_q[447:320];
    wire [31:0] h_frame = header_q[319:288], h_sequence = header_q[287:256],
        h_offset = header_q[255:224], h_bytes = header_q[223:192], h_frame_crc = header_q[191:160];
    wire [15:0] h_length = header_q[159:144];
    wire [31:0] h_payload_crc = header_q[63:32];
    wire take = s_valid && s_ready;
    // Capture and application dispatch have separate registers and RAM banks.
    reg [1:0] owned_q, queued_q;
    reg capture_active_q, capture_bank_q, active_bank_q;
    reg [15:0] capture_count_q, capture_length_q;
    reg [95:0] capture_metadata_q;
    reg [511:0] capture_header_q;
    reg [31:0] capture_hcrc_q, capture_pcrc_q, capture_gap_q;
    reg capture_bad_q;
    reg [511:0] bank_header[0:1];
    reg [31:0] bank_hcrc[0:1], bank_pcrc[0:1];
    reg [15:0] bank_count[0:1], bank_length[0:1];
    reg [95:0] bank_metadata[0:1];
    reg bank_bad[0:1];
    reg queue_bank[0:1];
    reg queue_head_q, queue_tail_q;
    reg [1:0] queue_count_q;
    reg capture_timeout_q;
    wire free_bank = owned_q[0];
    wire write_bank = capture_active_q ? capture_bank_q : free_bank;
    wire [15:0] write_index = capture_active_q ? capture_count_q : 16'd0;
    wire enqueue = take && s_last;
    wire dequeue = pipe_state_q == CAPTURE && queue_count_q != 0;
    wire release_bank = (pipe_state_q == REPLY && response_ready) ||
        (pipe_state_q == VERIFY && (received_q < 64 ||
         header_q[511:480] != 32'h45564631 || header_q[479:472] != 1 ||
         ~header_crc_q != header_q[31:0] ||
         (OUTPUT_CONTROLLER_PRESENT && h_type >= 7 && h_type <= 9)));
    wire capture_timeout = capture_active_q && !take &&
        capture_gap_q == PACKET_GAP_TIMEOUT_CYCLES-1;
    wire [31:0] expected_chunk = ((FRAME_BYTES-progress_q) < CHUNK_BYTES) ? (FRAME_BYTES-progress_q) : CHUNK_BYTES;
    assign s_ready = rst_n && (capture_active_q || !(&owned_q));
    assign response_valid = rst_n && pipe_state_q == REPLY;
    assign frame_wr_en = rst_n && pipe_state_q == RAM_WRITE && frame_state_q == RECEIVING;
    assign frame_wr_addr = apply_offset_q[18:0] + apply_index_q;
    assign frame_wr_data = apply_data_q;
    assign frame_locked = frame_state_q == RUNNING;
    assign frame_state = frame_state_q;
    assign next_offset = progress_q;
    assign expected_frame_id = expected_id_q;

    function automatic [31:0] crc_byte(input [31:0] current, input [7:0] data);
        reg [31:0] v;
        integer k;
        begin
            v = current ^ {24'd0,data};
            for (k=0;k<8;k=k+1) v = v[0] ? ((v>>1)^32'hedb88320) : (v>>1);
            crc_byte = v;
        end
    endfunction
    task automatic clear_capture;
        begin
            received_q <= 0; packet_length_q <= 0; packet_length_bad_q <= 0;
            header_q <= 0; header_crc_q <= 32'hffffffff; payload_crc_q <= 32'hffffffff;
            gap_timer_q <= 0;
        end
    endtask
    task automatic respond(input [15:0] code, input [31:0] progress);
        begin
            pipe_state_q <= REPLY;
            response_status <= code; response_next_offset <= progress;
        end
    endtask
    reg reject_event_q;
    // Diagnostic counting is one cycle after the decision. Keep protocol
    // priority/response timing intact while removing the deep decision tree
    // from the 32-bit counter clock-enable path.
    always @(posedge clk)begin
        if(!rst_n)rejected_count<=0;
        else if(reject_event_q)rejected_count<=rejected_count+1;
    end
    task automatic reject(input [15:0] code);
        begin reject_event_q <= 1; respond(code,progress_q); end
    endtask
    localparam integer PAYLOAD_AW=(2*CHUNK_BYTES<2)?1:$clog2(2*CHUNK_BYTES);
    wire[PAYLOAD_AW-1:0]payload_write_addr=write_bank*CHUNK_BYTES+write_index-64;
    wire[PAYLOAD_AW-1:0]payload_read_addr=active_bank_q*CHUNK_BYTES+apply_index_q+
        (pipe_state_q==RAM_WRITE?1:0);
    wire payload_read_enable=pipe_state_q==RAM_READ||
        (pipe_state_q==RAM_WRITE&&apply_index_q<h_length-1);
    // One explicit synchronous read port. Address selection precedes the RAM;
    // the output register belongs only to RAM and keeps the same copy latency.
    always @(posedge clk) begin
        if (take && write_index >= 64 && write_index < 64+CHUNK_BYTES)
            payload_mem[payload_write_addr] <= s_data;
        if(payload_read_enable)apply_data_q<=payload_mem[payload_read_addr];
    end
    // Each bank remains owned from first capture beat to final reply handshake.
    // Invalid/ignored headers also free exactly their own bank. Timeout frees
    // only the incomplete capture bank; it cannot disturb dispatch or RUNNING.
    integer bank_i;
    always @(posedge clk) begin
        if (!rst_n) begin
            owned_q<=0;queued_q<=0;capture_active_q<=0;capture_bank_q<=0;
            capture_count_q<=0;capture_length_q<=0;capture_metadata_q<=0;
            capture_header_q<=0;capture_hcrc_q<=32'hffffffff;capture_pcrc_q<=32'hffffffff;
            capture_gap_q<=0;capture_bad_q<=0;queue_head_q<=0;queue_tail_q<=0;queue_count_q<=0;
            capture_timeout_q<=0;packet_timeout_count<=0;
            for(bank_i=0;bank_i<2;bank_i=bank_i+1)begin
                bank_header[bank_i]<=0;bank_hcrc[bank_i]<=0;bank_pcrc[bank_i]<=0;
                bank_count[bank_i]<=0;bank_length[bank_i]<=0;bank_metadata[bank_i]<=0;bank_bad[bank_i]<=0;
                queue_bank[bank_i]<=0;
            end
        end else begin
            capture_timeout_q<=0;
            if (release_bank) owned_q[active_bank_q]<=0;
            if (dequeue) begin queued_q[queue_bank[queue_head_q]]<=0;queue_head_q<=~queue_head_q;end
            case ({enqueue,dequeue})
                2'b10:queue_count_q<=queue_count_q+1'b1;
                2'b01:queue_count_q<=queue_count_q-1'b1;
                default:begin end
            endcase
            if(take)begin
                owned_q[write_bank]<=1;capture_gap_q<=0;
                if(!capture_active_q)begin
                    capture_bank_q<=free_bank;capture_length_q<=s_length;capture_metadata_q<=s_metadata;
                    capture_header_q<={504'd0,s_data};capture_hcrc_q<=crc_byte(32'hffffffff,s_data);
                    capture_pcrc_q<=32'hffffffff;capture_bad_q<=0;capture_count_q<=1;
                end else begin
                    if(write_index<64)capture_header_q<={capture_header_q[503:0],s_data};
                    if(write_index<60)capture_hcrc_q<=crc_byte(capture_hcrc_q,s_data);
                    if(write_index>=64)capture_pcrc_q<=crc_byte(capture_pcrc_q,s_data);
                    if(write_index==16'hffff || write_index>=64+CHUNK_BYTES ||
                        s_length!=capture_length_q || s_metadata!=capture_metadata_q)capture_bad_q<=1;
                    if(write_index!=16'hffff)capture_count_q<=write_index+1'b1;
                end
                capture_active_q<=!s_last;
                if(s_last)begin
                    queue_bank[queue_tail_q]<=write_bank;queue_tail_q<=~queue_tail_q;queued_q[write_bank]<=1;
                    bank_header[write_bank]<=!capture_active_q?{504'd0,s_data}:
                        (write_index<64?{capture_header_q[503:0],s_data}:capture_header_q);
                    bank_hcrc[write_bank]<=!capture_active_q?crc_byte(32'hffffffff,s_data):
                        (write_index<60?crc_byte(capture_hcrc_q,s_data):capture_hcrc_q);
                    bank_pcrc[write_bank]<=write_index>=64?crc_byte(capture_pcrc_q,s_data):32'hffffffff;
                    bank_count[write_bank]<=write_index==16'hffff ? 16'hffff : write_index+1'b1;
                    bank_length[write_bank]<=capture_active_q?capture_length_q:s_length;
                    bank_metadata[write_bank]<=capture_active_q?capture_metadata_q:s_metadata;
                    bank_bad[write_bank]<=capture_active_q&&(capture_bad_q || write_index==16'hffff ||
                        write_index>=64+CHUNK_BYTES || s_length!=capture_length_q || s_metadata!=capture_metadata_q);
                end
            end else if(capture_active_q)begin
                if(capture_timeout)begin
                    owned_q[capture_bank_q]<=0;capture_active_q<=0;capture_gap_q<=0;
                    capture_timeout_q<=1;packet_timeout_count<=packet_timeout_count+1;
                end else capture_gap_q<=capture_gap_q+1'b1;
            end
        end
    end
    initial begin
        if (FRAME_BYTES<1 || FRAME_BYTES>524288 || CHUNK_BYTES<1 || CHUNK_BYTES>1024 ||
            RX_IDLE_TIMEOUT_CYCLES<1 || PACKET_GAP_TIMEOUT_CYCLES<1)
            $fatal(1,"invalid ethernet_frame_rx parameters");
    end
    // Dispatch context is overwritten atomically on dequeue. Do not
    // clear its 610 bits from serializer final-ready; this removes the
    // length/last/ready -> context clock-enable path without changing ownership.
    // Identity registers have no shared reply-decision CE: the 397-load enable
    // on the first implementation's worst path is avoided. Fields settle
    // before REPLY and remain constant while its packet is stalled.
    always @(posedge clk) begin
        if (!rst_n) begin
            response_type<=0;response_session<=0;response_frame_id<=0;response_sequence<=0;
            response_offset<=0;response_frame_crc<=0;response_metadata<=0;
        end else begin
            response_type<=h_type|8'h80;response_session<=h_session;response_frame_id<=h_frame;
            response_sequence<=h_sequence;response_offset<=h_offset;response_frame_crc<=h_frame_crc;
            response_metadata<=packet_metadata_q;
        end
    end
    // rst_n must be synchronously released by the application clock-domain reset.
    always @(posedge clk) begin
        if (!rst_n) begin
            pipe_state_q<=CAPTURE; frame_state_q<=NO_SESSION; session_q<=0;
            packet_metadata_q<=0;
            expected_id_q<=0; progress_q<=0; sequence_q<=0; declared_crc_q<=0; frame_crc_q<=32'hffffffff;
            last_packet_valid_q<=0; last_done_valid_q<=0; last_sequence_q<=0; last_offset_q<=0;
            last_payload_crc_q<=0; last_length_q<=0; last_done_id_q<=0; last_done_crc_q<=0;
            apply_index_q<=0; apply_offset_q<=0; expected_chunk_q<=0; core_start<=0;
            response_status<=0; response_next_offset<=0;
            idle_timer_q<=0; start_count<=0; written_bytes_count<=0; reject_event_q<=0;
            receive_timeout_count<=0; active_bank_q<=0;
            clear_capture();
        end else begin
            core_start<=0;
            reject_event_q<=capture_timeout_q;
            // Timeout is receiving-inactivity only: never frees a running frame.
            if ((frame_state_q==RECEIVING || frame_state_q==FAILED) && pipe_state_q==CAPTURE && queue_count_q==0 && !capture_active_q && !s_valid) begin
                if (idle_timer_q == RX_IDLE_TIMEOUT_CYCLES-1) begin
                    frame_state_q<=NO_SESSION; session_q<=0; progress_q<=0; sequence_q<=0;
                    last_packet_valid_q<=0; last_done_valid_q<=0; idle_timer_q<=0;
                    receive_timeout_count<=receive_timeout_count+1;
                end else idle_timer_q<=idle_timer_q+1;
            end else idle_timer_q<=0;
            if (frame_release && frame_state_q==RUNNING) begin
                last_done_valid_q<=1; last_done_id_q<=expected_id_q; last_done_crc_q<=declared_crc_q;
                expected_id_q<=expected_id_q+1; frame_state_q<=IDLE;
            end
            case (pipe_state_q)
                CAPTURE: if (dequeue) begin
                    active_bank_q <= queue_bank[queue_head_q];
                    header_q <= bank_header[queue_bank[queue_head_q]];
                    header_crc_q <= bank_hcrc[queue_bank[queue_head_q]];
                    payload_crc_q <= bank_pcrc[queue_bank[queue_head_q]];
                    received_q <= bank_count[queue_bank[queue_head_q]];
                    packet_length_q <= bank_length[queue_bank[queue_head_q]];
                    packet_metadata_q <= bank_metadata[queue_bank[queue_head_q]];
                    packet_length_bad_q <= bank_bad[queue_bank[queue_head_q]];
                    pipe_state_q <= VERIFY;
                end
                VERIFY: begin
                    if (received_q<64 || header_q[511:480]!=32'h45564631 || header_q[479:472]!=1 ||
                        ~header_crc_q!=header_q[31:0]) begin
                        reject_event_q<=1; pipe_state_q<=CAPTURE;
                    end else if (OUTPUT_CONTROLLER_PRESENT && h_type>=7 && h_type<=9) begin
                        pipe_state_q<=CAPTURE;
                    end else if (packet_length_bad_q || received_q!=packet_length_q || received_q!=64+h_length)
                        reject(E_LENGTH);
                    else if (~payload_crc_q!=h_payload_crc) reject(E_PAYLOAD_CRC);
                    else pipe_state_q<=PREPARE;
                end
                PREPARE: begin expected_chunk_q<=expected_chunk; pipe_state_q<=DISPATCH; end
                DISPATCH: begin
                    if (header_q[463:448]!=0 || header_q[143:128]!=0 || header_q[127:64]!=0) reject(E_FLAGS);
                    else if (h_type<1 || h_type>9) reject(E_TYPE);
                    else if (h_bytes!=FRAME_BYTES) reject(E_LENGTH);
                    else if (h_type>6) reject(E_TYPE); // separate output ownership layer
                    else if (h_type==1) begin
                        if (h_length!=0 || h_frame!=0 || h_sequence!=0 || h_offset!=0 || h_frame_crc!=0) reject(E_LENGTH);
                        else if (frame_state_q!=NO_SESSION && session_q==h_session) respond(OK,progress_q);
                        else if (frame_state_q!=NO_SESSION && frame_state_q!=IDLE) reject(BUSY);
                        else begin
                            session_q<=h_session; frame_state_q<=IDLE; expected_id_q<=0; progress_q<=0; sequence_q<=0;
                            declared_crc_q<=0; frame_crc_q<=32'hffffffff; last_packet_valid_q<=0; last_done_valid_q<=0;
                            respond(OK,0);
                        end
                    end else if (frame_state_q==NO_SESSION || session_q!=h_session) reject(E_SESSION);
                    else if (last_done_valid_q && h_frame==last_done_id_q && h_frame_crc==last_done_crc_q &&
                        (h_type==2 || h_type==3 || h_type==4)) respond(FRAME_DONE,progress_q);
                    else if (h_frame!=expected_id_q) reject(E_FRAME_ID);
                    else if (h_type==5 || h_type==6) begin
                        if (h_length!=0 || h_sequence!=0 || h_offset!=0 || h_frame_crc!=0) reject(E_LENGTH);
                        else if (h_type==5) begin
                            case(frame_state_q)
                                RECEIVING: respond(ACK,progress_q);
                                RUNNING: respond(PROCESSING,progress_q);
                                FAILED: respond(E_FRAME_CRC,progress_q);
                                default: respond(OK,progress_q);
                            endcase
                        end else if (frame_state_q==RUNNING) reject(BUSY);
                        else begin
                            frame_state_q<=IDLE; progress_q<=0; sequence_q<=0; declared_crc_q<=0;
                            frame_crc_q<=32'hffffffff; last_packet_valid_q<=0; respond(OK,0);
                        end
                    end else if (h_type==2) begin
                        if (h_length!=0 || h_sequence!=0 || h_offset!=0) reject(E_LENGTH);
                        else if (frame_state_q==RUNNING) reject(BUSY);
                        else if (frame_state_q==RECEIVING || frame_state_q==FAILED)
                            respond((frame_state_q==RECEIVING && declared_crc_q==h_frame_crc)?ACK:E_FRAME_CRC,progress_q);
                        else begin
                            frame_state_q<=RECEIVING; declared_crc_q<=h_frame_crc; progress_q<=0; sequence_q<=0;
                            frame_crc_q<=32'hffffffff; last_packet_valid_q<=0; respond(ACK,0);
                        end
                    end else if (frame_state_q==RUNNING) begin
                        if (h_type==4 && h_length==0 && h_frame_crc==declared_crc_q && h_offset==FRAME_BYTES && h_sequence==sequence_q)
                            respond(STARTED,progress_q);
                        else reject(BUSY);
                    end else if (frame_state_q!=RECEIVING) reject(frame_state_q==FAILED?E_FRAME_CRC:NOT_READY);
                    else if (h_frame_crc!=declared_crc_q) reject(E_FRAME_CRC);
                    else if (h_type==3) begin
                        if (last_packet_valid_q && h_sequence==last_sequence_q && h_offset==last_offset_q &&
                            h_length==last_length_q && h_payload_crc==last_payload_crc_q) respond(ACK,progress_q);
                        else if (h_offset!=progress_q || h_sequence!=sequence_q) reject(E_OFFSET);
                        else if (h_length==0 || h_length!=expected_chunk_q) reject(E_LENGTH);
                        else begin apply_index_q<=0; apply_offset_q<=progress_q; pipe_state_q<=RAM_READ; end
                    end else if (h_type==4) begin
                        if (h_length!=0 || h_offset!=FRAME_BYTES || h_sequence!=sequence_q || progress_q!=FRAME_BYTES) reject(E_OFFSET);
                        else if (~frame_crc_q!=declared_crc_q) begin frame_state_q<=FAILED; reject(E_FRAME_CRC); end
                        else begin frame_state_q<=RUNNING; core_start<=1; start_count<=start_count+1; respond(STARTED,progress_q); end
                    end else reject(E_TYPE);
                end
                RAM_READ: pipe_state_q<=RAM_WRITE;
                RAM_WRITE: begin
                    frame_crc_q<=crc_byte(frame_crc_q,apply_data_q);
                    written_bytes_count<=written_bytes_count+1;
                    if (apply_index_q==h_length-1) begin
                        progress_q<=progress_q+h_length; sequence_q<=sequence_q+1;
                        last_packet_valid_q<=1; last_sequence_q<=h_sequence; last_offset_q<=h_offset;
                        last_length_q<=h_length; last_payload_crc_q<=h_payload_crc;
                        respond(ACK,progress_q+h_length);
                    end else begin apply_index_q<=apply_index_q+1; pipe_state_q<=RAM_WRITE; end
                end
                REPLY: if (response_ready) begin pipe_state_q<=CAPTURE; end
                default: begin pipe_state_q<=CAPTURE; end
            endcase
        end
    end
endmodule
`default_nettype wire
