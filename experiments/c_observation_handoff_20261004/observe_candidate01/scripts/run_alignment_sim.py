from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,time

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['bank16','multiframe','fullframe','controlled']);parser.add_argument('attempt');parser.add_argument('--optimization',choices=['0','1','2'],default='2');parser.add_argument('--wall-timeout',type=int,default=900);args=parser.parse_args()
if not args.attempt.replace('_','').isalnum():raise RuntimeError('Invalid attempt')
run=root/'sim'/f'{args.mode}_{args.attempt}'
if run.exists():raise RuntimeError('Run exists; evidence preserved')
run.mkdir();rtl=root/'overlay/multiframe/rtl';tb=root/'overlay/multiframe/tb';b=root/'b_reference'
vivado=Path(json.loads((root/'toolchain.json').read_text(encoding='utf-8'))['vivado_root']);bin=vivado/'bin'
env=os.environ.copy();env['XILINX_VIVADO']=str(vivado)
env['PATH']=os.pathsep.join([str(vivado/'bin'),str(vivado/'lib/win64.o'),str(vivado/'bin/unwrapped/win64.o'),env.get('PATH','')])
start=time.time();stage='preflight';log_records=[]
def tool(name,options,timeout,label=None):
    global stage
    stage=label or name;p=bin/f'{name}.bat';log=run/f'{stage}_stdout.txt'
    with log.open('wb') as out:
        process=subprocess.Popen(['cmd.exe','/d','/c',str(p),*map(str,options)],cwd=run,env=env,stdout=out,stderr=subprocess.STDOUT)
        try: code=process.wait(timeout=timeout)
        except BaseException:
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=out,stderr=subprocess.STDOUT,check=False)
            process.wait(timeout=30)
            raise
    log_records.append(dict(tool=stage,exit_code=code,log=str(log)))
    if code:raise RuntimeError(f'{stage} exited {code}; see {log}')
try:
    if args.mode=='bank16':
        top='tb_c_input_bank16'
        files=[rtl/'c_config.vh',rtl/'input_rom.v',rtl/'input_stream.v',tb/f'{top}.v']
    else:
        top='tb_c_fullframe_uart' if args.mode=='fullframe' else ('tb_c_controlled_pause' if args.mode=='controlled' else 'tb_c_multiframe_uart')
        rel=['experiments/l5_splitmem_20260924/rtl/b/fsrcnn_network_core.sv','rtl/b_real_ae29515/stream/fsrcnn_network_mem_top.sv','rtl/b_real_ae29515/stream/b_core_real.sv','experiments/l5_splitmem_20260924/rtl/b/fsrcnn_stream_layer.sv','rtl/b_real_ae29515/stream/window_stream_frontend.sv','rtl/b_real_ae29515/stream/window_kminus1_bram.sv','rtl/b_real_ae29515/stream/same_pad_raster.sv','experiments/l5_splitmem_20260924/rtl/b/elastic_fifo.sv','experiments/l5_splitmem_20260924/rtl/b/mac_issue_stage.sv','experiments/l5_splitmem_20260924/rtl/b/phase_mac_pipeline.sv','experiments/l5_splitmem_20260924/rtl/b/phase_accumulator_36.sv','rtl/b_real_ae29515/stream/eight_phase_issue.sv','rtl/b_real_ae29515/stream/pixel_shuffle2x_row_banks.sv','experiments/l5_splitmem_20260924/rtl/b/vector_postprocess_shared.sv','experiments/l5_splitmem_20260924/rtl/b/prelu_requantize.sv']
        bfiles=[b/r for r in rel]
        tool('xvlog',['--nolog','--work','worklib','-d','C_SIM','-d','C_USE_B_REAL','-sv',*bfiles],120,label='xvlog_b')
        files=[rtl/n for n in ['c_config.vh','input_rom.v','input_stream.v','stripe_buffer.v','pingpong_buffer.v','output_stream.v','uart_tx.v','readback_ctrl.v','c_ctrl.v','b_core_stub.v','b_core_if.v','c_core.v','c_observation.v','c_protocol_assertions.v','uart_rx.v','uart_frame_loader.v','c_multiframe_top.v']]+[tb/f'{top}.v']
        for p in (b/'rom/member_a_d16_s8_m1_c16').glob('*_packed.mem'):shutil.copyfile(p,run/p.name)
        refs=root/'fixtures/simulation'
        for name in (['full_in.mem','full_out.mem'] if args.mode=='fullframe' else ['tv_impulse_in.mem','tv_impulse_out.mem','tv_ramp_in.mem','tv_ramp_out.mem']):shutil.copyfile(refs/name,run/name)
    manifest_files=(bfiles if args.mode!='bank16' else [])+files+list(run.glob('*.mem'))
    (run/'source_manifest.json').write_text(json.dumps([dict(path=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in manifest_files],indent=2)+'\n',encoding='utf-8')
    tool('xvlog',['--nolog','--work','worklib','--include',rtl,'-d','C_SIM','-d','C_USE_B_REAL',*files],120,label='xvlog_c')
    tool('xelab',['--nolog','-O'+args.optimization,f'worklib.{top}','-s',top],120)
    # Use the installed 2025.2 launchers/runtime; no copied 2022.2 DLLs.
    tool('xsim',[top,'-runall'],args.wall_timeout)
    text=(run/'xsim_stdout.txt').read_text(encoding='utf-8',errors='replace')
    marker='RESULT: PASS bank16 writes' if args.mode=='bank16' else ('RESULT: PASS 2 full-size C+B frames' if args.mode=='fullframe' else ('RESULT: PASS controlled pause with two consecutive byte-exact UART frames' if args.mode=='controlled' else 'RESULT: PASS 2 consecutive UART frames'))
    if marker not in text or '[FAIL]' in text:raise RuntimeError('Required simulation PASS missing or FAIL recorded')
    result=dict(status='PASS',tool_version='2025.2',mode=args.mode,optimization=args.optimization,wall_timeout_s=args.wall_timeout,elapsed_s=round(time.time()-start,3),logs=log_records)
except Exception as error:
    result=dict(status='FAIL',tool_version='2025.2',mode=args.mode,stage=stage,reason=str(error),elapsed_s=round(time.time()-start,3),logs=log_records,impact='Only isolated simulation; no synthesis or hardware action.')
    (run/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result));raise
(run/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
