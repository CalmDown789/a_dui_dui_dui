`timescale 1ns / 1ps
`default_nettype none

// Single-clock normalized packet contract. Not a PHY/MAC/IP/UDP parser.
// RAM contents are private until length and end-of-packet integrity agree.
module udp_packet_commit_buffer #(
    parameter integer MAX_BYTES = 1472,
    parameter integer META_WIDTH = 64,
    parameter integer GOOD_FLAG_WIDTH = 4,
    parameter [GOOD_FLAG_WIDTH-1:0] GOOD_REQUIRED_MASK = {GOOD_FLAG_WIDTH{1'b1}},
    parameter integer TIMEOUT_CYCLES = 1024
)(
    input  wire clk,
    input  wire rst_n,
    input  wire rx_begin,
    input  wire [15:0] rx_declared_len,
    input  wire [META_WIDTH-1:0] rx_metadata,
    input  wire rx_data_valid,
    input  wire [7:0] rx_data,
    input  wire rx_end,
    input  wire [GOOD_FLAG_WIDTH-1:0] rx_good_flags,
    output wire rx_begin_ready,
    output wire rx_busy,
    output wire out_valid,
    input  wire out_ready,
    output wire [7:0] out_data,
    output wire out_last,
    output wire [15:0] out_length,
    output wire [META_WIDTH-1:0] out_metadata,
    output reg [31:0] committed_count,
    output reg [31:0] rejected_event_count,
    output reg [31:0] timeout_count,
    output reg [3:0] last_reject_reason
);

    localparam integer AW=(MAX_BYTES<=1)?1:$clog2(MAX_BYTES);
    localparam integer TW=(TIMEOUT_CYCLES<=1)?1:$clog2(TIMEOUT_CYCLES);
    localparam [3:0] ERR_DECLARED_LENGTH=1,ERR_LENGTH=2,ERR_GOOD_FLAGS=3,
        ERR_BUSY_BEGIN=4,ERR_TIMEOUT=5,ERR_UNFRAMED_DATA=6;
    // Power-of-two stride keeps both byte ports in one true dual-port BRAM.
    (* ram_style="block" *) reg [7:0] packet_mem[0:(2<<AW)-1];
    reg [1:0] owned_q;
    reg receiving_q, capture_bank_q, drop_active_q;
    reg [15:0] received_q,declared_q,declared_last_q;
    reg [META_WIDTH-1:0] metadata_q;
    reg length_bad_q;
    reg [TW-1:0] timer_q;
    reg fifo_bank[0:1];
    reg head_q,tail_q;
    reg [1:0] count_q;
    reg [15:0] bank_length[0:1];
    reg [META_WIDTH-1:0] bank_metadata[0:1];
    reg draining_q,read_bank_q;
    reg [15:0] read_index_q,published_length_q;
    reg [META_WIDTH-1:0] published_metadata_q;
    reg out_valid_q,out_last_q;
    reg [7:0] out_data_q;
    wire release_output=out_valid_q&&out_ready&&out_last_q;
    wire free0=!owned_q[0]||(release_output&&read_bank_q==0);
    wire free1=!owned_q[1]||(release_output&&read_bank_q==1);
    wire chosen_bank=!free0;
    assign rx_begin_ready=rst_n&&!drop_active_q&&!receiving_q&&(free0||free1);
    assign rx_busy=receiving_q||drop_active_q||(|owned_q);
    wire accept_begin=rx_begin&&rx_begin_ready;
    wire legal_declared=rx_declared_len!=0&&rx_declared_len<=MAX_BYTES;
    wire required_good=(rx_good_flags&GOOD_REQUIRED_MASK)==GOOD_REQUIRED_MASK;
    wire [15:0] received_next=rx_data_valid&&received_q!=16'hffff ? received_q+1'b1 : received_q;
    // Compare the old byte count with a captured final index. Avoid
    // count increment -> two magnitude comparators -> metadata write enable.
    wire end_count_matches=rx_data_valid ? received_q==declared_last_q : received_q==declared_q;
    wire length_bad_next=length_bad_q||(rx_data_valid&&(received_q>=declared_q||received_q>=MAX_BYTES));
    wire finish_first=accept_begin&&legal_declared&&rx_end&&rx_data_valid&&rx_declared_len==1&&required_good;
    wire finish_more=receiving_q&&!drop_active_q&&!rx_begin&&rx_end&&
        !length_bad_q&&end_count_matches&&required_good;
    wire enqueue=finish_first||finish_more;
    wire enq_bank=finish_first?chosen_bank:capture_bank_q;
    wire dequeue=!draining_q&&count_q!=0;
    wire store_first=accept_begin&&legal_declared&&rx_data_valid;
    wire store_more=receiving_q&&!drop_active_q&&!rx_begin&&rx_data_valid&&!length_bad_q&&
        received_q<declared_q&&received_q<MAX_BYTES;
    wire [AW:0] write_address=store_first?{chosen_bank,{AW{1'b0}}}:{capture_bank_q,received_q[AW-1:0]};
    wire mem_read=rst_n&&draining_q&&(!out_valid_q||out_ready)&&read_index_q<published_length_q;
    always @(posedge clk)begin
        if(rst_n&&(store_first||store_more))packet_mem[write_address]<=rx_data;
        if(mem_read)out_data_q<=packet_mem[{read_bank_q,read_index_q[AW-1:0]}];
    end
    assign out_valid=rst_n&&out_valid_q;
    assign out_data=out_data_q;
    assign out_last=out_last_q;
    assign out_length=published_length_q;
    assign out_metadata=published_metadata_q;
    initial begin
        if(MAX_BYTES<1||MAX_BYTES>65535||META_WIDTH<1||GOOD_FLAG_WIDTH<1||
            GOOD_REQUIRED_MASK==0||TIMEOUT_CYCLES<1)$fatal(1,"invalid two-bank UDP parameters");
    end
    integer i;
    always @(posedge clk or negedge rst_n)begin
        if(!rst_n)begin
            owned_q<=0;receiving_q<=0;capture_bank_q<=0;drop_active_q<=0;
            received_q<=0;declared_q<=0;declared_last_q<=0;metadata_q<=0;length_bad_q<=0;timer_q<=0;
            head_q<=0;tail_q<=0;count_q<=0;draining_q<=0;read_bank_q<=0;
            read_index_q<=0;published_length_q<=0;published_metadata_q<=0;
            out_valid_q<=0;out_last_q<=0;committed_count<=0;rejected_event_count<=0;
            timeout_count<=0;last_reject_reason<=0;
            for(i=0;i<2;i=i+1)begin fifo_bank[i]<=0;bank_length[i]<=0;bank_metadata[i]<=0;end
        end else begin
            // Output state never changes because a new RX packet is rejected.
            if(mem_read)begin out_valid_q<=1;out_last_q<=read_index_q==published_length_q-1;read_index_q<=read_index_q+1'b1;end
            else if(out_valid_q&&out_ready)begin out_valid_q<=0;out_last_q<=0;end
            if(release_output)begin owned_q[read_bank_q]<=0;draining_q<=0;end
            if(dequeue)begin
                read_bank_q<=fifo_bank[head_q];published_length_q<=bank_length[fifo_bank[head_q]];
                published_metadata_q<=bank_metadata[fifo_bank[head_q]];
                read_index_q<=0;draining_q<=1;head_q<=~head_q;
            end
            if(enqueue)begin
                fifo_bank[tail_q]<=enq_bank;tail_q<=~tail_q;
                bank_length[enq_bank]<=finish_first?rx_declared_len:declared_q;
                bank_metadata[enq_bank]<=finish_first?rx_metadata:metadata_q;
                committed_count<=committed_count+1;
            end
            case({enqueue,dequeue})
                2'b10:count_q<=count_q+1'b1;
                2'b01:count_q<=count_q-1'b1;
                default:begin end
            endcase
            if(drop_active_q)begin
                if(rx_begin)begin rejected_event_count<=rejected_event_count+1;last_reject_reason<=ERR_BUSY_BEGIN;end
                if(rx_end)begin drop_active_q<=0;timer_q<=0;end
                else if(rx_data_valid||rx_begin)timer_q<=0;
                else if(timer_q==TIMEOUT_CYCLES-1)begin
                    drop_active_q<=0;timer_q<=0;rejected_event_count<=rejected_event_count+1;
                    timeout_count<=timeout_count+1;last_reject_reason<=ERR_TIMEOUT;
                end else timer_q<=timer_q+1'b1;
            end else if(accept_begin)begin
                timer_q<=0;capture_bank_q<=chosen_bank;received_q<=rx_data_valid?1:0;
                declared_q<=rx_declared_len;declared_last_q<=rx_declared_len-16'd1;metadata_q<=rx_metadata;length_bad_q<=0;
                if(!legal_declared)begin
                    drop_active_q<=!rx_end;rejected_event_count<=rejected_event_count+1;last_reject_reason<=ERR_DECLARED_LENGTH;
                end else if(rx_end)begin
                    if(finish_first)owned_q[chosen_bank]<=1;
                    else begin rejected_event_count<=rejected_event_count+1;
                        last_reject_reason<=rx_data_valid&&rx_declared_len==1?ERR_GOOD_FLAGS:ERR_LENGTH;end
                end else begin owned_q[chosen_bank]<=1;receiving_q<=1;end
            end else if(rx_begin)begin
                if(receiving_q)begin owned_q[capture_bank_q]<=0;receiving_q<=0;end
                drop_active_q<=!rx_end;timer_q<=0;rejected_event_count<=rejected_event_count+1;last_reject_reason<=ERR_BUSY_BEGIN;
            end else if(receiving_q)begin
                if(rx_data_valid||rx_end)begin
                    timer_q<=0;received_q<=received_next;length_bad_q<=length_bad_next;
                    if(rx_end)begin
                        receiving_q<=0;
                        if(!finish_more)begin owned_q[capture_bank_q]<=0;rejected_event_count<=rejected_event_count+1;
                            last_reject_reason<=length_bad_q||!end_count_matches?ERR_LENGTH:ERR_GOOD_FLAGS;end
                    end
                end else if(timer_q==TIMEOUT_CYCLES-1)begin
                    receiving_q<=0;owned_q[capture_bank_q]<=0;timer_q<=0;
                    rejected_event_count<=rejected_event_count+1;timeout_count<=timeout_count+1;last_reject_reason<=ERR_TIMEOUT;
                end else timer_q<=timer_q+1'b1;
            end else if(rx_data_valid||rx_end)begin
                drop_active_q<=!rx_end;timer_q<=0;rejected_event_count<=rejected_event_count+1;last_reject_reason<=ERR_UNFRAMED_DATA;
            end
        end
    end
endmodule
`default_nettype wire
