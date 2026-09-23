# B 五层真实 RTL 来源与校验（commit `ae29515`）

本目录是**成员 B 交付的真实五层 RTL**，已按用户指令正式纳入 C 工程文件列表。
**不是临时副本**：`scripts/*.tcl` 的仿真/综合文件列表直接指向本目录。

| 项 | 值 |
|---|---|
| 仓库 | `https://github.com/CalmDown789/a_dui_dui_dui` |
| 分支 | `member-b-five-layer-stream` |
| **锁定 commit** | `ae29515`（`ae29515945fbb6e9566626d7f2d28660ac94d5c4`） |
| 上游子目录 | `acx750_rtl/` |
| 取件方式 | `git fetch origin member-b-five-layer-stream` + `git cat-file blob ae29515:<path>` |

## 取件方式为什么是 `cat-file` 而不是复制工作树（本项目踩过的坑）

A 的本地克隆 `core.autocrlf=true`。**工作树检出会把 LF 改写成 CRLF**：例如
`expand_bias_packed.mem` 在提交里是 **202 B（LF）**，检出后变 **204 B（CRLF）**。
若从工作树复制、再与同一工作树对比，就是**自证循环**，证明不了 B 的提交字节。

故本目录的每个文件都用 `git cat-file blob %s:<path>` 取出**提交内的原始字节**写盘；
下表的 SHA-256 即**提交内容**的哈希，任何人可用下面命令复现：

```bash
git cat-file blob ae29515:<上游路径> | sha256sum
```

## 依赖闭包 = 15 个 RTL 文件（机械推导，非人工摘抄）

`_b_closure.py` 在剥离注释与字符串字面量后抽取 `module` 声明与例化，从 `b_core_real`
做传递闭包：可达模块 **15 个**、无未解析例化。`acx750_rtl/rtl/` 下另有 **19 个**模块
**不在闭包内**（compute/ 10、window/ 4、memory/ 1、postprocess/ 1、stream/ 3），
它们不参与五层网络，**不得**计入本路径的资源与验收。

## 文件与 SHA-256（= `ae29515` 中的 blob）

| 本目录相对路径 | 上游路径 | 字节 | CRLF | SHA-256 |
|---|---|---|---|---|
| `stream/b_core_real.sv` | `acx750_rtl/rtl/stream/b_core_real.sv` | 1177 | no | `3e9374f142188fc73000170a80c8393e9754b722c3a7767a00e90246a3d4c1fe` |
| `stream/fsrcnn_network_mem_top.sv` | `acx750_rtl/rtl/stream/fsrcnn_network_mem_top.sv` | 2697 | no | `52f02d6d539b1363f1542cd6d55f7ba13f507e6a3fe26af0aec32a5bf85062cf` |
| `stream/fsrcnn_network_core.sv` | `acx750_rtl/rtl/stream/fsrcnn_network_core.sv` | 5029 | no | `d0d413bae07d946852e3c6323d670c10a85f76da88dfdd54bc0f9c2c4db95037` |
| `stream/fsrcnn_stream_layer.sv` | `acx750_rtl/rtl/stream/fsrcnn_stream_layer.sv` | 2817 | no | `3ec52632fa1f790be28a417fde0e174f8d3524c819b5af736496115bcbe4ccbe` |
| `stream/window_stream_frontend.sv` | `acx750_rtl/rtl/stream/window_stream_frontend.sv` | 2986 | no | `94778afc21a3ea1ef1b5bb5adb33435b13745bf23fc4eef909cd6d1402c84660` |
| `stream/window_kminus1_bram.sv` | `acx750_rtl/rtl/stream/window_kminus1_bram.sv` | 3264 | no | `cf66969817e2ee2bb170fa3e3bc9f6a53d5d19b5282b3d5bf4c196fe000a34ee` |
| `stream/same_pad_raster.sv` | `acx750_rtl/rtl/stream/same_pad_raster.sv` | 2367 | no | `6c699400d3f8779797bba2813e70ca5abcd6e4bb48a978b1487ef8f0a357f784` |
| `stream/elastic_fifo.sv` | `acx750_rtl/rtl/stream/elastic_fifo.sv` | 1840 | no | `ad3409f54b1d1a0a9378364a6466e45a586a0bfc5e5bc9375a583a937129bb7b` |
| `stream/mac_issue_stage.sv` | `acx750_rtl/rtl/stream/mac_issue_stage.sv` | 2380 | no | `638a982889f2e708ad968f2fece4190391721860939a1d39cc18261fe7208203` |
| `stream/phase_mac_pipeline.sv` | `acx750_rtl/rtl/stream/phase_mac_pipeline.sv` | 4539 | no | `90274c20abafdb13b8550c9efc20ab6632e4b5fdf2f16690788b5a30ea9a6a4c` |
| `stream/phase_accumulator.sv` | `acx750_rtl/rtl/stream/phase_accumulator.sv` | 2773 | no | `1f03bd32647f09585b7b7b6b371646eb4f9aff92f627c4caabd92d263d35c66c` |
| `stream/eight_phase_issue.sv` | `acx750_rtl/rtl/stream/eight_phase_issue.sv` | 1830 | no | `26858a8148ea5194d47b177097e5621770bb50f7f8824be1e52c0d461f415b2a` |
| `stream/pixel_shuffle2x_row_banks.sv` | `acx750_rtl/rtl/stream/pixel_shuffle2x_row_banks.sv` | 4352 | no | `3b90586971f1d39f8f5d31a8ac4b7190df39ec67019fd505a0a067661e837940` |
| `stream/vector_postprocess_shared.sv` | `acx750_rtl/rtl/stream/vector_postprocess_shared.sv` | 4690 | no | `1203bb7cfb7b491ca5a2c43abb08c74d9ddcaeb133f10f7b8b913035f5d72bb8` |
| `postprocess/prelu_requantize.sv` | `acx750_rtl/rtl/postprocess/prelu_requantize.sv` | 4828 | no | `7f4f21ce208ae9489088bf856dada8cdd8f675352a993b4ff02f52e5205bcff1` |

