# C → B：内部观测候选的时序定位与修复交接

日期：2026-10-04，北京时间。交付仓库：`CalmDown789/a_dui_dui_dui`，交接发布分支：`c-side-latest`。

## 1. 交接目标与当前结论

请 B 的模型接手 **C 内部观测候选的根因定位、最小修正、功能回归和完整板级实现验证**，把可审查的结果交还 C。B 不需要开发板即可进行上述软件工作，但需要 Vivado/XSim 2025.2、目标器件支持和有效工具条件。最终新版本的内部观测、受控背压与 UART 多帧板测由 C 在实际开发板上执行。

**已有多帧板测通过，不应重新登记为未完成。** `_c2025_2_validation_20261004_02` 是已通过的冻结基线；`observe_candidate01` 是新增调试硬件的独立候选。候选时序失败不推翻基线，也不能继承基线的板测通过。当前任务不是重新开发 UART 多帧通路，也不是优化 200 MHz。

本交接发布源码与既有证据，没有执行新一轮 HDL 修改、Vivado 实现或开发板烧录。B 的模型尚需由使用者在自己的环境中启动；发布交接材料不等于模型已开始运行。

## 2. 固定版本、保护范围与目录

| 项目 | 固定值或位置 |
|---|---|
| B 来源 | `6cc8ea4173d2a720f741e80b7cbd9279558ee93a`，不得改用当前分支最新提交 |
| A 来源 | `98c82f394bdfba85bc2959bede9760edc4d6862f`；复用已校验向量与 Golden |
| 工具 | Vivado/XSim 2025.2，现有 Windows 报告 SW Build 6299465 |
| 器件 | `xc7a200tfbg484-2` |
| 候选顶层 | `c_multiframe_synth_top`；综合定义 `C_USE_B_REAL` |
| 时钟 | 板输入 50 MHz；核 150 MHz 或 100 MHz，MMCM divide 分别 8.0/12.0；UART 参数同步传播 |
| 原 C 工程 | `C:\Users\Administrator\WorkBuddy\srtp\c_side`；已有暂存/未暂存修改必须保留 |
| 冻结基线 | `C:\Users\Administrator\WorkBuddy\srtp\_c2025_2_validation_20261004_02`；只读 |
| 原失败候选 | `C:\Users\Administrator\WorkBuddy\srtp\_c_b_remaining_20261004_01\observe_candidate01`；失败产物只读 |
| 云端工作材料 | 仓库 `experiments/c_observation_handoff_20261004/`，以下简称 `H` |

`H/observe_candidate01/` 保存候选 C RTL、完整 C XDC、测试台、脚本、仿真向量、B 精确依赖副本及生成 IP 的 XCI；`H/baseline/` 保存基线 C overlay、构建脚本和板测记录；`H/contracts/` 保存 934 位快照契约与映射；`H/audit/` 保存进度、分析与来源记录。板测会话与烧录收据在 `H/baseline_board_evidence.zip`；完整基线/失败时序报告分别在 `baseline_vivado_reports.zip` 和 `candidate_failure_reports.zip`，按 README 解压后即可使用下文路径。原始 UART 图像文件和两档基线 bitstream 保留在 C 本地，不在本交接包内。逐文件 SHA-256 在 `H/PACKAGE_MANIFEST.json`。

本包不携带大体积 DCP。失败 DCP 本地仍保留：150 MHz SHA-256 `F0B6873F946FD4305E55A4950B53F96C281C66E7BCA7A7E573A531E917BEDAFC`；100 MHz SHA-256 `74C10A5CDD625EB59AEFB47074FED2146503823E7A2DC8B4E83B59017A827541`。若模型需要 Tcl 实时查询网表，可用包内源码新建实现，或向 C 请求对应 DCP，不得冒充已做过查询。

## 3. 已完成结果，可复用

