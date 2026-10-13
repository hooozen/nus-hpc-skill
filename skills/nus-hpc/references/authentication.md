# macOS 与无头 Linux 认证

## 先复用，再补齐缺失的认证

检查现有 SSH alias、可信主机记录、ControlMaster、agent 和用户已授权的凭据 helper；只读取配置与可用状态，不读取秘密。账号、主机、项目编号可以写入本地配置；密码、OTP、私钥口令和 token 不进入聊天、脚本常量、命令参数、环境变量、任务清单或日志。凭据库条目名、helper 路径和 socket 路径不是秘密，可作为配置句柄。

分别判断下列能力，不能把其中一项失败推导为全部不可用：

| 能力 | 判断依据 | 何时需要 |
| --- | --- | --- |
| 网络/VPN | 目标主机实际可达；必要时用户完成官方 VPN/MFA | 连接 HPC |
| SSH | 非交互执行轻量身份检查成功 | 传文件、查询和提交 |
| PBS/项目使用权 | 调度器可用，指定项目的任务被接受 | 提交计算任务 |
| 预算服务 | 该服务自己的有效会话和查询结果 | 查询未知项目、余额或管理额度 |

已知项目时按实时帮助验证 `qsub -P PROJECT_ID` 后提交用户授权的测试；不要把 `amgr sshlogin -H` 当成所有 PBS 作业的前置步骤。已有真实测试证明：已知项目编号的任务可以通过直接指定项目完成；这不保证其他项目、账号或站点同样有权限。若提交明确报项目无权/失效，记录错误并处理该问题。

项目未知时先查用户已有配置和任务记录。只有任务确实需要预算服务才检查其帮助与现有登录；`amgr sshlogin -H` 是建立认证会话，不是纯查询。依据当前用户授权及工具审批执行，不因旧对话曾受阻而永久禁止，也不把旧审批当成新操作的许可。任何 token 由官方客户端管理，不打印、复制到任务目录或转交模型。预算查询不可用时如实标为未知，不捏造余额或扩大预算。

## 人工初始化与共用 SSH 配置

确认 NUS-ID 已开通 HPC；账号申请/项目审批与登录不同。校外使用官方支持的 VPN 流程；无头 Linux 不假定存在图形客户端，应确认当前官方 Linux/终端支持方式或在已有可达的执行主机上工作。MFA 由用户完成，不自动回应或反复推送。

首次主机信任核对 NUS IT 或独立可信来源的指纹。`ssh-keyscan` 只收集待比对值，不能证明身份；已有可信 `known_hosts` 可直接复用。指纹变化暂停，不删除记录绕过检查。用户在自己的 Terminal/TTY 输入密码；模型可见的 PTY 不作为密码输入渠道。没有可接管终端时给出本地命令，用户执行后再检查。

在已有 `~/.ssh/config` 中合并专用 Host block，保留其他配置；目录 `~/.ssh` 与 `~/.ssh/controlmasters` 设为 0700，配置和凭据文件仅本人可读写。示例填值后用于 macOS 与 Linux：

```sshconfig
Host nus-hpc
    HostName VERIFIED_HOST.nus.edu.sg
    User NUS_ID
    StrictHostKeyChecking yes
    ForwardAgent no
    ControlMaster auto
    ControlPath ~/.ssh/controlmasters/nus-%C
    ControlPersist 30m
    ServerAliveInterval 30
    ServerAliveCountMax 3
    ConnectTimeout 15
```

```sh
# 用户在实际运行托管程序的机器、同一系统账号下建立会话
ssh -MNf nus-hpc
# 检查 master，再验证实际远程访问；后者也支持已有 agent 的非交互认证
ssh -O check nus-hpc
ssh -o BatchMode=yes nus-hpc 'id -un'
# 结束本任务独占的连接
ssh -O exit nus-hpc
```

