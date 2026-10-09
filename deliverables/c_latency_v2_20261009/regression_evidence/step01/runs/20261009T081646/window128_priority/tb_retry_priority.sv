`timescale 1ns/1ps
module tb_retry_priority;
  reg clk=0, rst_n=0;
  always #3.333 clk=~clk;
  evf2_result_window #(.RETRY_CYCLES(3000000)) dut(
    .clk(clk),.rst_n(rst_n),.frame_start(1'b0),.frame_session(128'd0),
    .frame_id(32'd0),.core_done(1'b0),.rd_busy(1'b0),.rd_valid(1'b0),.rd_data(8'd0),
    .control_valid(1'b0),.control_kind(2'd0),.control_session(128'd0),
    .control_frame(32'd0),.control_crc(32'd0),.control_metadata(96'd0),
    .control_count(8'd0),.control_window(8'd128),.proof_valid(1'b0),
    .proof_sequence(32'd0),.proof_crc(32'd0),.desc_ready(1'b0),
    .payload_rd_req(1'b0),.payload_rd_addr(10'd0)
  );
  integer wanted, count=0;
  // Deposit legal scheduler states at the falling edge. This microtest checks
  // actual RTL NBA priority, not end-to-end loss recovery or phase probability.
  task check(input integer timer, input integer request, input integer expect_pass,
             input integer expect_request, input integer boundary);
    begin
      @(negedge clk);
      dut.active=1;dut.negotiated=1;dut.base_q=0;
      dut.next_q=boundary ? 0 : 1;dut.scan_q=0;
      dut.filling_q=1;dut.pending_q=0;dut.read_request_q=0;dut.read_update_q=0;
      dut.retry_timer_q=timer;dut.retry_requested_q=request;dut.retry_pass_q=0;
      dut.desc_valid=0;dut.control_reply_q=0;
      dut.ready_q=0;dut.sent_q=0;dut.acked_q=0;
      @(posedge clk);#1;
      if(dut.retry_pass_q !== (expect_pass!=0) || dut.retry_requested_q !== (expect_request!=0))
        $fatal(1,"priority case failed timer=%0d request=%0d boundary=%0d pass=%0d pending=%0d",timer,request,boundary,dut.retry_pass_q,dut.retry_requested_q);
      count=count+1;
    end
  endtask
  initial begin
    wanted=1;
    repeat(3)@(negedge clk);rst_n=1;
    check(2999999,0,wanted,0,1); // same-cycle expiry and scan end
    check(2999998,0,0,0,1);      // not yet expired
    check(0,1,1,0,1);           // old queued request consumed
    check(2999999,1,1,0,1);     // queued and new request at boundary
    check(2999999,0,0,1,0);     // expiry during a pass remains queued
    check(0,0,0,0,1);           // quiet boundary
    $display("RETRY_PRIORITY_PASS fixed=%0d cases=%0d RTO=3000000 MAX_WINDOW=128",wanted,count);
    $finish;
  end
endmodule
