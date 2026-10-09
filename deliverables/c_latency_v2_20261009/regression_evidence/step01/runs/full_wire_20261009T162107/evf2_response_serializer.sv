`timescale 1ns/1ps
`default_nettype none
// Descriptor is held by caller until desc_ready pulses on FINAL output beat.
// CRC is calculated over 60 header bytes in 60 cycles, avoiding an unrolled
// 480-bit combinational CRC path. Four byte slots retain prefetched payload
// across arbitrary downstream stalls; descriptor ownership lasts to final beat.
module evf2_response_serializer(
    input wire clk,rst_n,
    input wire desc_valid,output wire desc_ready,output wire busy,
    input wire [7:0] desc_type,
    input wire [15:0] desc_status,desc_flags,desc_length,
    input wire [127:0] desc_session,
    input wire [31:0] desc_frame_id,desc_sequence,desc_offset,desc_frame_bytes,
    input wire [31:0] desc_frame_crc,desc_next_offset,desc_payload_crc,
    input wire [95:0] desc_metadata,
    output wire payload_rd_req,output wire [9:0] payload_rd_addr,
    input wire payload_rd_valid,input wire [7:0] payload_rd_data,
    output wire m_valid,input wire m_ready,output wire [7:0] m_data,
    output wire m_last,output wire [15:0] m_length,output wire [95:0] m_metadata
);
    localparam IDLE=0,CRC=1,HEADER=2,P_REQ=3,P_WAIT=4,P_SEND=5;
    reg [2:0] state_q;
    reg [511:0] header_q,shift_q;
    reg [31:0] crc_q;
    reg [6:0] index_q;
    reg [15:0] payload_length_q,payload_index_q,packet_length_q;
    reg [15:0] payload_final_index_q;
    reg [7:0] byte_q;
    reg [7:0] payload_fifo[0:3];
    reg [1:0] payload_head_q,payload_tail_q;
    reg [2:0] payload_count_q,payload_pending_q;
    reg [15:0] payload_issued_q;
    reg empty_payload_q,payload_last_q;
    reg [95:0] metadata_q;
    function automatic [31:0] crc_byte(input [31:0] current,input [7:0] data);
        reg [31:0] v;integer k;
        begin v=current^{24'd0,data};for(k=0;k<8;k=k+1)v=v[0]?((v>>1)^32'hedb88320):(v>>1);crc_byte=v;end
    endfunction
    wire [511:0] new_header={32'h45564632,8'd2,desc_type,desc_flags,desc_session,
        desc_frame_id,desc_sequence,desc_offset,desc_frame_bytes,desc_frame_crc,
        desc_length,desc_status,desc_next_offset,32'd0,desc_payload_crc,32'd0};
    assign busy=state_q!=IDLE;
    assign m_valid=rst_n&&(state_q==HEADER||(state_q==P_SEND&&payload_count_q!=0));
    assign m_data=state_q==HEADER?shift_q[511:504]:payload_fifo[payload_head_q];
    // The final payload index is registered at descriptor capture.
    assign m_last=(state_q==HEADER&&index_q==63&&empty_payload_q)||
        (state_q==P_SEND&&payload_index_q==payload_final_index_q);
    assign m_length=packet_length_q;
    assign m_metadata=metadata_q;
    assign desc_ready=m_valid&&m_ready&&m_last;
    wire payload_take=m_valid&&m_ready&&state_q==P_SEND;
    wire payload_return=payload_rd_valid&&payload_pending_q!=0;
    // Queued and in-flight bytes jointly reserve the four physical slots.
    assign payload_rd_req=rst_n&&state_q==P_SEND&&payload_issued_q<payload_length_q&&
        (payload_count_q+payload_pending_q)<4;
    assign payload_rd_addr=payload_issued_q[9:0];
    always @(posedge clk)begin
        if(!rst_n)begin payload_head_q<=0;payload_tail_q<=0;payload_count_q<=0;payload_pending_q<=0;payload_issued_q<=0;end
        else if(state_q==IDLE&&desc_valid)begin payload_head_q<=0;payload_tail_q<=0;payload_count_q<=0;payload_pending_q<=0;payload_issued_q<=0;end
        else begin
            if(payload_rd_req)payload_issued_q<=payload_issued_q+1'b1;
            case({payload_rd_req,payload_return})
                2'b10:payload_pending_q<=payload_pending_q+1'b1;
                2'b01:payload_pending_q<=payload_pending_q-1'b1;
                default:begin end
            endcase
            if(payload_return)begin payload_fifo[payload_tail_q]<=payload_rd_data;payload_tail_q<=payload_tail_q+1'b1;end
            if(payload_take)payload_head_q<=payload_head_q+1'b1;
            case({payload_return,payload_take})
                2'b10:payload_count_q<=payload_count_q+1'b1;
                2'b01:payload_count_q<=payload_count_q-1'b1;
                default:begin end
            endcase
        end
    end
    always @(posedge clk)begin
        if(!rst_n)begin state_q<=IDLE;header_q<=0;shift_q<=0;crc_q<=32'hffffffff;index_q<=0;
            payload_length_q<=0;payload_final_index_q<=0;payload_index_q<=0;packet_length_q<=16'd64;byte_q<=0;metadata_q<=0;
            empty_payload_q<=1;payload_last_q<=0;end
        else case(state_q)
            IDLE:if(desc_valid)begin
                header_q<=new_header;shift_q<=new_header;crc_q<=32'hffffffff;index_q<=0;
                payload_length_q<=desc_length;payload_final_index_q<=desc_length-16'd1;payload_index_q<=0;metadata_q<=desc_metadata;state_q<=CRC;
                // Precompute before the 60-cycle header CRC. The packet bridge
                // consumes a registered total length, not add-then-subtract.
                packet_length_q<=16'd64+desc_length;
                empty_payload_q<=desc_length==0;
            end
            CRC:begin
                crc_q<=crc_byte(crc_q,shift_q[511:504]);shift_q<={shift_q[503:0],8'd0};
                if(index_q==59)begin shift_q<={header_q[511:32],~crc_byte(crc_q,shift_q[511:504])};index_q<=0;state_q<=HEADER;end
                else index_q<=index_q+1;
            end
            HEADER:if(m_ready)begin
                shift_q<={shift_q[503:0],8'd0};index_q<=index_q+1;
                if(index_q==63)state_q<=empty_payload_q?IDLE:P_SEND;
            end
            P_REQ:begin payload_last_q<=payload_index_q==payload_final_index_q;state_q<=P_WAIT;end
            P_WAIT:if(payload_rd_valid)begin byte_q<=payload_rd_data;state_q<=P_SEND;end
            P_SEND:if(payload_take)begin
                if(payload_index_q==payload_final_index_q)state_q<=IDLE;
                else payload_index_q<=payload_index_q+1;
            end
            default:state_q<=IDLE;
        endcase
    end
endmodule
`default_nettype wire