## 参数 ROM（19 个 `*_packed.mem`）

`rom/member_a_d16_s8_m1_c16/`：由 **A 已审计整数资产**逐位重排；权重数值与量化语义
**未由 B 重新决定**。

| 文件 | 字节 | SHA-256 |
|---|---|---|
| `expand_bias_packed.mem` | 202 | `541c9ca488f625a321b2be5a871a5929f573e897af5b6206ba658c2dd55345ca` |
| `expand_prelu_packed.mem` | 138 | `052540e3bf7ee126b653016f2d4754e2fc8214a72fb5d0c07e93d832d0d838e9` |
| `expand_q31_packed.mem` | 202 | `250f870d53de711fedbf36b919626dba1835b8b0436b1cb7ac8a0ef2d750df92` |
| `expand_weights_packed.mem` | 330 | `9c95fd40e36a4c087178da49f842ae21c81209ce04bb55d2759161b5719f6e95` |
| `feature_bias_packed.mem` | 202 | `d753d3694b94a1eeee6b4f3c82f17107f9736f199b000bcdd2e83cfd0994e62e` |
| `feature_prelu_packed.mem` | 138 | `bd40a1b164e9dcd6cc8c35e340919b7cd9b3c5a42569bb4960c4e8bffd7f4733` |
| `feature_q31_packed.mem` | 202 | `a1fafc2057a3178fd4a92e18909e4f197c3fb642f83afbe8eccea3cd7823e897` |
| `feature_weights_packed.mem` | 874 | `e5b1fab6d868294cee9fb00b0ac0971ff64b2675f3d6f3343bf5f7421ce6e030` |
| `mapping0_bias_packed.mem` | 138 | `07ef3a9febe5fb4740d97a68203c17613386a4b73df783be980766dfea3fb159` |
| `mapping0_prelu_packed.mem` | 106 | `4ed2b69ee166a9775520d3191b50da846553a750b6c5d5515e4e91c3180f85fc` |
| `mapping0_q31_packed.mem` | 138 | `a662ad434c7c3dc5e85217d4d2070cc74f0d71f8297e324f866c49efed568aae` |
| `mapping0_weights_packed.mem` | 1226 | `7e3c8bfd15c121324d21a1151808b7e646438fc7d45080cd28487414912e159a` |
| `shrink_bias_packed.mem` | 138 | `a584ead8d3b912a9d8c14788bed57f4dca039379fe395c4d64508c864029973e` |
| `shrink_prelu_packed.mem` | 106 | `9c1ca29703ed76baa603fdb14feab6116d4e2287cf4343cc8e9bfc077051b68d` |
| `shrink_q31_packed.mem` | 138 | `fbb49763aec61bfed753d138671a55174521438bbb84b3ee94cce2f39c536839` |
| `shrink_weights_packed.mem` | 330 | `4f1f927796a7ea21dd19293501e9bd20f02b0f4d7293098fc0487146a8cd2bb8` |
| `subpixel_bias_packed.mem` | 106 | `403d3d432a73adc305071fc4b835f19244990bd0ea380b0dd604595cf3b8ebd0` |
| `subpixel_q31_packed.mem` | 106 | `9bc54acad057c236becbb93745fd33ed907e751f6dba5c4ea7e52ca7e3fbf9e8` |
| `subpixel_weights_packed.mem` | 3274 | `16d575c7eb63d002e96503a12428cea82061be69d12cec9cc5c63681d0d31b71` |
| `README.md` | 1314 | `236c8abfcca29da4465c96d3773b68c124087183b21d66a2fd09a9701e114762` |
| `manifest.json` | 5532 | `9c8206b6ac2dcbac0f5826b9ad6fb10183611de8abb39ccaeb9395c9c073abba` |

### `$readmemh` 路径约束（关键）

`fsrcnn_network_mem_top.sv` 的 `initial` 块用**裸文件名**调用，例如
`$readmemh("feature_weights_packed.mem",w1)` —— 没有目录前缀。因此这 19 个文件
**必须位于仿真进程的工作目录**（xsim 运行目录）。C 侧脚本为每个 TB 都把它们复制进去。

## 与旧交付的关系（勿混用）

`rtl/b_real/rtl/**`（旧 17 原语包）**不属于**本闭包。两者模块名重叠：`prelu_requantize`。

重叠文件的**版本差异实测**（同为 `prelu_requantize`，内容不同）：

| 来源 | SHA-256 |
|---|---|
| `ae29515:acx750_rtl/rtl/postprocess/prelu_requantize.sv` | `7f4f21ce208ae9489088bf856dada8cdd8f675352a993b4ff02f52e5205bcff1` |
| 本地旧副本 `rtl/b_real/rtl/rtl/postprocess/prelu_requantize.sv` | `0c914c8cd6e97278b8e509cfd30d0f9614d8477a2d50ce1db631e26b3c54ca89` |

同源？****否****

⇒ **绝不把两个目录放进同一份编译文件列表**（重复模块定义 + 版本混淆）。
旧包仅保留给其自身的原语级回归，**不得**作为五层网络验收路径。
