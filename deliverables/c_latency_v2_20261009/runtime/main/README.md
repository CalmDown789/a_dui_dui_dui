四步整合候选包

此包将第1步的RTL重试到期修补与第2～4步主机优化一起启用：直接解码EVF2、非阻塞IO、每16次采样一次细粒度计时。原始报文、CRC验证、逐帧计时和释放前日志检查仍完整执行。

运行入口：

```powershell
& C:\t6int09\main\run_integrated.ps1 -Mode Preflight
& C:\t6int09\main\run_integrated.ps1 -Mode Run
```

Run会加载本包新BIT至FPGA配置RAM，依次执行Smoke、Probe、Natural2和Natural16，并对实际原始报文独立审计。程序创建的硬件服务器在结束时停止；已有服务器保持运行。结果保存到本包attempts目录，每次使用新目录。

默认设置为150 MHz、输入窗口16、输出窗口128、非阻塞IO、sampled计时模式、采样间隔16。streaming/streaming_client.py保持已有API默认值，整合方案由lab/streaming_board_lab.py入口显式启用。

主机代码来自已检查的第4步候选，RTL来自已检查的第1步候选。implementation目录保存首次综合及增量布局失败证据，implementation_full保存完整布局布线及首轮时序检查，implementation_refine保存最终布线优化、时序、DRC和新BIT生成日志；provenance保存原包及分步候选的源身份。image与PACKAGE_MANIFEST.json绑定本包真实BIT和源文件。

测试结论见工作区output/INTEGRATED_STEPS01_04_20261009。此包用于当前用户授权的上板试验；本次结果只覆盖实际运行的协议与Golden字节验证，未计入PC4K和显示链路。
