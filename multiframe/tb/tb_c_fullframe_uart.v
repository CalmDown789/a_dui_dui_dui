`timescale 1ns/1ps
`default_nettype none
// Full geometry C + exact B closure. UART DIV=1 accelerates simulation only;
// physical 921600-baud UART and framed loading have separate board gates.
module tb_c_fullframe_uart;
  localparam integer INPUT_BYTES=518400, OUTPUT_BYTES=2073600;
  reg clk=0;
  always #5 clk=~clk;
  reg rst_n=0, start=0, wr_en=0;
  reg [18:0] wr_addr=0;
  reg [7:0] wr_data=0;
  wire busy, done, uart_tx, proto_err, overflow_err, tx_busy, rb_busy;
  wire [31:0] bytes_sent;
  reg [7:0] input_pixels[0:INPUT_BYTES-1];
  reg [7:0] golden[0:OUTPUT_BYTES-1];
  integer frame=0, i, received=0, accepted=0, output_count=0;
  integer stripe_count=0, frame_last_count=0, done_count=0, cycles=0, fd;
  reg stalled=0;
  reg [9:0] held_output;
  c_core #(.IMG_W(960),.IMG_H(540),.OUT_W(1920),.OUT_H(1080),
    .STRIPE_H(64),.ROM_ADDR_W(19),.ROM_DEPTH(524288),.ROM_INIT_EN(0),
    .CLK_HZ(100000000),.UART_BAUD(100000000),.UART_DIV(1)) dut(
    .clk(clk),.rst_n(rst_n),.start(start),.busy(busy),.done(done),
    .rb_enable(1'b1),.uart_tx(uart_tx),.frame_wr_en(wr_en),
    .frame_wr_addr(wr_addr),.frame_wr_data(wr_data),
    .dbg_uart_bytes(bytes_sent),.dbg_proto_err(proto_err),
    .dbg_overflow_err(overflow_err),.dbg_uart_tx_busy(tx_busy),
    .dbg_readback_busy(rb_busy));
  always @(posedge clk) begin
    cycles=cycles+1;
    if (rst_n) begin
      if (proto_err || overflow_err) $fatal(1,"[FAIL] C error flag");
      if (wr_en && busy) $fatal(1,"[FAIL] write while computing");
      if (done) done_count=done_count+1;
      if (dut.in_valid && dut.in_ready) begin
        if (accepted>=INPUT_BYTES || dut.in_data !== input_pixels[accepted])
          $fatal(1,"[FAIL] full input stream pixel %0d",accepted);
        accepted=accepted+1;
      end
      if (stalled && (!dut.out_pipe_valid_q ||
          {dut.out_pipe_frame_last_q,dut.out_pipe_stripe_last_q,dut.out_pipe_data_q} !== held_output))
        $fatal(1,"[FAIL] elastic output unstable during backpressure");
      stalled=dut.out_pipe_valid_q && !dut.out_stream_ready;
      held_output={dut.out_pipe_frame_last_q,dut.out_pipe_stripe_last_q,dut.out_pipe_data_q};
      if (dut.out_pipe_valid_q && dut.out_stream_ready) begin
        if (output_count>=OUTPUT_BYTES || dut.out_pipe_data_q !== golden[output_count])
          $fatal(1,"[FAIL] B to C byte %0d",output_count);
        if (dut.out_pipe_stripe_last_q !== (((output_count+1) % (1920*64))==0 || output_count==OUTPUT_BYTES-1))
          $fatal(1,"[FAIL] stripe sideband at %0d",output_count);
        if (dut.out_pipe_frame_last_q !== (output_count==OUTPUT_BYTES-1))
          $fatal(1,"[FAIL] frame sideband at %0d",output_count);
        if (dut.out_pipe_stripe_last_q) stripe_count=stripe_count+1;
        if (dut.out_pipe_frame_last_q) frame_last_count=frame_last_count+1;
        output_count=output_count+1;
      end
      if (dut.tx_start && dut.tx_ready) begin
        if (received>=OUTPUT_BYTES || dut.tx_data !== golden[received])
          $fatal(1,"[FAIL] C UART accepted byte %0d",received);
        $fdisplay(fd,"%02x",dut.tx_data);
        received=received+1;
      end
      if (cycles % 1000000 == 0)
        $display("FULL_PROGRESS cycles=%0d frame=%0d input=%0d output=%0d uart=%0d",cycles,frame,accepted,output_count,received);
      if (cycles>=100000000) $fatal(1,"[FAIL] 100M-cycle full regression timeout");
    end
  end
  initial begin
    $readmemh("full_in.mem",input_pixels);
    $readmemh("full_out.mem",golden);
    repeat(8) @(negedge clk);
    rst_n=1;
    repeat(8) @(negedge clk);
    for(frame=0;frame<2;frame=frame+1) begin
      accepted=0; output_count=0; received=0; stripe_count=0; frame_last_count=0;
      fd=$fopen(frame==0 ? "actual_full0.mem" : "actual_full1.mem","w");
      for(i=0;i<INPUT_BYTES;i=i+1) begin
        @(negedge clk);wr_en=1;wr_addr=i;wr_data=input_pixels[i];
      end
      @(negedge clk);wr_en=0;start=1;
      @(negedge clk);start=0;
      wait(received==OUTPUT_BYTES);
      wait(!busy && !tx_busy && !rb_busy);
      repeat(8) @(negedge clk);
      $fclose(fd);
      if(accepted!=INPUT_BYTES || output_count!=OUTPUT_BYTES ||
         stripe_count!=17 || frame_last_count!=1 || done_count!=frame+1 ||
         bytes_sent!=(frame+1)*OUTPUT_BYTES)
        $fatal(1,"[FAIL] full frame counts frame=%0d done=%0d bytes=%0d stripes=%0d",frame,done_count,bytes_sent,stripe_count);
      $display("FULL_FRAME_PASS frame=%0d input=%0d output=%0d uart=%0d stripes=%0d no_reset=1",frame,accepted,output_count,received,stripe_count);
    end
    $display("RESULT: PASS 2 full-size C+B frames, official A Golden, no reset");
    $finish;
  end
endmodule
`default_nettype wire
