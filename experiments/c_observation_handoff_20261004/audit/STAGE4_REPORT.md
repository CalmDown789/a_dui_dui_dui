阶段 4 报告：C-B 内部握手、侧带、错误与帧快照

状态：PASS。实现和生成证据只在隔离候选目录 observe_candidate01 内；原始 C 工程和冻结 C 快照没有被修改。

固定输入和来源

- B RTL 固定提交：6cc8ea4173d2a720f741e80b7cbd9279558ee93a。
- A 输入来源固定提交：98c82f394bdfba85bc2959bede9760edc4d6862f。
- 隔离候选 C 来源：冻结目录 _c2025_2_validation_20261004_02。B 接口包装器的 pinned 版本差异已明确列在 candidate_delta_stage4.json。

完成项

- C→B 与 B→C 握手、B 的 stripe/frame 侧带接受数、错误状态、UART 字节增量、末输入/输出周期、core_done 区间、帧级停顿交集、数据保持违例以及受控暂停计数都映射到 934 位记录；signal_map.json 验证为 31 字段、934 位。
- 16 个槽按帧完成次序保留，不覆盖旧槽；容量后置 snapshot_overflow。自检使用 2 槽参数验证槽保留和容量溢出。
- session_done 接既有 loader frame_done。loader 只在 core_done_seen、core_busy 低、输出字节数正确、UART TX 空闲和 readback 空闲时结束。
- OBS_TEST_PAUSE_ENABLE 默认 0；功能回归不受暂停影响。受控暂停只在明确设为 1 的候选测试或调试构建生效。VIO 输出 5 位初始化为 0。
- Vivado 2025.2 生成 ILA 6.2/VIO 3.0。ILA 为 10 个探针，宽度 1/934/4/1/1/1/1/1/1/1、深度 1024、时钟 150 MHz；VIO 输入为 256/256/256/166/1/5，输出 5 位且 INIT=0。生成模板已与合成包装器实例化端口逐一核对，包装器在 xvlog/xelab 黑盒接口检查中通过。
- 观察器独立 xsim 自检覆盖首拍和末拍握手、侧带/数据保持、故意违例检测、stall/joint-stall、粘滞/累计错误取样、UART idle 快照、core_done 与 session_done 分离、周期计数、暂停计数、两槽保留及溢出，结果 PASS。

发现并保留的非通过尝试

- ILA 深度 16 不在 Vivado 2025.2 支持范围，工具报告最小深度为 1024；随后按最低合法值生成。
- VIO 单输入 934 位超过其 1..256 位范围；快照拆成四个数据片段，并单独暴露 valid/count。
- ILA 只设置周期仍留下 200 MHz 生成元数据；最终配置同时明确设置 C_CLK_FREQ=150 和 C_CLK_PERIOD=6.666667 ns，生成核心元数据验证为 150 MHz/6.667 ns。
- 第一次自检释放拍意外改变 frame_last，按监视器定义形成了第二次保持违例；已保存失败证据，修正向量后通过。
- 第一次包装器 elaboration 的黑盒桩缺少 timescale；保留失败日志，添加 timescale 后重跑通过。

保护检查

阶段 4 后校验直接重哈希冻结源 22 项、原始 C 非忽略文件 333 项和原始 C Git index。全部与既有收据一致；阶段 4 没有在原始 C 仓库运行 Git 命令，也没有改动它的暂存/未暂存内容。

主证据路径

- 契约：contracts/OBSERVATION_SPEC.md
- 位映射和源代码哈希/行号：contracts/signal_map.json
- 候选差异：audit/candidate_delta_stage4.json
- 原始 C 与冻结快照保护复核：audit/stage4_preservation_postcheck.json
- ILA/VIO 配置、端口宽度、生成元数据与文件哈希：audit/debug_ip_capability.json
- 观察器自检：observe_candidate01/sim/observe_selfcheck_attempt02/result.json 和 xsim_stdout.txt
- 包装器端口 elaboration：observe_candidate01/sim/synth_wrapper_compile_attempt02/result.json
- 最终 IP 生成：observe_candidate01/ipgen_attempt06/vivado.log、vivado.jou、result.json

阶段 5 已开始：使用真实 B 的 96×54 两帧 C-B-C UART 用例，在 OBS_TEST_PAUSE_ENABLE=1 的隔离仿真中短暂强制 B 输出阻塞，并要求两帧仍与 Golden 逐字节一致，同时快照报告非零 forced-block 计数且 hold violation 为零。此项尚未登记通过。
