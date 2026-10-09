`timescale 1ns/1ps
module tb_retry_age_and_stale_ack;
 reg clk=0;always #3.333 clk=~clk;
 reg rst_n=0,frame_start=0,control_valid=0,desc_ready=0,rd_valid=0;
 reg[1:0]control_kind=1;reg[7:0]control_count=1;
 reg proof_valid=0;reg[31:0]proof_sequence=0,proof_crc=0;
 reg[31:0]proofs[0:1];
 wire control_ready,proof_req,desc_valid,active,negotiated,rd_req;
 wire[6:0]proof_index;wire[7:0]desc_type;
 wire[31:0]desc_sequence,window_base,window_next,rejected_count,retransmitted_count;
 localparam[127:0]SESSION=128'h000102030405060708090a0b0c0d0e0f;
 evf2_result_window #(.OUTPUT_BYTES(3072),.MAX_WINDOW(2),.RETRY_CYCLES(150000))dut(
  .clk(clk),.rst_n(rst_n),.frame_start(frame_start),.frame_session(SESSION),.frame_id(32'd0),.core_done(1'b0),
  .rd_req(rd_req),.rd_busy(1'b1),.rd_valid(rd_valid),.rd_data(8'h5a),
  .control_valid(control_valid),.control_ready(control_ready),.control_kind(control_kind),
  .control_session(SESSION),.control_frame(32'd0),.control_crc(32'd0),.control_metadata(96'd0),
  .control_count(control_count),.control_window(8'd2),
  .proof_req(proof_req),.proof_index(proof_index),.proof_valid(proof_valid),
  .proof_sequence(proof_sequence),.proof_crc(proof_crc),
  .desc_valid(desc_valid),.desc_ready(desc_ready),.desc_type(desc_type),.desc_sequence(desc_sequence),
  .payload_rd_req(1'b0),.payload_rd_addr(10'd0),.active(active),.negotiated(negotiated),
  .window_base(window_base),.window_next(window_next),.rejected_count(rejected_count),
  .retransmitted_count(retransmitted_count));
 integer cycles=0,sent0=0,sent1=0,sent2=0;
 integer serializer_delay=0;reg first_zero=1;
 real first_one_ns=0,second_one_ns=0;
 always @(posedge clk)begin
  cycles<=cycles+1;if(cycles>600000)$fatal(1,"FIXTURE_TIMEOUT");
  rd_valid<=rst_n&&rd_req;proof_valid<=rst_n&&proof_req;
  if(proof_req)begin proof_sequence<=proofs[proof_index];proof_crc<=32'ha9da8aa6;end
  if(desc_valid&&desc_ready&&desc_type==8'h17)begin
   if(desc_sequence==0)sent0<=sent0+1;
   if(desc_sequence==1)begin
    sent1<=sent1+1;
    if(sent1==0)first_one_ns=$realtime;
    if(sent1==1)second_one_ns=$realtime;
   end
   if(desc_sequence==2)sent2<=sent2+1;
  end
 end
 // A serializer owns a descriptor until the full output packet completes.
 // Stall the first one past one global expiry, then charge 9.5us per packet.
 always @(negedge clk)begin
  if(!rst_n||!desc_valid)begin desc_ready=0;serializer_delay=0;end
  else if(desc_type!=8'h17)desc_ready=1;
  else if(desc_ready)begin desc_ready=0;serializer_delay=0;end
  else begin
   serializer_delay=serializer_delay+1;
   if(first_zero&&desc_sequence==0)begin
    if(serializer_delay>=190000)begin desc_ready=1;first_zero=0;end
   end else if(serializer_delay>=1425)desc_ready=1;
  end
 end
 task send_control(input[1:0]kind,input[7:0]count,input[31:0]a,input[31:0]b);
  begin
   @(negedge clk);proofs[0]=a;proofs[1]=b;control_kind=kind;control_count=count;control_valid=1;
   wait(control_ready);@(negedge clk);control_valid=0;repeat(3)@(negedge clk);
  end
 endtask
 integer rejection_before;
 initial begin
  repeat(5)@(negedge clk);rst_n=1;
  send_control(1,1,0,0);wait(negotiated&&!desc_valid);
  @(negedge clk);frame_start=1;@(negedge clk);frame_start=0;
  wait(sent1>=2);
  if(second_one_ns-first_one_ns<999900)$fatal(1,"PER_PACKET_AGE_WAS_NOT_ENFORCED");
  $display("ORIGINAL_RTL_RETRY_AGE first_q1_ns=%0.3f second_q1_ns=%0.3f age_ns=%0.3f retry_cycles=150000",first_one_ns,second_one_ns,second_one_ns-first_one_ns);
  send_control(2,1,0,0);wait(window_base==1&&window_next==3&&sent2>=1);
  rejection_before=rejected_count;
  // q0's bank now belongs to q2. Mixing its old valid CRC with q1 rejects
  // the entire proof batch; q1 must remain unacknowledged.
  send_control(2,2,0,1);
  if(rejected_count!=rejection_before+1||dut.acked_q[1]||window_base!=1)
   $fatal(1,"STALE_MIXED_BATCH_NOT_REJECTED_ATOMICALLY");
  send_control(2,1,1,0);wait(window_base==2);
  send_control(2,1,2,0);wait(window_base==3);
  $display("AGE_GUARD_CAUSAL_PASS bounded_retry_and_atomic_stale_batch_reject retransmitted=%0d",retransmitted_count);
  $finish;
 end
endmodule
