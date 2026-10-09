`timescale 1ns/1ps
module tb_duplicate_suppression;
 parameter integer RETRY=3000000, ACK_DELAY=40000, EXPECT_DUPLICATES=0, LOST_PROOF=1, CLOCK_WRAP=0;
 reg clk=0;always #3.333 clk=~clk;
 reg rst_n=0,frame_start=0,control_valid=0,desc_ready=0,rd_valid=0;
 reg[1:0]control_kind=1;reg[7:0]control_count=1;
 reg[31:0]control_crc=0,frame_id=0;
 reg proof_valid=0;reg[31:0]proof_sequence=0,proof_crc=0,proof_q=0;
 wire control_ready,proof_req,desc_valid,active,negotiated,rd_req,frame_release;
 wire[6:0]proof_index;wire[7:0]desc_type;
 wire[31:0]desc_sequence,base,next_q,rejected,retries;
 localparam[127:0]SESSION=128'h000102030405060708090a0b0c0d0e0f;
 evf2_result_window #(.OUTPUT_BYTES(4096),.MAX_WINDOW(2),.RETRY_CYCLES(RETRY))dut(
  .clk(clk),.rst_n(rst_n),.frame_start(frame_start),.frame_session(SESSION),.frame_id(frame_id),.core_done(1'b1),
  .rd_req(rd_req),.rd_busy(1'b1),.rd_valid(rd_valid),.rd_data(8'h5a),
  .control_valid(control_valid),.control_ready(control_ready),.control_kind(control_kind),
  .control_session(SESSION),.control_frame(frame_id),.control_crc(control_crc),.control_metadata(96'd0),
  .control_count(control_count),.control_window(8'd2),
  .proof_req(proof_req),.proof_index(proof_index),.proof_valid(proof_valid),
  .proof_sequence(proof_sequence),.proof_crc(proof_crc),
  .desc_valid(desc_valid),.desc_ready(desc_ready),.desc_type(desc_type),.desc_sequence(desc_sequence),
  .payload_rd_req(1'b0),.payload_rd_addr(10'd0),.frame_release(frame_release),.active(active),.negotiated(negotiated),
  .window_base(base),.window_next(next_q),.rejected_count(rejected),.retransmitted_count(retries));
 integer cycles=0,serializer_delay=0,frame_number=0,q;
 integer copies[0:3],last_finished[0:3],first_finished[0:3];
 integer observed_duplicates=0,minimum_retry_spacing=2147483647;
 reg first_zero=1;
 always @(posedge clk)begin
  cycles<=cycles+1;
  if(dut.active&&dut.retry_timer_q==RETRY-1&&!desc_valid&&dut.scan_q>=next_q)
   $display("EXPIRY_COLLISION cycle=%0d base=%0d next=%0d retry_requested=%0d retry_pass=%0d",cycles,base,next_q,dut.retry_requested_q,dut.retry_pass_q);if(cycles>20000000)$fatal(1,"FIXTURE_TIMEOUT base=%0d next=%0d retry_requested=%0d retry_pass=%0d retries=%0d",base,next_q,dut.retry_requested_q,dut.retry_pass_q,retries);
  rd_valid<=rst_n&&rd_req;proof_valid<=rst_n&&proof_req;
  if(proof_req)begin proof_sequence<=proof_q;proof_crc<=32'ha9da8aa6;end
  if(desc_valid&&desc_ready&&desc_type==8'h17)begin
   if(copies[desc_sequence]!=0)begin
    observed_duplicates=observed_duplicates+1;
    if(cycles-last_finished[desc_sequence]<minimum_retry_spacing)
      minimum_retry_spacing=cycles-last_finished[desc_sequence];
    if(!EXPECT_DUPLICATES&&cycles-last_finished[desc_sequence]<RETRY)
      $fatal(1,"EARLY_RETRANSMISSION q=%0d age=%0d RTO=%0d",desc_sequence,cycles-last_finished[desc_sequence],RETRY);
   end else first_finished[desc_sequence]=cycles;
   copies[desc_sequence]=copies[desc_sequence]+1;
   last_finished[desc_sequence]=cycles;
  end
 end
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
 task send_control(input[1:0]kind,input[31:0]sequence_q);
  begin
   @(negedge clk);proof_q=sequence_q;control_kind=kind;control_valid=1;
   wait(control_ready);@(negedge clk);control_valid=0;repeat(3)@(negedge clk);
  end
 endtask
 initial begin
  for(q=0;q<4;q=q+1)begin copies[q]=0;last_finished[q]=0;first_finished[q]=0;end
  repeat(5)@(negedge clk);rst_n=1;
  send_control(1,0);wait(negotiated&&!desc_valid);
  for(frame_number=0;frame_number<2;frame_number=frame_number+1)begin
   for(q=0;q<4;q=q+1)begin copies[q]=0;last_finished[q]=0;first_finished[q]=0;end
   @(negedge clk);frame_id=frame_number;frame_start=1;@(negedge clk);frame_start=0;
   if(CLOCK_WRAP)begin
    // Source-bound candidate wrap exercise, before the first serializer completion.
    dut.tx_clock_q=32'hfffe0000;
   end
   for(q=0;q<4;q=q+1)begin
    wait(copies[q]>=1);
    if(LOST_PROOF&&q==1)wait(copies[q]>=2);
    else wait(cycles>=first_finished[q]+ACK_DELAY);
    send_control(2,q);wait(base>=q+1);
   end
   control_crc=~dut.rolling_crc_q;
   send_control(3,0);wait(!active);repeat(3)@(negedge clk);
  end
  if(EXPECT_DUPLICATES&&observed_duplicates==0)$fatal(1,"BASELINE_DID_NOT_REPRODUCE");
  if(!EXPECT_DUPLICATES&&!LOST_PROOF&&observed_duplicates!=0)$fatal(1,"HEALTHY_PATH_DUPLICATES count=%0d",observed_duplicates);
  if(LOST_PROOF&&observed_duplicates==0)$fatal(1,"LOST_PROOF_NOT_RECOVERED");
  if(rejected!=0||dut.release_count!=2)$fatal(1,"CONTROL_OR_FRAME_RELEASE_FAILURE");
  $display("DUPLICATE_SUPPRESSION_PASS baseline=%0d lost_proof=%0d wrap=%0d duplicates=%0d min_retry_spacing_cycles=%0d RTO=%0d frames=2",EXPECT_DUPLICATES,LOST_PROOF,CLOCK_WRAP,observed_duplicates,minimum_retry_spacing,RETRY);
  $finish;
 end
endmodule