| 构建/验证 | 实测结果 | 包内证据 |
|---|---|---|
| 2025.2 基线 100 MHz | WNS +0.517 ns、WHS +0.014 ns，TNS/THS=0；上板四帧全部 bit-exact | `baseline/audit/EXECUTION_REPORT_2026-10-04.md`，`baseline/board/100_attempt01/` |
| 2025.2 基线 150 MHz | 正式约束 WNS +0.400 ns、WHS +0.036 ns；额外 +0.300 ns 压力 WNS +0.100 ns；上板四帧和连续 16 帧全部 bit-exact | `baseline/board/150_attempt01/`、`150_attempt02/`，基线 route/bitgen 原始报告 |
| 连续 16 帧 | 四种不同 960×540 输入各重复四次；ID 0–15；帧间无复位；每帧输出 2,073,600 字节，失配 0；总主机时间 453.929 s | `baseline/board/150_attempt02/capture/session.json`、`input_sequence.json`，ZIP 中逐帧返回长度/哈希与对拍收据；原始返回保留在 C 本地 |
| 基线完整双帧仿真 | 两帧各输入 518,400、输出 2,073,600；全部匹配 Golden；2025.2 PASS | `baseline/sim/fullframe_attempt02/` |
| 冷上电恢复、S0 空闲复位恢复 | 各四帧全部 bit-exact；前者为上电后 JTAG 重配置，后者没有重配置 | `baseline/board/150_coldpower_attempt01/`、`150_buttonreset_attempt01/` |
| 阶段 0–2 | 输入固定与原 C 保护、历史证据重哈希/PC 离线回放、B +0.492 ns 实验复现/审计完成 | `audit/progress.json`、`sequence_validation.json`、B 复现实验审计 |
| 阶段 3 | 复位警告盘点完成；结构风险仍 OPEN，不能用板测成功消除 | `audit/reset_disposition.md`、`reset_stage3_validation.json`、`baseline/audit/RESET_WARNING_REVIEW_2026-10-04.md` |
| 阶段 4 | 观察器自检、31 字段/934 位映射、ILA/VIO 生成与接口检查 PASS | `audit/STAGE4_REPORT.md`、`contracts/`、候选自检日志 |
| 阶段 5 | 真实固定 B，两帧 96×54；每帧注入 16 周期强制背压；两帧输出各 20,736 字节，Golden 0 失配；计数正确且 hold violation=0 | `audit/STAGE5_REPORT.md`、`observe_candidate01/sim/controlled_observe03/` |

基线 150 MHz bit SHA-256：`93dd60cffbefa43f6ab9f49697ff1d3f1ab6657445d01552c88842b6bc0760f6`；100 MHz：`524f72bc8ca01388f7305dbb02c48d5f1c68e1abe51900ce6c3738e667b80c3c`。计时为主机传输/接收时间，不代表 CNN 核心周期、实时播放帧率或 30 fps。

## 4. 新增内容与已确认失败

新增 `c_observation`：输入/输出握手计数，stripe/frame sideband 接受计数，多项 64 位周期与停顿计数，阻塞期间数据/侧带保持检查，错误快照，16×934 位帧记录。顶层增加 ILA、VIO 和可选暂停门控。原 UART 多帧、输入缓存、输出回读和一拍弹性寄存器是基线已有功能。

ILA：10 探针、1024 深度，其中 probe1=934 位、一个 match unit、输入流水级为 0。VIO：快照拆成 256/256/256/166 位输入，另有 valid/count；5 位输出低四位选槽，最高位申请暂停，INIT=0。两次失败的完整实现均用 `OBS_TEST_PAUSE_ENABLE=0`，因此不能把“暂停没有释放”当成当前失败原因。

| 观测候选 | WNS / TNS | 失败 setup 端点 | WHS / THS | 布线与 DRC |
|---|---:|---:|---|---|
| 150 MHz，恢复原约束 | −6.984 / −27871.592 ns | 33,451 | +0.016 / 0 ns | 107,867 全部布线；route errors=0；DRC Error=0 |
| 100 MHz，恢复原约束 | −3.790 / −3293.397 ns | 2,862 | +0.036 / 0 ns | 107,622 全部布线；route errors=0；DRC Error=0 |

