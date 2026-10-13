---
name: nus-hpc
description: 从 macOS 或无头 Linux 使用 NUS IT HPC，处理安全认证、CPU/GPU 环境、数据传输、PBS 任务托管、监控、断点接续及账号/项目/存储到期。适用于 Atlas、Vanda、Hopper；NSCC 和院系独立服务器须另行确认配置。
---

# NUS HPC 一站式托管

把用户的计算需求落实为可追踪、可恢复、可停止的 PBS 工作流。默认用中文交流。不要让用户反复拼接 SSH、传文件和队列命令。

## 先确定当前状态

先识别执行端是 macOS、Linux 桌面还是无头 Linux，以及是否有人工 TTY、可达校内网络和持久执行器。复用已有 SSH alias、安全登录 helper、项目配置、任务清单和用户授权。只询问真正缺失的主机/用户名、代码和输入路径、资源规模及最终结果位置；密码不属于可询问信息。尚未登录时也继续准备运行脚本与资源方案。

读 [site-facts.md](references/site-facts.md) 确认官方来源与已知限制，再用实际主机的 `hpc pbs help`、`qstat -Qf`、`hpc space`、模块列表更新主机/队列/配额/存储规则。公开网页与旧例子不是实时队列配置。不得把 Atlas、Vanda、Hopper、HPC Cloud、NSCC 当成同一个环境。

## 连接与认证

首次连接、登录失败或无人值守需求，读 [authentication.md](references/authentication.md)。macOS 可复用用户已配置的 Keychain 登录 helper；无头 Linux 默认由用户在自己的 TTY 完成密码/MFA，再复用短时 SSH 连接。已有获准的凭据代理也可使用，但无头环境不能假定桌面密钥环已解锁。常规自动操作用 `BatchMode=yes`；首次凭据代理认证与后续复用分开，失效后停止自动重试。仅在站点允许时使用专用 SSH key。

以下辅助命令中的 `scripts/` 相对本 skill 目录；从项目目录运行时使用安装目录下的绝对路径。可运行只读预检：

```sh
python3 scripts/hpc.py doctor
python3 scripts/hpc.py probe --host nus-hpc
```

需要 Python 3.8+ 与 OpenSSH；生成的计算脚本使用 Bash。`nus-hpc` 是已核对主机密钥的 SSH alias，也可传完整主机名和 `--user NUS_ID`。可通过 `--control-path /absolute/socket` 复用现有会话，或 `--ssh-config /absolute/config` 指定配置。预检用远程 Bash 登录环境，并在 PBS 命令缺失时尝试 `module load pbs`；不索取密码、不提交作业。退出码 0 表示身份/PBS/队列查询通过，2 表示本地工具、SSH 或超时错误，3 表示 PBS 环境未就绪；配额工具仅检查是否存在，`hpc space` 单独限时查询，避免配额服务阻塞基本连接检查。完整输出留在本地。

## 项目与资源

用户已指定的项目在当前任务授权内直接复用。Hopper 提交需 `#PBS -P PROJECT_ID`；已知项目时无需先做 `amgr login/sshlogin`。成功的 PBS 提交能证明此次提交被接受，不能证明项目余额、到期日或未来运行权限。仅在用户要查询余额/期限、项目未知或调度器返回项目错误时使用项目查询流程。不要把本次测试的个人账号、项目 ID 或 helper 路径写成全局默认值。

Hopper 的普通 GPU 队列与 CPU 集群不同，先读 [site-facts.md](references/site-facts.md) 的实测段；纯 CPU 工作优先选择已获准的 CPU 队列。用户要求在 Hopper 测试时采用站点最小 GPU 资源并明确预算。

## 任务准备、提交与收尾

读 [operations.md](references/operations.md)。建立每个任务独立的目录与清单，包含输入/代码版本、PBS 资源、checkpoint 协议、输出和授权边界。