`ControlPersist 30m` 是没有客户端连接后的空闲期限，适合正常每 15 分钟检查并留出调度延迟；应大于实际轮询间隔加预期抖动。短时手动操作可以缩短，机器休眠或服务中断仍可能使连接过期。持续监控可能让 master 长期不退出，因此空闲期限不是绝对授权期限。后台托管的控制器记录并检查 `auth_deadline`，到期拒绝新操作，并关闭本任务独占的 master。共享 master 不应为本任务截止而强制中断其他使用者，应提前选独立控制路径。`ssh-agent` 中 key 到期也不会撤销已经建立的 SSH master。keepalive 只检测连接，不续 VPN、MFA、账号或 PBS walltime。[OpenSSH 配置说明](https://man.openbsd.org/ssh_config)

ControlMaster socket 是可使用会话的能力，必须保存在执行机本地、私有且路径足够短的目录。家目录位于共享文件系统或路径过长时，改用经过验证的本地私有运行目录，确保不同执行机不会误用相同路径。不能复制 socket 到另一台机器，不能放进项目或备份。

## macOS：交互登录或已有 Keychain helper

默认由用户在 Terminal 建立上面的 SSH master，Codex 随后用 `BatchMode=yes` 复用。也可沿用用户已经配置、已授权的 Keychain-backed `SSH_ASKPASS` helper：先检查 helper 的文件权限、目标账号/服务绑定及是否会输出日志，调用时仅传 helper 路径和非敏感标识。秘密只在凭据库 → helper → SSH 的本地进程链路中流动；不得单独执行凭据读取命令把密码回显到工具结果，也不把输出捕获进模型可见变量或文件。

建立 master 的一次受控调用可以启用 askpass；此时 `BatchMode=yes` 会禁止密码提示，因此不应同时使用。`SSH_ASKPASS_REQUIRE=force` 仅在本机 OpenSSH 支持且该 helper 已验证时使用，设有限提示次数；后续监控恢复 `BatchMode=yes`。凭据库锁定、helper 需要用户确认或一次认证失败时进入 `AUTH_REQUIRED`，让用户解锁或重新认证，不能循环尝试。后台服务与交互桌面进程的 Keychain 访问权限可能不同，须在实际执行上下文验证。[OpenSSH askpass 行为](https://man.openbsd.org/ssh.1)

macOS 的 `UseKeychain` 针对 SSH **私钥口令**，不自动保存远程 NUS-ID 密码；远程密码的 Keychain helper 是另一路配置。不要把 macOS 专用选项无条件复制到 Linux；跨平台共享配置时将其限定在本机配置，或使用已验证的 `IgnoreUnknown UseKeychain` 兼容方式。[Apple OpenSSH 说明](https://developer.apple.com/library/archive/technotes/tn2449/_index.html)

## 无头 Linux：用户 TTY 初始化，后台复用

默认不依赖桌面凭据库。用户先通过自己的终端登录执行机，在同一 Linux 账号下完成 VPN/SSH 认证并建立 master；worker 使用相同 SSH 配置和控制路径。密码只由用户直接输入 TTY。`ssh-agent` 管理私钥认证，不能替代远程账号密码库。

如果已有站点允许、用户授权的 vault/credential helper，可复用其非交互接口和已有解锁方式，不默认安装新服务或创建长期凭据。由 helper 直接交给 SSH，不经过日志、shell 展开或环境变量传递密码。GNOME Keyring/Secret Service 只是可选方案：需要可用的用户 D-Bus、服务实现及已解锁的集合；SSH 登录、cron 或 systemd worker 未必拥有这些条件。不要建议仅安装 `secret-tool` 就可完成无头认证，也不能把凭据库主密码写进启动脚本。[Secret Service 规范](https://specifications.freedesktop.org/secret-service/latest/description.html)

在启用任何后台调度前，从它**实际的运行身份与环境**验证以下条件：

- 执行机网络/VPN 可用，当前账号能读取 SSH 配置和可信主机记录，能访问同机私有 master socket。
- 若使用 agent，`SSH_AUTH_SOCK` 指向该账号真实可访问的 socket；登录 shell 的变量不会自然出现在 cron/systemd 环境中。只显式传递需要的路径等非敏感配置，不导出整个环境。
- systemd 用户服务、agent、VPN 与 master 在用户退出登录后是否仍存在取决于当前系统配置；不能因交互终端成功就宣称能无人值守。`linger` 可能维持用户管理器，但不负责解锁凭据库、续 MFA 或恢复 VPN；只在用户要求持续托管且确有必要时配置，不默认修改系统登录策略。
- 重启或 runtime 目录清理后 socket 可能失效；配置文件存在不代表已经登录。用户重新建立认证后再恢复未提交动作。

上述条件缺失时，仍可提交当前已授权且认证可用的 PBS 作业，再报告后台监控/后续补交的限制。不能承诺无人值守自动重新登录。PBS 已接受的作业通常不依赖本地 SSH 持续在线。

## 可选：站点允许的专用 SSH key

公开入门指南确认 NUS-ID 登录，但不保证中央 HPC 允许公钥；先核实当前站点政策，不能套用 SoC/实验室服务器的教程。允许时使用带口令的专用 key 或站点支持的硬件 key，由用户本地生成/解锁，私钥留在执行机；设置专用 `IdentityFile` 与 `IdentitiesOnly yes`，例如：

```sh
# 仅在已有专用 key 且站点允许时，由用户运行
ssh-add -t 8h ~/.ssh/id_ed25519_nus_hpc
```

期限应覆盖用户授权的操作窗口；已有 master 仍受其自身截止策略约束。公钥安装按已有明确授权执行，不重复索取已给出的许可；保留现有 `authorized_keys`，不得改成无口令私钥或转发 agent 到计算节点。[OpenSSH ssh-add](https://man.openbsd.org/ssh-add)

## 状态与恢复

分别保存 `network`、`ssh`、`pbs`、`budget_service` 的非敏感状态及检查时间。网络失败记 `NETWORK_UNAVAILABLE`，认证拒绝记 `AUTH_REQUIRED`，主机密钥冲突记 `HOST_KEY_CHANGED`，明确账号/项目权限错误记 `ACCESS_REVIEW_REQUIRED`；预算未查记 `UNKNOWN`。只有本次动作需要的能力就绪才执行，不把认证中断当成计算失败。

一次认证失败后停止自动登录重试，保留提交 intent、PBS IDs 与待办，仅在状态变化或需要用户处理时通知；无认证的网络检查可以有限退避。用户恢复会话后，先核对既有作业与结果，再补交尚未提交的动作，避免重复扣费。实际审批拒绝仍须按工具要求报告具体被拒动作和原因；继续不依赖该动作的工作。
