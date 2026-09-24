# FSRCNN 参数 ROM

目录中的 19 个 `.mem` 文件是成员 A 冻结的 `d16/s8/m1/c16` 量化参数，按成员 B 的 RTL packed bus 位序排列。权重和量化数值未作修改；`manifest.json` 记录源量化参数及导出文件的校验信息。

网络仿真和综合通过 `$readmemh` 读取这些参数。运行时应将 19 个文件放在工具脚本指定的工作目录中；具体目录由相应 Vivado/XSim 工程配置决定。