1. 检查代码入口、模块/容器/conda、MPI/线程、GPU 需求、路径与配额。依赖环境在站点允许的位置准备；不要在登录节点执行长计算、完整编译或大型解压。计算验证也用小型 PBS 作业。
2. 明确作业资源和数据目的地后，传入必要文件，先试运行再运行完整任务。禁止 `qsub -V` 导出整个本地环境，避免泄露 token。
3. 提交前记录 intent 与唯一任务/分段标识；成功后原子写入完整 PBS job ID。连接断开导致提交结果不明时先查队列与历史，不盲目重提。
4. 查询状态、日志及退出状态；作业从队列消失不等于成功。认证不可用、历史不可查或日志不完整时记为 UNKNOWN。
5. 验证结果文件与应用完成标记，校验归档/下载，报告任务 ID、结果位置、资源使用与后续动作。不要自动删除原始数据。

生成基础 PBS 文件（队列/资源值由实时发现获得）：

```sh
python3 scripts/hpc.py render --name experiment --queue VERIFIED_QUEUE \
  --workdir /absolute/verified/workdir --ncpus 4 --mem-gb 16 \
  --walltime 02:00:00 --command-file run.sh --output job.pbs
```

Hopper 单节点示例（替换实际项目和已核验工作目录）：

```sh
python3 scripts/hpc.py render --profile hopper --project PROJECT_ID \
  --name smoke --ngpus 1 --walltime 00:01:00 \
  --workdir /absolute/verified/workdir \
  --command-file assets/smoke.sh --output smoke.pbs
```

Hopper profile 默认路由队列 `auto`、加入 `#PBS -P` 与 `#PBS -k oed`，不硬编码站点分配的 CPU/内存；队列变更仍须现场核验。`generic` profile 保持显式 CPU/内存/队列配置，可加 `--project`。这些是单节点模板，多节点按站点样例处理。

`run.sh` 是经审阅的应用脚本，包含模块/环境激活与计算入口。生成器只准备文件，不传输或提交。简单验证可用 [assets/smoke.sh](assets/smoke.sh)：在全新目录生成输出，核对求和值 `5000050000`、`COMPLETE`、PBS `F` 与退出码 `0`；只运行该脚本不代表验证了 PBS、GPU 计算或断点接续。

## 托管与自动续期

读 [continuation.md](references/continuation.md)。分别处理计算接续、认证失效、账号/项目期限与数据保留，不许用一种“保活”代替所有机制。

- “托管到完成”包含提交、监控和用户已授权范围内的恢复。自动恢复须有可验证 checkpoint、有限资源预算、最多分段/重试次数及截止时间；缺失时先完成准备，再让用户确定实际影响运行的边界。
- PBS 负责已提交作业的运行，本地聊天或 SSH 断开通常不影响作业。skill 本身不会保持后台执行。只有用户要求未来监控/自动续跑时才创建可持久调度的自动化，明确执行主机和 VPN/认证前提；工具不可用时交付配置方案并说明尚未启用。
- 默认使用有限 PBS 分段依赖链（站点支持时），由应用 gate 决定后继是否真的计算；不无限递归 `qsub`，不默认延长运行中的 walltime。
- 账号/项目续期只使用已证实的门户或正式流程；没有官方自动续期 API 时提供到期提醒和申请材料，不宣称已经续期。
- 临时存储默认归档到用户指定的持久位置；除非明确获准延长保留，否则不使用 `touch` 或复制回写规避清理。

## 权限边界与报告

当前用户授权适用于指定任务，不扩张到新增收费资源、其他账号/项目、无限重试、修改远程认证或发送支持工单。用户已经授权的提交/监控/有限续跑无需反复确认。只在任务实际需要且缺少授权时确认具体动作。工具自动审批若拒绝某次认证操作，保留其具体原因，不改用其他路径规避；也不要把一次工具审批结果写成 NUS 全局认证政策。先做好可审阅的脚本、预算与申请草稿。

若用户要求发布或部署代码，遵守所在项目的 Git 提交规则，发布内容必须对应已提交版本；普通 PBS 提交不自动等于发布软件。对接外部通知/工单只在用户授权发送时执行。

交付时明确：已执行事项、运行或结束状态、认证是否可用于后台、自动化是否真正启用、续跑剩余额度、结果/归档位置及需要用户介入的唯一下一步。不要把生成模板或计划写成已完成远程操作。
