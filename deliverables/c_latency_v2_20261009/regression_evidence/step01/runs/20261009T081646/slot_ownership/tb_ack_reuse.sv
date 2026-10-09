`timescale 1ns/1ps
module tb_ack_reuse;
 reg clk=0;always #3.333 clk=~clk;
 reg rst_n=0,frame_start=0,control_valid=0,desc_ready=1;
 reg[1:0]control_kind=1;
 wire control_ready,proof_req,proof_valid,desc_valid,active,negotiated,rd_req;
 wire[6:0]proof_index;wire[7:0]desc_type;wire[31:0]desc_sequence,window_base,window_next;
 reg proof_valid_q=0;reg[31:0]proof_sequence_q=0,proof_crc_q=0;reg rd_valid=0;
 assign proof_valid=proof_valid_q;
 localparam[127:0]SESSION=128'h000102030405060708090a0b0c0d0e0f;
 evf2_result_window #(.OUTPUT_BYTES(3072),.MAX_WINDOW(2),.RETRY_CYCLES(40))dut(
  .clk(clk),.rst_n(rst_n),.frame_start(frame_start),.frame_session(SESSION),.frame_id(0),.core_done(1'b0),
  .rd_req(rd_req),.rd_busy(1'b1),.rd_valid(rd_valid),.rd_data(8'h5a),
  .control_valid(control_valid),.control_ready(control_ready),.control_kind(control_kind),
  .control_session(SESSION),.control_frame(0),.control_crc(0),.control_metadata(96'd0),.control_count(8'd2),.control_window(8'd2),
  .proof_req(proof_req),.proof_index(proof_index),.proof_valid(proof_valid),.proof_sequence(proof_sequence_q),.proof_crc(proof_crc_q),
  .desc_valid(desc_valid),.desc_ready(desc_ready),.desc_type(desc_type),.desc_sequence(desc_sequence),
  .payload_rd_req(1'b0),.payload_rd_addr(10'd0),.active(active),.negotiated(negotiated),.window_base(window_base),.window_next(window_next));
 always @(posedge clk)begin
  rd_valid<=rst_n&&rd_req;
  proof_valid_q<=rst_n&&proof_req;
  if(proof_req)begin proof_sequence_q<=proof_index;proof_crc_q<=32'ha9da8aa6;end
 end
 task send_control(input[1:0]kind);
  begin @(negedge clk);control_kind=kind;control_valid=1;wait(control_ready);@(negedge clk);control_valid=0;
   repeat(2)@(negedge clk);end
 endtask
 integer cycles=0;
 always @(posedge clk)begin cycles<=cycles+1;if(cycles>20000)$fatal(1,"ACK_REUSE_TIMEOUT base=%0d next=%0d",window_base,window_next);end
 initial begin
  repeat(5)@(negedge clk);rst_n=1;
  send_control(1);wait(negotiated&&!desc_valid);@(negedge clk);frame_start=1;@(negedge clk);frame_start=0;
  wait(dut.sent_q==2'b11&&desc_valid&&desc_type==8'h17&&desc_sequence==0);
  @(negedge clk);desc_ready=0;
  // An old retry descriptor owns bank 0, so the first valid ACK cannot yet
  // release the base. The second ACK repeats the same valid proofs.
  send_control(2);if(window_base!=0||dut.acked_q!=2'b11)$fatal(1,"SETUP_DID_NOT_HOLD_ACKED_BANK");
  @(negedge clk);control_kind=2;control_valid=1;
  wait(proof_req&&proof_index==0);
  repeat(3)@(posedge clk);@(negedge clk);desc_ready=1;
  wait(control_ready);@(negedge clk);control_valid=0;
  repeat(8)@(negedge clk);
  if(dut.filling_q&&dut.fill_bank_q==0&&dut.acked_q[0])
   $fatal(1,"ACK_REUSE_OLD_PROOF_MARKED_NEW_FILL bank=0 base=%0d next=%0d",window_base,window_next);
  wait(window_next==3);repeat(6)@(negedge clk);
  if(window_base!=2||dut.acked_q[0]||!dut.ready_q[0])
   $fatal(1,"ACK_REUSE_UNPROVED_PACKET_FREED base=%0d next=%0d acked=%b ready=%b",window_base,window_next,dut.acked_q,dut.ready_q);
  $display("ACK_REUSE_PASS old_repeat_cannot_ack_new_packet cycles=%0d",cycles);$finish;
 end
endmodule