报告在 `H/observe_candidate01/impl/board150_candidate_attempt06/reports/` 与 `board100_candidate_attempt01/reports/`。时钟周期、自动派生 MMCM、原 user uncertainty 恢复、内部约束覆盖均检查过。工具正常结束不等于时序 PASS。此候选没有生成 BIT、没有上板。

已确认的贡献路径：

1. **ILA 内部最差路径**：100 MHz 数据延迟 13.179 ns，117 CARRY4 + 1 SRLC32E；150 MHz 13.191 ns，同样 118 级。宽探针触发/匹配是合理假设，但加密 IP 内部名称屏蔽，尚未证明确切内部运算。不能直接写“已确认是 934 位比较器”。
2. **C 观测计数器**：150 MHz 有多条 `frame_start` 到 64 位计数器高位的约 12.1–12.3 ns 路径，兼有进位链与约 10 ns 布线延迟。
3. **未变 B 代码的高扇出物理实现**：100 MHz 的 L5 `pending1_reg` → `win/shift_reg[*]/CE`，负载 6,406，数据 12.522 ns，其中布线 12.089 ns，slack −2.754 ns。B 独立构建中同源控制被复制，其中一个副本网负载 228、布线 5.276 ns、slack +0.526 ns。为什么集成后复制程度不同仍需隔离；B 的 `c_synth_top` 与 C 完整多帧顶层不是同一设计。

## 5. B 执行阶段：每阶段必须留下产物、门槛与证据

### T0：接收、核验与工具盘点（不需要板）

阅读本书、`H/README.md`、`H/contracts/OBSERVATION_SPEC.md` 和固定 B 文档 `docs/MEMBER_B_TO_C_BOARD_VALIDATION_2026-09-26.md`。运行包哈希检查，记录 Git HEAD、B 精确提交、工具版本、目标器件支持、系统/内存/磁盘、能否运行 XSim/实现。有工具则继续；没有工具仍可完成代码审查和补丁，但将物理验证明确登记为 NOT_RUN。

产物：`results/T0_environment.json`、`source_manifest.json`。通过：源码/ROM/XDC/向量全部匹配来源，完整固定 B 层级可选中；不以当前 B 分支 HEAD 替代固定提交。已通过基线不用重复上板或重复长仿真。

### T1：根因隔离（不需要板）

先复用现有原候选失败报告与基线 PASS 报告。设计少量、单一变量的诊断构建：保留观察器及可读取快照而移除 ILA；必要时做受控小型 ILA 独立试验，对比宽探针的数据采集与触发匹配配置；检查计数器/frame_start 路径及 B `pending1` 的复制、扇出、布局和最差布线。诊断构建均不得作为交付 PASS。

尤其核对去掉消费者后观察器是否被综合优化掉；若计数器消失，必须在结果中标明，不能把“整个观测器被消除”当成其时序修复。每次只变一个诊断因素，保持器件、完整 C XDC、频率、固定 B 和实现策略可比。

产物：`results/T1_root_cause.md`、`diagnostic_matrix.csv`、每构建源/IP 参数清单、综合层级与 post-route 路径/扇出报告。通过：确认事实和推测分开；说明 ILA、计数器、B 高扇出各自影响和未排除因素。已有数据可复用，不为凑矩阵盲目重复长 route。

### T2：最小修正设计与代码（不需要板）

限于当前确认问题，优先改善 C 观测/ILA/VIO 实现。可研究只让少量状态字段承担触发、完整快照用于数据采集，或有明确延迟契约的调试流水；计数器实现调整必须保持原 64 位计量范围、首末拍、同拍事件与帧归属语义。不能直接删字段、缩窄范围、删计数器、断开真实边界或拿常量代替信号来制造 PASS。

