module tb_c_b_smoke;
    localparam integer IMG_W=6, IMG_H=5, OUT_W=12, OUT_H=10, STRIPE_H=4;
    localparam integer N_IN=IMG_W*IMG_H, N_OUT=OUT_W*OUT_H, MAX_CYC=100000;

    reg clk=0, rst_n=0, start=0, rb_enable=1;
    wire busy, done, uart_tx;
    wire [1:0] dbg_buf_state;
    wire [15:0] dbg_stripe_cnt, dbg_stripes_sent, dbg_in_x, dbg_in_y, dbg_out_x, dbg_out_y;
    wire [31:0] dbg_uart_bytes;
    wire dbg_proto_err, dbg_overflow_err, dbg_in_done, dbg_b_busy, dbg_b_done_seen;
    integer cycles=0, input_count=0, b_count=0, c_count=0, stripe_count=0, frame_count=0;
    integer errors=0; reg done_seen=0;

    always #5 clk=~clk;

    c_core #(
        .IMG_W(IMG_W), .IMG_H(IMG_H), .OUT_W(OUT_W), .OUT_H(OUT_H),
        .STRIPE_H(STRIPE_H), .PIXEL_W(8),
        .ROM_ADDR_W(6), .ROM_DEPTH(64), .ROM_INIT_MODE(1), .ROM_INIT_EN(0),
        .ROM_INIT_FILE(""), .CLK_HZ(1000), .UART_BAUD(100)
    ) dut (
        .clk(clk), .rst_n(rst_n), .start(start), .busy(busy), .done(done),
        .rb_enable(rb_enable), .uart_tx(uart_tx),
        .dbg_buf_state(dbg_buf_state), .dbg_stripe_cnt(dbg_stripe_cnt),
        .dbg_uart_bytes(dbg_uart_bytes), .dbg_stripes_sent(dbg_stripes_sent),
        .dbg_proto_err(dbg_proto_err), .dbg_overflow_err(dbg_overflow_err),
        .dbg_in_done(dbg_in_done), .dbg_b_busy(dbg_b_busy), .dbg_b_done_seen(dbg_b_done_seen),
        .dbg_in_x(dbg_in_x), .dbg_in_y(dbg_in_y), .dbg_out_x(dbg_out_x), .dbg_out_y(dbg_out_y)
    );

    always @(posedge clk) begin
        if (rst_n) begin
            if (dut.src_valid && dut.src_ready) input_count = input_count + 1;
            if (dut.b_out_valid && dut.out_ready) begin
                b_count = b_count + 1;
                if (dut.b_stripe_last) stripe_count = stripe_count + 1;
                if (dut.b_frame_last) frame_count = frame_count + 1;
            end
            if (dut.wr_push) c_count = c_count + 1;
        end
    end

    initial begin
        repeat (5) @(negedge clk);
        rst_n=1;
        repeat (2) @(negedge clk);
        start=1;
        @(negedge clk);
        start=0;
        while (!done_seen && cycles < MAX_CYC) begin
            @(negedge clk);
            cycles=cycles+1; if (done) done_seen=1;
        end
        repeat (2) @(negedge clk);
        if (!done_seen) begin $display("RESULT: FAIL timeout cycles=%0d",cycles); $finish; end
        if (input_count != N_IN) begin $display("FAIL input_count=%0d expected=%0d",input_count,N_IN); errors=errors+1; end
        if (b_count != N_OUT) begin $display("FAIL b_count=%0d expected=%0d",b_count,N_OUT); errors=errors+1; end
        if (c_count != N_OUT) begin $display("FAIL c_count=%0d expected=%0d",c_count,N_OUT); errors=errors+1; end
        if (stripe_count != 3 || frame_count != 1) begin $display("FAIL sideband stripe=%0d frame=%0d",stripe_count,frame_count); errors=errors+1; end
        if (!dbg_in_done || !dbg_b_done_seen) begin $display("FAIL completion in=%0d b_seen=%0d",dbg_in_done,dbg_b_done_seen); errors=errors+1; end
        if (dbg_proto_err || dbg_overflow_err) begin $display("FAIL protocol=%0d overflow=%0d",dbg_proto_err,dbg_overflow_err); errors=errors+1; end
        $display("counts in=%0d B_accept=%0d C_write=%0d stripes=%0d frames=%0d cycles=%0d",
                 input_count,b_count,c_count,stripe_count,frame_count,cycles);
        if (errors==0) $display("RESULT: PASS (C/B elastic boundary, real B, complete 6x5 frame)");
        else $display("RESULT: FAIL errors=%0d",errors);
        $finish;
    end

    initial begin
        #(MAX_CYC*10*2);
        $display("RESULT: FAIL hard timeout");
        $finish;
    end
endmodule