# 任务托管与提交恢复

## 清单

每个工作流用独立 UUID，清单留在用户私有项目目录，排除秘密、原始敏感日志和 SSH socket；原子写入（同目录临时文件 + rename），控制器用互斥锁，禁止两个监控者并发重提。

记录：workflow_id；用户/集群/完整 PBS server；代码 commit 或内容 hash；输入 manifest/hash；应用命令文件 hash；资源与队列；工作/checkpoint/输出/归档路径；job IDs 和分段数；每次提交 intent/时间/唯一 job name；状态与证据；重试策略；授权截止时间；最大分段和总请求 core/GPU hours；账号/项目/数据期限及来源（未知为 null）；控制器位置/自动化 ID。

不要将输入、用户名或完整内部路径上传到通知服务；状态摘要先去敏。

## 跨平台执行与项目

本地辅助程序仅依赖 Python 3.8+ 标准库和 OpenSSH，macOS/Linux 使用同一命令；计算脚本运行在远端 Bash。不要依赖本地 GNU `timeout`、`readlink -f`、`sha256sum` 或 macOS 专有 `security` 命令处理所有平台。跨平台超时、hash、路径、原子写文件交给 Python。Python 的实际可执行路径在执行端发现，不能把 macOS 虚拟环境绝对路径复制到 Linux。

PBS 命令通过远程登录环境执行，例如 `ssh -o BatchMode=yes nus-hpc 'bash -lc "command -v qsub; qstat -Qf"'`；仍不可用时按站点帮助 `module load pbs`。复用私有 control socket 时每次连接与传输显式使用同一 `-S`/`ControlPath`、用户名、主机，不能误连默认本地用户名。实际路径和命令参数用结构化参数及 shell quoting，不能拼接未转义的任务内容。

对已知项目，直接在脚本 `#PBS -P` 或 qsub `-P` 指定；不为探测余额而阻塞本已授权的有限测试。用户未指定项目时，优先已有私有配置/可读任务记录，再查询站点提供的项目接口；组名仅是线索，不能自行把组名推导成项目编号。预算服务登录为独立流程，遇工具审批拒绝遵守其结果。

## 环境与数据

按应用需求使用 module/conda/Apptainer 等站点支持方式；GPU CUDA 与驱动/框架版本核对，CPU 线程不超过请求资源。MPI 与多节点按站点模板，不在基础单节点模板上凭猜测改造。

SFTP/SCP 默认，rsync 仅在两端支持时使用；不默认 `--delete`。只上传任务所需输入和代码，不同步 `.env`、`.ssh` 或整个 home。传输先写临时名字，校验后 rename；确认所有计算节点可见相同 checkpoint 路径。大文件 checksum、解压等重 I/O 按站点规定使用作业或数据传输节点。

## 提交及幂等性

准备小型试运行，验证应用退出状态与输出；任务需要接续时还要验证 checkpoint 恢复，之后才放大规模。简单 smoke test 用 1 段、0 自动重试、60 秒 walltime；在 Hopper 上按最小 1 GPU 资源，告知伴随的 CPU/内存分配。使用全新目录，避免把上一轮 COMPLETE/输出当成本轮结果。在 `qsub` 前持久化 SUBMITTING intent，包含命令文件 hash 和唯一 name（适配本站 name 长度上限）；不要仅以人类任务名称去重。

保留 `qsub` 返回完整 job ID（含 server/数组标识），成功后持久化 SUBMITTED。远端可用原子 `mkdir .submission-attempt` 阻止同目录的第二次提交，先保存 stdout/stderr，再原子保存完整 job ID；目录存在不证明已提交。若远程调用超时或失联，或 SSH 返回非零但无法证实 qsub 被拒绝，标记 SUBMISSION_UNKNOWN；先按用户、name、server、提交时间与工作路径查询 `qstat -f`、`qstat -xf` 或本站可用的历史/记录。若不能唯一判断，不自动重提。qsub 不具备通用的 exactly-once API，本地锁不能消除网络歧义。

基本命令（先核对本站支持）：

```sh
qsub job.pbs
qstat -f FULL_JOB_ID
qstat -xf FULL_JOB_ID
qstat -Qf VERIFIED_QUEUE
qdel FULL_JOB_ID
```

`qdel` 仅处理本任务已确认属于当前用户的 ID。取消续跑先写 STOP/禁用控制器，取消已排队后继，再按用户要求处理当前任务，防止取消后被补交。数组任务保存数组父 ID 与子任务映射。

## 监控与收尾

轮询常规 5–15 分钟（按任务/站点调优）；正在交互验证的短 smoke test 可约 30–60 秒查询一次，网络错误有限退避。不在 login node 留无限循环 daemon。状态 Q/H 先检查队列、依赖和资源原因，不靠重复提交“加速”。PBS job state F 必须结合 Exit_status、应用状态、日志和输出验证。

超时可恢复、节点故障、OOM、软件/输入错误分别处理；OOM 只有在预算允许且用户已授权资源调整时扩大资源。成功归档验证文件数、大小/校验与应用结果；归档失败单独标记，不重新计算完整任务。没有结果证据则 UNKNOWN，不能从 qstat 返回非零推断成功。

## 分级验收

本地生成/语法测试、连接/PBS 预检、真实调度/结果读取、断点恢复、长期无人值守分别记录。不要用前一层成功宣称后一层已验证。状态证据含完整 PBS ID、项目、执行节点、退出状态、实际 walltime、输出校验。下载日志/结果失败时标为归档待完成，不自动重跑计算。