最终快照必须仍可恢复 31 个字段和 16 帧对应关系，快照不能覆盖尚未导出的记录；如改变布局/读取方式，提交逐字段兼容映射和 C 操作方法，使原验收内容仍可取得。对 B 高扇出先分析实现阶段可复现处理，**不得直接修改固定 B RTL**；如证明必须修改 B，提交单独依赖说明与补丁建议，由 C/使用者决定新的来源冻结方案，不能悄悄混入其他 B 版本。

产物：可审查 Git patch/提交、`results/T2_design.md`、更新信号映射/IP 参数、变化影响范围。通过：改动限定于确认问题，原 C/基线与固定 B 不变，计量和接口契约未降低。

### T3：针对变化的功能回归（不需要板）

观察器自检须覆盖首末握手、同拍事件、停顿与联合停顿、保持违例检测、core_done/session_done 区分、UART 最终空闲、16 槽保留与溢出。真实固定 B 的 96×54 两帧受控暂停回归必须通过：每帧 16 周期 forced block、每帧 20,736 返回字节、Golden 0 失配、正常运行错误和保持违例均为 0。

如果修改真实握手、输出弹性级、复位、存储组织或帧结束关系，还必须重跑对应长背压与完整双帧端到端用例；若只是调试 IP 配置变化，明确复用已有完整数值证据的理由，不能把旧证据写成新候选运行结果。对人工注入错误的自检，应记录预期非零检测，不要求故意违例测试“错误全部零”。

产物：`results/T3_regression.md`、独立 attempt 源哈希/日志/返回数据。通过：所需断言和 Golden 全部通过，停顿计数准确，错误检测确实有效。

### T4：完整 C 板级实现与门控（不需要板，需要 Vivado）

对修正后的完整 `c_multiframe_synth_top` 从源码新建综合、布局和布线，150 MHz 为主线；100 MHz 是恢复/对照线，不能替代 150 MHz 登记通过。保持完整 C XDC，保持 `ExtraNetDelay_high`、`AggressiveExplore`、`NoTimingRelaxation` 和固定 B L5 phase 网的窄范围 fanout 标准作为首个可比流。若改变物理指令或增加局部实现约束，单独记录对照、依据与影响，不得放宽时序验收。

保留 +0.300 ns 额外 setup 压力与恢复原约束两套报告，记录实际原 uncertainty 及范围；自动器件 jitter 不可删除。最终门槛：setup/hold/pulse-width slack 均非负、对应 TNS/THS/TPWS=0，route errors=0，DRC Error=0，NSTD-1/UCIO-1 保持 Error，无新增未约束内部端点或无时钟寄存器；全部真实 B 层级/模型 ROM 正确。

产物：新源码/IP/ROM/约束哈希清单，clocks、timing_summary、setup/hold paths、route_status、DRC、check_timing、exceptions、utilization、原/压力/恢复 XDC、DCP SHA、完整命令与日志。通过：最终同一布线满足既定门槛，全部字段有实测报告支持。综合 WNS、工具 exit 0 或单个模块通过均不能代替此门槛。

### T5：交还 C 的板测包（生成不需要板）

仅对 T4 通过的物理设计生成 BIT 和对应 LTX；记录二者 SHA、顶层、频率、工具与来源提交。交付可复现脚本、观察器字段读取/导出脚本和逐步操作指南，并关联 BIT/LTX，避免读到旧镜像探针。

必须区分 `OBS_TEST_PAUSE_ENABLE=0` 普通观测版本与 `=1` 受控背压版本。现有失败版本是 `=0`；其 VIO 暂停位不会产生暂停。若交付板上强制背压功能，`=1` 必须另建受验收的实现、回归、BIT/LTX，不能以 `=0` 的时序报告覆盖它。不要让 C 通过长时间暂停串口读取来冒充内部 `out_ready` 背压：现有 UART 通路没有因此自动产生硬件反压。

