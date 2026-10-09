`timescale 1ns/1ps
module tb_window;
    `include "window_config.vh"
    reg clk=0;always #3.333 clk=~clk;
    reg rst_n=0,sv=0,sl=0,frame_start=0,core_done=0;reg[7:0]sd=0;reg[15:0]sn=0;
    reg[95:0]sm=96'h123456789abcdef012345678;reg[31:0]frame_id=0;
    wire sr,cv,cr,pq,pv,dv,dr,pr,pvalid,mv,ml,busy,release_frame,active,negotiated;
    wire[1:0]ck;wire[127:0]cs,ds;wire[31:0]cf,cc,ps,pc,df,dseq,doff,dc,dnext,dpc;
    wire[95:0]cm,dm,mm;wire[7:0]cn,cw,dt,pdata,md;wire[6:0]pi;wire[9:0]pa;
    wire[15:0]dst,dflags,dlen,mn;wire[31:0]base,next_q,reads,releases,rejects,retries;
    reg mr=0;integer cycle=0,current_frame=0,produced=0,consumed=0,coverage_count=0;
    integer offers=0,final_replies=0,packet_at=0,wire_file,begin_cycle=0;
    reg[PACKETS-1:0]coverage=0;reg[7:0]packet[0:1087];
    reg[7:0]golden[0:2*BYTES-1],requests[0:2000000];
    wire req,rbusy,rvalid;wire[7:0]rdata;wire wr_ready,wr_next,overflow;
    wire push=rst_n&&active&&produced<BYTES&&wr_ready&&(cycle%17!=3);
    wire[8:0]stripe_length=(BYTES-(produced/256)*256<256)?BYTES-(produced/256)*256:256;
    pingpong_buffer #(.WIDTH(64),.ROWS(4)) banks(.clk(clk),.rst_n(rst_n),.wr_push(push),
        .wr_data(golden[current_frame*BYTES+produced]),.wr_stripe_len(stripe_length),
        .wr_ready(wr_ready),.wr_ready_nxt(wr_next),.rd_req(req),.rd_avail(),.rd_valid(rvalid),
        .rd_data(rdata),.rd_start(),.rd_last(),.rd_len(),.rd_busy(rbusy),.buf_state(),.overflow_err(overflow));
    evf2_control_parser #(.OUTPUT_BYTES(BYTES),.MAX_WINDOW(W)) parser(.clk(clk),.rst_n(rst_n),
        .s_valid(sv),.s_ready(sr),.s_data(sd),.s_last(sl),.s_length(sn),.s_metadata(sm),
        .control_valid(cv),.control_ready(cr),.control_kind(ck),.control_session(cs),.control_frame(cf),
        .control_crc(cc),.control_metadata(cm),.control_count(cn),.control_window(cw),
        .proof_req(pq),.proof_index(pi),.proof_valid(pv),.proof_sequence(ps),.proof_crc(pc),.rejected_count(),.timeout_count());
    evf2_result_window #(.OUTPUT_BYTES(BYTES),.MAX_WINDOW(W),.RETRY_CYCLES(3000000)) win(.clk(clk),.rst_n(rst_n),
        .frame_start(frame_start),.frame_session(128'h000102030405060708090a0b0c0d0e0f),.frame_id(frame_id),.core_done(core_done),
        .rd_req(req),.rd_busy(rbusy),.rd_valid(rvalid),.rd_data(rdata),.control_valid(cv),.control_ready(cr),
        .control_kind(ck),.control_session(cs),.control_frame(cf),.control_crc(cc),.control_metadata(cm),
        .control_count(cn),.control_window(cw),.proof_req(pq),.proof_index(pi),.proof_valid(pv),.proof_sequence(ps),.proof_crc(pc),
        .desc_valid(dv),.desc_ready(dr),.desc_type(dt),.desc_status(dst),.desc_flags(dflags),.desc_length(dlen),
        .desc_session(ds),.desc_frame_id(df),.desc_sequence(dseq),.desc_offset(doff),.desc_frame_crc(dc),
        .desc_next_offset(dnext),.desc_payload_crc(dpc),.desc_metadata(dm),.payload_rd_req(pr),.payload_rd_addr(pa),
        .payload_rd_valid(pvalid),.payload_rd_data(pdata),.frame_release(release_frame),.active(active),.negotiated(negotiated),
        .read_bytes_count(reads),.release_count(releases),.rejected_count(rejects),.retransmitted_count(retries),
        .window_base(base),.window_next(next_q));
    evf2_response_serializer serializer(.clk(clk),.rst_n(rst_n),.desc_valid(dv),.desc_ready(dr),.busy(busy),
        .desc_type(dt),.desc_status(dst),.desc_flags(dflags),.desc_length(dlen),.desc_session(ds),.desc_frame_id(df),
        .desc_sequence(dseq),.desc_offset(doff),.desc_frame_bytes(BYTES),.desc_frame_crc(dc),.desc_next_offset(dnext),
        .desc_payload_crc(dpc),.desc_metadata(dm),.payload_rd_req(pr),.payload_rd_addr(pa),.payload_rd_valid(pvalid),
        .payload_rd_data(pdata),.m_valid(mv),.m_ready(mr),.m_data(md),.m_last(ml),.m_length(mn),.m_metadata(mm));
    reg[120:0]held;reg holding=0;
    always @(posedge clk)begin
        cycle<=cycle+1;
        if(rst_n)begin
            if(push)produced<=produced+1;
            if(req&&rbusy)begin if(consumed>=BYTES)$fatal(1,"read past output");consumed<=consumed+1;end
            if(overflow)$fatal(1,"stripe overwrite");
            if(next_q-base>W)$fatal(1,"window unbounded");
            if(holding&&(!mv||held!=={md,ml,mn,mm}))$fatal(1,"serializer stall changed bytes");
            holding<=mv&&!mr;held<={md,ml,mn,mm};
            if(mv&&mr)begin
                packet[packet_at]=md;$fwrite(wire_file,"%02x",md);
                if(ml)begin
                    if(packet_at+1!=mn)$fatal(1,"wire length");
                    $fwrite(wire_file,"\n");
                    if(packet[5]==8'h81)offers<=offers+1;
                    if(packet[5]==8'h89)final_replies<=final_replies+1;
                    if(packet[5]==8'h17)begin
                        if({packet[24],packet[25],packet[26],packet[27]}!==current_frame)$fatal(1,"old frame output");
                        if(!coverage[{packet[28],packet[29],packet[30],packet[31]}])begin
                            coverage[{packet[28],packet[29],packet[30],packet[31]}]<=1;coverage_count<=coverage_count+1;
                        end
                    end
                    packet_at<=0;
                end else packet_at<=packet_at+1;
            end
        end
    end
    always @(negedge clk)mr=rst_n&&(cycle%23!=0)&&(cycle%23!=1)&&(cycle%11!=3);
    task send_control(input integer at,n,bad_meta);
        integer k;
        begin
            for(k=0;k<n;k=k+1)begin
                @(negedge clk);while(!sr)@(negedge clk);sv=1;sd=requests[at+k];sl=k==n-1;sn=n;
                sm=bad_meta?96'hffffffffffffffffffffffff:96'h123456789abcdef012345678;
            end
            @(negedge clk);sv=0;sl=0;
        end
    endtask
    task wait_control_idle;
        begin repeat(3)@(negedge clk);while(!sr||cv)@(negedge clk);end
    endtask
    task wait_coverage(input integer n);begin while(coverage_count<n)@(negedge clk);end endtask
    task wait_base(input integer n);begin while(base<n)@(negedge clk);end endtask
    task launch(input integer f);
        begin
            @(negedge clk);current_frame=f;frame_id=f;produced=0;consumed=0;coverage=0;coverage_count=0;begin_cycle=cycle;
            frame_start=1;@(negedge clk);frame_start=0;
        end
    endtask
    initial begin
        $readmemh("window_golden.hex",golden);$readmemh("window_requests.hex",requests);
        wire_file=$fopen("wire_packets.txt","w");repeat(6)@(negedge clk);rst_n=1;
        `include "window_actions.vh"
        repeat(10)@(negedge clk);
        if(releases!=2||active||reads!=BYTES||consumed!=BYTES||retries!=0)$fatal(1,"window release/reads wrong");
        $fclose(wire_file);$display("EVF2_WINDOW_PASS bytes_per_frame=%0d frames=2 last_frame_cycles=%0d retries=%0d rejects=%0d",BYTES,cycle-begin_cycle,retries,rejects);$finish;
    end
    initial begin #1000000000;$fatal(1,"window timeout coverage=%0d base=%0d next=%0d",coverage_count,base,next_q);end
endmodule