产物：`results/T5_delivery.md`、通过镜像/调试文件及哈希、操作脚本、可回退基线说明、明确尚待 C 板测的清单。通过：离线交付可复现、镜像身份明确；此时状态仅 BOARD_READY，不是 BOARD_PASS。

### T6：C 本地实际板测（需要板）

C 核验新 BIT/LTX 后烧录，采集四种不同输入及连续 16 帧，逐帧 Golden 精确对比；读取实际握手计数 518,400/2,073,600、stripe_last/frame_last 计数（本几何 17/1）、frame_id、错误状态、最终 UART 空闲及停止/等待周期。受控暂停试验必须有实际 forced-block>0，解除后完成帧，保持违例和正常错误为 0。先用短、安全暂停，不在无人监管时长时间保持暂停。

C 保存 JTAG 身份、烧录日志、BIT/LTX 哈希、原始 UART 返回、逐帧比较 JSON、原始快照/ILA 导出、实际时序/计量结果。修改复位相关实现时，冷上电后 JTAG 恢复和 S0 空闲复位需要针对新版本复核。Flash 自主启动、忙时复位、HDMI、30 fps、200 MHz 不得因这次通过而自动登记通过。

## 6. 失败处理与禁止项

任何阶段失败先保留源哈希、完整命令、日志和原始输出；判定工具/环境、功能、约束或物理实现依赖及影响范围，再针对已确认原因处理。不覆盖旧 attempt，不删失败证据，不把 host timeout 直接记为功能失败，不把历史脚本解析错误误当硬件失败。

禁止 reset/清理原 dirty C，禁止修改冻结基线，禁止混入其他 B RTL，禁止降级 DRC、忽略约束、扩大 false path、虚填 IO 延迟、删除器件 jitter、任意 multicycle 或改 Golden/计数口径制造 PASS。REQP-1839/1840 与 BRAM 异步复位结构保持 OPEN，现有报告 20 条上限不是完整违规数量；本任务不能顺便未经论证改复位体系。

## 7. 需要 C 配合的事项

代码分析与 T0–T5 不需要 C 按键、接板或等待人在线。若 B 没有 Vivado runner，请先交根因/补丁/可执行脚本和 NOT_RUN 清单，C 再安排工具验证，不以“模型更强”替代实现报告。需要实时查询原失败 DCP时，由 C 提供大文件。T6 由 C 负责实际开发板、JTAG/UART、物理按钮/上电及新镜像验收。

请最终返回：根因与证据、最小 patch/提交、回归结果、150/100 MHz 实测状态、完整可复现构建、镜像与 LTX 哈希、C 板测操作指南、仍 OPEN 项及其依赖。不得只返回“已优化/应该能过”。

## 8. 可直接给 B 模型的启动指令

> 接手 `docs/C_TO_B_OBSERVATION_HANDOFF_2026-10-04.md` 指定的 C 内部观测候选时序任务。先读取交接书和 `experiments/c_observation_handoff_20261004/README.md`，核验来源和包哈希，报告工具条件，然后依次完成 T0–T5。B 固定为 `6cc8ea4173d2a720f741e80b7cbd9279558ee93a`，使用完整 C XDC 与真实多帧顶层，保护已通过的冻结基线。先依据原始时序报告隔离 ILA、观测计数器和 L5 高扇出因素，再作最小修正；禁止降低验收、混入其他 B 版本或用去掉观测的诊断构建登记通过。每阶段交付具体产物、通过条件和证据路径。已通过的 2025.2 基线 150 MHz 连续 16 帧板测继续有效，200 MHz 不阻塞；新候选须独立验证。没有 Vivado时可分析并交补丁，但所有未运行验证必须标为 NOT_RUN。最终把通过完整实现门控的源码、BIT/LTX、哈希和板测步骤交还 C；实际板测由 C 完成。
